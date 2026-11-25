# ventas/tasks.py
"""Tareas asíncronas de la app ventas — W17 y W18.

W16: estructura base (solo log).
W17: envío real de correos con django-anymail + SendGrid.
W18: reporte diario de ventas con Celery Beat.
"""
import logging
from decimal import Decimal, InvalidOperation

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

logger = logging.getLogger(__name__)


def _url_absoluta(nombre_url: str) -> str:
    """Construye una URL absoluta sin request."""
    return f'{settings.SITE_URL}{reverse(nombre_url)}'


def _items_con_subtotal(items_snapshot: list) -> list:
    """Agrega 'subtotal' (precio × cantidad, Decimal) a cada item."""
    items = []
    for item in items_snapshot or []:
        try:
            precio   = Decimal(str(item.get('precio', '0')))
            cantidad = int(item.get('cantidad', 0))
        except (InvalidOperation, TypeError, ValueError):
            precio, cantidad = Decimal('0.00'), 0
        items.append({
            **item,
            'precio':   precio.quantize(Decimal('0.01')),
            'cantidad': cantidad,
            'subtotal': (precio * cantidad).quantize(Decimal('0.01')),
        })
    return items


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name='ventas.enviar_confirmacion_pedido',
)
def enviar_confirmacion_pedido(self, pedido_id: int) -> dict:
    """Envía el correo de confirmación de pedido al cliente."""
    from configuracion.models import ConfiguracionERP
    from ventas.models        import Pedido

    try:
        pedido = Pedido.objects.select_related('cliente').get(pk=pedido_id)
    except Pedido.DoesNotExist:
        logger.error(f'[correo_confirmacion] Pedido {pedido_id} no existe.')
        return {'estado': 'error', 'pedido_id': pedido_id, 'razon': 'Pedido no encontrado'}

    if pedido.correo_enviado:
        logger.info(f'[correo_confirmacion] Pedido {pedido.numero_pedido}: correo ya enviado — skip.')
        return {'estado': 'skip', 'pedido_id': pedido_id, 'razon': 'correo ya enviado'}

    config = ConfiguracionERP.get_instance()
    contexto = {
        'pedido':     pedido,
        'config':     config,
        'items':      _items_con_subtotal(pedido.items_snapshot),
        'url_tienda': _url_absoluta('catalogo:catalogo'),
    }

    asunto = f'Confirmación de pedido {pedido.numero_pedido} — {config.nombre_empresa}'
    texto_plano = render_to_string('emails/confirmacion_pedido.txt',  contexto)
    html_body   = render_to_string('emails/confirmacion_pedido.html', contexto)

    correo_destino = pedido.cliente.correo

    mensaje = EmailMultiAlternatives(
        subject    = asunto,
        body       = texto_plano,
        from_email = settings.DEFAULT_FROM_EMAIL,
        to         = [correo_destino],
    )
    mensaje.attach_alternative(html_body, 'text/html')

    try:
        mensaje.send()
    except Exception as exc:
        logger.error(f'[correo_confirmacion] Error al enviar correo: {exc}')
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))

    Pedido.objects.filter(pk=pedido.pk).update(correo_enviado=True)
    logger.info(f'[correo_confirmacion] Correo enviado a {correo_destino} para pedido {pedido.numero_pedido}.')
    return {'estado': 'ok', 'pedido_id': pedido_id, 'correo': correo_destino}


@shared_task(
    bind=True,
    max_retries=1,
    name='ventas.verificar_stock_bajo',
)
def verificar_stock_bajo(self, umbral: int = 5) -> dict:
    """Verifica productos con stock bajo y envía alerta al admin."""
    from productos.models import Producto

    productos_bajos = list(
        Producto.objects
        .filter(activo=True, stock__lt=umbral)
        .values('pk', 'nombre', 'stock', 'categoria__nombre')
        .order_by('stock')
    )

    if not productos_bajos:
        logger.info(f'[stock_bajo] Todos los productos tienen stock >= {umbral}. OK.')
        return {'umbral': umbral, 'total': 0, 'productos_bajos': [], 'alerta_enviada': False}

    logger.warning(f'[stock_bajo] {len(productos_bajos)} producto(s) con stock < {umbral}.')
    alerta_enviada = False
    if settings.ADMINS:
        alerta_enviada = _enviar_alerta_stock(productos_bajos, umbral)

    return {
        'umbral':          umbral,
        'total':           len(productos_bajos),
        'productos_bajos': productos_bajos,
        'alerta_enviada':  alerta_enviada,
    }


def _enviar_alerta_stock(productos_bajos: list, umbral: int) -> bool:
    """Envía el correo de alerta de stock al primer administrador."""
    from configuracion.models import ConfiguracionERP

    config = ConfiguracionERP.get_instance()
    fecha  = timezone.localtime().strftime('%d/%m/%Y %H:%M')

    contexto = {
        'productos_bajos': productos_bajos,
        'total_productos': len(productos_bajos),
        'umbral':          umbral,
        'fecha':           fecha,
        'url_admin':       _url_absoluta('admin:productos_producto_changelist'),
        'config':          config,
    }

    asunto = f'[ALERTA] {len(productos_bajos)} producto(s) con stock < {umbral}'
    texto_plano = render_to_string('emails/alerta_stock.txt',  contexto)
    html_body   = render_to_string('emails/alerta_stock.html', contexto)

    _admin_nombre, admin_correo = settings.ADMINS[0]

    mensaje = EmailMultiAlternatives(
        subject    = asunto,
        body       = texto_plano,
        from_email = settings.DEFAULT_FROM_EMAIL,
        to         = [admin_correo],
    )
    mensaje.attach_alternative(html_body, 'text/html')

    try:
        mensaje.send()
    except Exception as exc:
        logger.error(f'[stock_bajo] Error al enviar alerta: {exc}')
        return False

    logger.info(f'[stock_bajo] Alerta enviada a {admin_correo}. {len(productos_bajos)} productos.')
    return True


