import logging
import stripe
from django.conf import settings
from django.db.models import F
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from productos.models import Producto
from ventas.models    import Pedido

logger = logging.getLogger(__name__)

@csrf_exempt
@require_POST
def stripe_webhook(request) -> HttpResponse:
    payload    = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')

    # ── 1. Verificar firma ─────────────────────────────────────────────────
    try:
        event = stripe.Webhook.construct_event(
            payload    = payload,
            sig_header = sig_header,
            secret     = settings.STRIPE_WEBHOOK_SECRET,
        )
    except ValueError:
        logger.warning('Webhook: payload inválido recibido.')
        return HttpResponse('Payload inválido.', status=400)
    except stripe.error.SignatureVerificationError:
        logger.warning('Webhook: firma inválida — posible ataque.')
        return HttpResponse('Firma inválida.', status=400)

    # ⚠️ CORRECCIÓN CLAVE DE LA GUÍA:
    # stripe >= 15 devuelve StripeObject, que ya NO es un dict.
    if hasattr(event, 'to_dict'):
        event = event.to_dict()

    # ── 2. Despachar por tipo de evento ────────────────────────────────────
    tipo = event['type']
    logger.info(f'Webhook recibido: {tipo}')

    if tipo == 'payment_intent.succeeded':
        _manejar_pago_exitoso(event['data']['object'])
    elif tipo == 'payment_intent.payment_failed':
        _manejar_pago_fallido(event['data']['object'])

    return HttpResponse(status=200)


def _manejar_pago_exitoso(payment_intent: dict) -> None:
    pedido_id = _extraer_pedido_id(payment_intent)
    if pedido_id is None:
        return

    try:
        pedido = Pedido.objects.get(pk=pedido_id)
    except Pedido.DoesNotExist:
        logger.error(f'Webhook: Pedido {pedido_id} no encontrado en BD.')
        return

    # Actualizar estado y descontar stock
    if pedido.estado != 'pagado':
        pedido.estado = 'pagado'
        pedido.save(update_fields=['estado'])
        logger.info(f'Pedido {pedido.numero_pedido} actualizado a "pagado".')
        _descontar_stock(pedido)

def _manejar_pago_fallido(payment_intent: dict) -> None:
    pedido_id = _extraer_pedido_id(payment_intent)
    if pedido_id is None:
        return
    try:
        pedido = Pedido.objects.get(pk=pedido_id)
        if pedido.estado == 'pendiente':
            pedido.estado = 'cancelado'
            pedido.save(update_fields=['estado'])
    except Pedido.DoesNotExist:
        pass

def _extraer_pedido_id(payment_intent: dict) -> int | None:
    metadata  = payment_intent.get('metadata', {})
    pedido_id = metadata.get('pedido_id')
    if not pedido_id:
        return None
    try:
        return int(pedido_id)
    except (ValueError, TypeError):
        return None

def _descontar_stock(pedido: 'Pedido') -> None:
    items = pedido.items_snapshot or []
    for item in items:
        producto_id = item.get('producto_id')
        cantidad    = int(item.get('cantidad', 0))
        if not producto_id or cantidad <= 0:
            continue

        # Aquí es donde el producto se "elimina" (se descuenta) del catálogo
        filas_actualizadas = Producto.objects.filter(
            pk=producto_id,
            stock__gte=cantidad 
        ).update(
            stock=F('stock') - cantidad
        )

        if filas_actualizadas:
            logger.info(f'Stock decrementado: Producto {producto_id} - {cantidad} unidades.')