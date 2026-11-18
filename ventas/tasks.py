# ventas/tasks.py
"""Tareas asíncronas de la app ventas — W17.

W17 implementa el envío real de correos con django-anymail + SendGrid.

Idempotencia:
    Pedido.correo_enviado=True previene envíos duplicados si la tarea
    se llama más de una vez para el mismo pedido.
"""
import logging
from decimal import Decimal, InvalidOperation

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

logger = logging.getLogger(__name__)

SITE_URL_DEFAULT = 'https://django-km8n.onrender.com'


def _site_url() -> str:
    """URL base del sitio (configurable con SITE_URL en settings)."""
    return getattr(settings, 'SITE_URL', SITE_URL_DEFAULT).rstrip('/')


def _items_con_subtotal(items: list) -> list:
    """Agrega 'subtotal' (texto con 2 decimales) a cada ítem del snapshot."""
    resultado = []
    for item in items:
        try:
            subtotal = Decimal(str(item.get('precio', '0'))) * int(
                item.get('cantidad', 0)
            )
        except (InvalidOperation, ValueError, TypeError):
            subtotal = Decimal('0')
        nuevo = dict(item)
        nuevo['subtotal'] = f'{subtotal:.2f}'
        resultado.append(nuevo)
    return resultado


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name='ventas.enviar_confirmacion_pedido',
)
def enviar_confirmacion_pedido(self, pedido_id: int) -> dict:
    """Envía el correo de confirmación de pedido al cliente.

    Garantías:
        - Idempotente: si correo_enviado=True, aborta sin error.
        - Retry automático hasta 3 veces si falla el envío.

    Args:
        pedido_id: ID del Pedido confirmado.

    Returns:
        dict con estado, pedido_id y correo del destinatario.
    """
    from configuracion.models import ConfiguracionERP  # import local
    from ventas.models import Pedido                    # import local

    try:
        pedido = Pedido.objects.select_related('cliente').get(pk=pedido_id)
    except Pedido.DoesNotExist:
        logger.error(f'[Tarea enviar_confirmacion] Pedido {pedido_id} no existe.')
        return {'estado': 'error', 'pedido_id': pedido_id}

    # ── Idempotencia ────────────────────────────────────────────────────
    if pedido.correo_enviado:
        logger.info(
            f'[correo_confirmacion] Pedido {pedido.numero_pedido}: '
            f'correo ya enviado anteriormente — skip.'
        )
        return {
            'estado':    'skip',
            'pedido_id': pedido_id,
            'razon':     'correo ya enviado',
        }

    correo_destino = pedido.cliente.correo
    if not correo_destino:
        logger.error(
            f'[correo_confirmacion] Pedido {pedido.numero_pedido}: '
            f'el cliente no tiene correo.'
        )
        return {'estado': 'error', 'pedido_id': pedido_id,
                'razon': 'cliente sin correo'}

    config = ConfiguracionERP.get_instance()

    # ── Contexto del correo ─────────────────────────────────────────────
    contexto = {
        'pedido':       pedido,
        'config':       config,
        'items':        _items_con_subtotal(pedido.items_snapshot or []),
        'url_catalogo': f'{_site_url()}/catalogo/',
    }

    # render_to_string sin request (las tareas Celery no tienen request)
    asunto = (
        f'Confirmación de pedido {pedido.numero_pedido} '
        f'— {config.nombre_empresa}'
    )
    texto_plano = render_to_string('emails/confirmacion_pedido.txt', contexto)
    html_body = render_to_string('emails/confirmacion_pedido.html', contexto)

    mensaje = EmailMultiAlternatives(
        subject=asunto,
        body=texto_plano,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[correo_destino],
    )
    mensaje.attach_alternative(html_body, 'text/html')

    # ── Enviar y manejar errores ────────────────────────────────────────
    try:
        mensaje.send()
    except Exception as exc:
        logger.error(
            f'[correo_confirmacion] Error al enviar correo para pedido '
            f'{pedido.numero_pedido}: {exc}'
        )
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))

    logger.info(
        f'[correo_confirmacion] Correo enviado a {correo_destino} '
        f'para pedido {pedido.numero_pedido}.'
    )

    # Marcar como enviado para evitar duplicados
    pedido.correo_enviado = True
    pedido.save(update_fields=['correo_enviado'])

    return {
        'estado':    'ok',
        'pedido_id': pedido_id,
        'numero':    pedido.numero_pedido,
        'cliente':   correo_destino,
        'correo':    correo_destino,
    }


@shared_task(
    bind=True,
    max_retries=1,
    name='ventas.verificar_stock_bajo',
)
def verificar_stock_bajo(self, umbral: int = 5) -> dict:
    """Verifica productos con stock bajo y envía alerta al administrador.

    Args:
        umbral: cantidad mínima de stock antes de alertar (default: 5).

    Returns:
        dict con umbral, total y lista de productos con stock bajo.
    """
    from productos.models import Producto   # import local

    productos_bajos = list(
        Producto.objects
        .filter(activo=True, stock__lt=umbral)
        .values('pk', 'nombre', 'stock', 'categoria__nombre')
        .order_by('stock')
    )

    if not productos_bajos:
        logger.info(
            f'[Tarea verificar_stock] Todos los productos tienen '
            f'stock >= {umbral}. OK.'
        )
        return {'umbral': umbral, 'productos_bajos': [], 'total': 0}

    logger.warning(
        f'[Tarea verificar_stock] {len(productos_bajos)} producto(s) '
        f'con stock < {umbral}: {[p["nombre"] for p in productos_bajos]}'
    )

    if settings.ADMINS:
        _enviar_alerta_stock(productos_bajos, umbral)

    return {
        'umbral':          umbral,
        'productos_bajos': productos_bajos,
        'total':           len(productos_bajos),
    }


def _enviar_alerta_stock(productos_bajos: list, umbral: int) -> None:
    """Envía el correo de alerta de stock al primer administrador."""
    from configuracion.models import ConfiguracionERP   # import local

    config = ConfiguracionERP.get_instance()

    contexto = {
        'productos_bajos': productos_bajos,
        'total_productos': len(productos_bajos),
        'umbral':          umbral,
        'fecha':           timezone.now().strftime('%d/%m/%Y %H:%M'),
        'url_admin':       f'{_site_url()}/admin/productos/producto/',
        'config':          config,
    }

    asunto = f'[ALERTA] {len(productos_bajos)} producto(s) con stock < {umbral}'
    texto_plano = render_to_string('emails/alerta_stock.txt', contexto)
    html_body = render_to_string('emails/alerta_stock.html', contexto)

    _, admin_correo = settings.ADMINS[0]

    mensaje = EmailMultiAlternatives(
        subject=asunto,
        body=texto_plano,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[admin_correo],
    )
    mensaje.attach_alternative(html_body, 'text/html')

    try:
        mensaje.send()
        logger.info(
            f'[stock_bajo] Alerta enviada a {admin_correo}. '
            f'{len(productos_bajos)} productos.'
        )
    except Exception as exc:
        logger.error(f'[stock_bajo] Error al enviar alerta: {exc}')