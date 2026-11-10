# catalogo/webhook_views.py
import logging
import stripe
from django.conf import settings
from django.db.models import F
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from productos.models import Producto
from ventas.models import Pedido

logger = logging.getLogger(__name__)

@csrf_exempt
@require_POST
def stripe_webhook(request) -> HttpResponse:
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')

    try:
        event = stripe.Webhook.construct_event(
            payload=payload, sig_header=sig_header, secret=settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        return HttpResponse('Payload inválido.', status=400)
    except stripe.error.SignatureVerificationError:
        return HttpResponse('Firma inválida.', status=400)

    tipo = event['type']
    logger.info(f'Webhook recibido: {tipo}')

    if tipo == 'payment_intent.succeeded':
        _manejar_pago_exitoso(event['data']['object'])
    elif tipo == 'payment_intent.payment_failed':
        _manejar_pago_fallido(event['data']['object'])

    return HttpResponse(status=200)

def _manejar_pago_exitoso(payment_intent: dict) -> None:
    pedido_id = int(payment_intent.get('metadata', {}).get('pedido_id', 0))
    try:
        pedido = Pedido.objects.get(pk=pedido_id)
        if pedido.estado != 'pagado':
            pedido.estado = 'pagado'
            pedido.save(update_fields=['estado'])
            _descontar_stock(pedido)
    except Pedido.DoesNotExist:
        logger.error(f'Pedido {pedido_id} no encontrado.')

def _manejar_pago_fallido(payment_intent: dict) -> None:
    pedido_id = int(payment_intent.get('metadata', {}).get('pedido_id', 0))
    Pedido.objects.filter(pk=pedido_id, estado='pendiente').update(estado='cancelado')

def _descontar_stock(pedido: Pedido) -> None:
    for item in pedido.items_snapshot:
        Producto.objects.filter(
            pk=item['producto_id'], stock__gte=item['cantidad']
        ).update(stock=F('stock') - item['cantidad'])