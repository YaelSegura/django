# catalogo/views.py
"""Vistas del módulo de catálogo y carrito — W13.

Módulo público (no requiere autenticación para lectura).
El carrito se almacena en la sesión Django.

Estructura del carrito en sesión:
    request.session['carrito'] = {
        '1': {
            'nombre':   'Laptop HP',
            'precio':   '10000.00',   # str — Decimal no es JSON serializable
            'cantidad': 2,
            'imagen':   'productos/laptop.jpg'  # o None
        },
        ...
    }
"""
from decimal import Decimal

from django.contrib import messages
from django.http import HttpRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import ListView

from productos.models import Producto

from .filters import ProductoFilter
import logging
import stripe
from django.conf import settings
from django.contrib.auth.decorators import login_required

from ventas.models import Pedido
from .checkout_utils import (
    calcular_totales,
    armar_items,
    generar_numero_pedido,
    obtener_o_crear_cliente,
)

# Configurar la clave secreta de Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY
logger = logging.getLogger(__name__)
# ── CATÁLOGO ───────────────────────────────────────────────────────────────

class CatalogoView(ListView):
    """Catálogo público de productos con filtros.

    No requiere autenticación — accesible para cualquier visitante.
    """

    model               = Producto
    template_name       = 'catalogo/catalogo.html'
    context_object_name = 'productos'
    paginate_by         = 12    # 3 filas de 4 tarjetas

    def get_queryset(self):
        """Filtra productos activos aplicando los filtros del request."""
        qs = (
            Producto.objects
            .select_related('categoria', 'proveedor')
            .filter(activo=True)
            .order_by('nombre')
        )
        self.filtro = ProductoFilter(self.request.GET, queryset=qs)
        return self.filtro.qs

    def get_context_data(self, **kwargs):
        """Agrega el objeto filtro al contexto para renderizar el formulario."""
        ctx = super().get_context_data(**kwargs)
        ctx['filtro']     = self.filtro
        ctx['categorias'] = self.filtro.form.fields['categoria'].queryset
        return ctx


# ── CARRITO ─────────────────────────────────────────────────────────────────

def _obtener_carrito(request: HttpRequest) -> dict:
    """Obtiene el carrito de la sesión o crea uno vacío."""
    return request.session.get('carrito', {})


def _guardar_carrito(request: HttpRequest, carrito: dict) -> None:
    """Guarda el carrito en la sesión y marca como modificado."""
    request.session['carrito'] = carrito
    request.session.modified   = True


def _leer_cantidad(request: HttpRequest, minimo: int = 1,
                   maximo: int = 99) -> int:
    """Lee 'cantidad' del POST como entero acotado entre minimo y maximo.

    Evita errores 500 con valores no numéricos y cantidades negativas
    que alterarían el total del carrito.
    """
    try:
        valor = int(request.POST.get('cantidad', 1))
    except (TypeError, ValueError):
        valor = 1
    return max(minimo, min(valor, maximo))


def ver_carrito(request):
    """Muestra el contenido del carrito con el total calculado.

    Convierte los precios de str a Decimal para el cálculo.
    """
    carrito = _obtener_carrito(request)

    items = []
    total = Decimal('0.00')

    for prod_id, datos in carrito.items():
        precio   = Decimal(datos['precio'])
        cantidad = int(datos['cantidad'])
        subtotal = precio * cantidad
        total   += subtotal
        items.append({
            'prod_id':  prod_id,
            'nombre':   datos['nombre'],
            'precio':   precio,
            'cantidad': cantidad,
            'subtotal': subtotal,
            'imagen':   datos.get('imagen'),
        })

    return render(request, 'catalogo/carrito.html', {
        'items': items,
        'total': total,
    })


def agregar_al_carrito(request, producto_id: int):
    """Agrega un producto al carrito o incrementa su cantidad.

    Solo acepta POST para proteger contra CSRF.
    La cantidad puede enviarse como parámetro POST (default: 1).

    Args:
        producto_id: ID del producto a agregar.
    """
    if request.method != 'POST':
        return redirect('catalogo:catalogo')

    producto = get_object_or_404(Producto, pk=producto_id, activo=True)
    carrito  = _obtener_carrito(request)

    clave    = str(producto_id)
    cantidad = _leer_cantidad(request)

    if clave in carrito:
        carrito[clave]['cantidad'] += cantidad
    else:
        carrito[clave] = {
            'nombre':   producto.nombre,
            'precio':   str(producto.precio),   # str para JSON serializable
            'cantidad': cantidad,
            'imagen':   producto.imagen.name if producto.imagen else None,
        }

    _guardar_carrito(request, carrito)
    messages.success(
        request,
        f'"{producto.nombre}" agregado al carrito.'
    )

    # Volver a la página anterior (catálogo, detalle de producto, etc.),
    # solo si pertenece a este mismo sitio.
    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER')
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect('catalogo:catalogo')


def remover_del_carrito(request, producto_id: int):
    """Elimina un producto del carrito.

    Solo acepta POST.
    """
    if request.method != 'POST':
        return redirect('catalogo:carrito')

    carrito = _obtener_carrito(request)
    clave   = str(producto_id)

    nombre = carrito.get(clave, {}).get('nombre', 'Producto')
    carrito.pop(clave, None)
    _guardar_carrito(request, carrito)

    messages.warning(request, f'"{nombre}" eliminado del carrito.')
    return redirect('catalogo:carrito')