# ── W18: reporte diario (Celery Beat) ─────────────────────────────────────

@shared_task(
    bind=True,
    max_retries=2,
    name='ventas.reporte_ventas_diario',
)
def reporte_ventas_diario(self) -> dict:
    """Genera y envía el reporte diario de ventas al administrador."""
    from decimal import Decimal
    from django.db.models import DecimalField, ExpressionWrapper, F, Sum
    from django.utils import timezone
    from configuracion.models import ConfiguracionERP
    from ventas.models        import DetalleVenta, Pedido

    hoy    = timezone.localdate()
    config = ConfiguracionERP.get_instance()

    # 1. KPIs del día
    pedidos_hoy = Pedido.objects.filter(
        fecha_pedido__date=hoy,
        estado='pagado'
    )
    total_pedidos   = pedidos_hoy.count()
    total_facturado = pedidos_hoy.aggregate(
        total=Sum('total_pagado')
    )['total'] or Decimal('0.00')

    # 2. Top 5 productos
    acumulado = {}

    internas = (
        DetalleVenta.objects
        .filter(venta__fecha__date=hoy)
        .values(nombre=F('producto__nombre'))
        .annotate(
            unidades=Sum('cantidad'),
            ingreso=Sum(
                ExpressionWrapper(
                    F('cantidad') * F('precio_unitario'),
                    output_field=DecimalField(max_digits=12, decimal_places=2)
                )
            )
        )
    )
    for fila in internas:
        dato = acumulado.setdefault(
            fila['nombre'], {'unidades': 0, 'ingreso': Decimal('0.00')}
        )
        dato['unidades'] += fila['unidades'] or 0
        dato['ingreso']  += fila['ingreso'] or Decimal('0.00')

    for pedido in pedidos_hoy.only('items_snapshot'):
        for item in _items_con_subtotal(pedido.items_snapshot):
            dato = acumulado.setdefault(
                item.get('nombre', '¿?'),
                {'unidades': 0, 'ingreso': Decimal('0.00')},
            )
            dato['unidades'] += item['cantidad']
            # Aseguramos que sea Decimal, por si viene como str
            subtotal = item['subtotal']
            if not isinstance(subtotal, Decimal):
                subtotal = Decimal(str(subtotal))
            dato['ingreso'] += subtotal

    top_productos = sorted(
        (
            {'nombre': nombre, 'unidades': d['unidades'],
             'ingreso': str(d['ingreso'].quantize(Decimal('0.01')))}
            for nombre, d in acumulado.items()
        ),
        key=lambda x: Decimal(x['ingreso']),
        reverse=True,
    )[:5]

    logger.info(
        f'[reporte_diario] {hoy}: {total_pedidos} pedidos, '
        f'${total_facturado} facturados, {len(top_productos)} productos top.'
    )

    # 3. Enviar correo
    if settings.ADMINS:
        _enviar_reporte_ventas(
            hoy, total_pedidos, total_facturado, top_productos, config
        )

    return {
        'fecha':           str(hoy),
        'total_pedidos':   total_pedidos,
        'total_facturado': str(total_facturado),
        'top_productos':   top_productos,
    }


def _enviar_reporte_ventas(fecha, total_pedidos, total_facturado, top_productos, config) -> None:
    """Envía el reporte diario al primer administrador configurado."""
    url_admin = _url_absoluta('admin:ventas_pedido_changelist')
    fecha_str = fecha.strftime('%d/%m/%Y')

    contexto = {
        'fecha':           fecha_str,
        'config':          config,
        'total_pedidos':   total_pedidos,
        'total_facturado': total_facturado,
        'top_productos':   top_productos,
        'url_admin':       url_admin,
        'hora_programada': getattr(settings, 'REPORTE_DIARIO_HORA', '06:50'),
    }

    asunto      = f'Reporte de ventas del {fecha_str} — {config.nombre_empresa}'
    texto_plano = render_to_string('emails/reporte_ventas.txt',  contexto)
    html_body   = render_to_string('emails/reporte_ventas.html', contexto)

    admin_nombre, admin_correo = settings.ADMINS[0]

    mensaje = EmailMultiAlternatives(
        subject    = asunto,
        body       = texto_plano,
        from_email = settings.DEFAULT_FROM_EMAIL,
        to         = [admin_correo],
    )
    mensaje.attach_alternative(html_body, 'text/html')

    try:
        mensaje.send()
        logger.info(f'[reporte_diario] Reporte enviado a {admin_correo}.')
    except Exception as exc:
        logger.error(f'[reporte_diario] Error al enviar reporte: {exc}')