def actualizar_cantidad(request, producto_id: int):
    """Actualiza la cantidad de un producto en el carrito.

    Solo acepta POST. Si la cantidad llega a 0 o menos, elimina el item.
    """
    if request.method != 'POST':
        return redirect('catalogo:carrito')

    carrito  = _obtener_carrito(request)
    clave    = str(producto_id)
    cantidad = _leer_cantidad(request, minimo=0)

    if clave in carrito:
        if cantidad > 0:
            carrito[clave]['cantidad'] = cantidad
        else:
            carrito.pop(clave)

    _guardar_carrito(request, carrito)
    return redirect('catalogo:carrito')


def vaciar_carrito(request):
    """Elimina todos los productos del carrito."""
    if request.method == 'POST':
        _guardar_carrito(request, {})
        messages.info(request, 'Carrito vaciado.')
    return redirect('catalogo:carrito')
# ── CHECKOUT — W14 ─────────────────────────────────────────────────────────

def _cancelar_pedido(pedido) -> None:
    """Marca como cancelado un pedido cuyo pago no pudo iniciarse.

    Evita que queden pedidos 'pendiente' huérfanos cuando Stripe falla.
    """
    if pedido is not None and pedido.pk:
        pedido.estado = 'cancelado'
        pedido.save(update_fields=['estado'])


@login_required
def checkout(request):
    """Proceso de pago: muestra resumen y crea PaymentIntent de Stripe.

    GET:  Muestra resumen del carrito con IVA calculado.
          No crea PaymentIntent (espera a POST).

    POST: Valida carrito → crea Pedido → crea PaymentIntent →
          retorna client_secret al template para que Stripe.js
          confirme el pago del lado del cliente.

    Redirige a /catalogo/ si el carrito está vacío.
    """
    carrito = _obtener_carrito(request)
    if not carrito:
        messages.warning(request, 'Tu carrito está vacío.')
        return redirect('catalogo:catalogo')

    totales         = calcular_totales(carrito)
    items           = armar_items(carrito)
    publishable_key = settings.STRIPE_PUBLISHABLE_KEY

    if request.method == 'POST':
        pedido = None
        try:
            # ── 1. Vincular usuario con Cliente del ERP ────────────────
            cliente = obtener_o_crear_cliente(request.user)

            # ── 2. Crear el Pedido en estado "pendiente" ───────────────
            numero = generar_numero_pedido()
            pedido = Pedido.objects.create(
                numero_pedido = numero,
                cliente       = cliente,
                estado        = 'pendiente',
                total_pagado  = totales['total'],
            )

            # ── 3. Crear PaymentIntent en Stripe ───────────────────────
            # Monto en centavos (Stripe requiere entero)
            monto_centavos = int(totales['total'] * 100)

            intent = stripe.PaymentIntent.create(
                amount          = monto_centavos,
                currency        = 'mxn',
                metadata        = {
                    'pedido_id':  pedido.pk,
                    'pedido_num': pedido.numero_pedido,
                    'cliente':    cliente.nombre,
                },
                idempotency_key = f'pedido-{pedido.pk}',
            )

            # ── 4. Retornar client_secret al template ──────────────────
            return render(request, 'catalogo/checkout.html', {
                'items':           items,
                'totales':         totales,
                'pedido':          pedido,
                'client_secret':   intent.client_secret,
                'publishable_key': publishable_key,
            })

        except stripe.error.StripeError as exc:
            _cancelar_pedido(pedido)
            detalle = exc.user_message or 'no se pudo procesar el pago'
            messages.error(
                request,
                f'Error al conectar con Stripe: {detalle}'
            )
            return redirect('catalogo:pago_error')

        except Exception:
            logger.exception('Fallo inesperado en el checkout')
            _cancelar_pedido(pedido)
            messages.error(
                request,
                'Error inesperado en el proceso de pago.'
            )
            return redirect('catalogo:pago_error')

    # GET — solo mostrar resumen (sin PaymentIntent)
    return render(request, 'catalogo/checkout.html', {
        'items':           items,
        'totales':         totales,
        'client_secret':   None,          # se genera en POST
        'publishable_key': publishable_key,
    })


def pago_exitoso(request, pedido_id: int):
    """Vista de confirmación post-pago exitoso.

    Vacía el carrito de la sesión y muestra el número de pedido.
    Stripe.js redirige aquí después de `confirmCardPayment` exitoso.
    """
    pedido = get_object_or_404(Pedido, pk=pedido_id)

    # Vaciar el carrito al confirmar el pago
    _guardar_carrito(request, {})
    messages.success(
        request,
        f'¡Pago exitoso! Tu pedido {pedido.numero_pedido} '
        f'está confirmado. Total: ${pedido.total_pagado}'
    )

    return render(request, 'catalogo/pago_exitoso.html', {
        'pedido': pedido,
    })


def pago_error(request):
    """Vista de error de pago — muestra mensaje y permite reintentar."""
    return render(request, 'catalogo/pago_error.html')