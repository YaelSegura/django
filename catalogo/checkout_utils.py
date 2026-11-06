# catalogo/checkout_utils.py
"""Funciones auxiliares para el proceso de checkout — W14.

Separadas de views.py para facilitar las pruebas unitarias.
"""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from clientes.models      import Cliente
from configuracion.models import ConfiguracionERP
from ventas.models        import Pedido


def calcular_totales(carrito: dict) -> dict:
    """Calcula subtotal, IVA y total del carrito.

    Args:
        carrito: dict de sesión con estructura
                 {str(pk): {precio: str, cantidad: int, ...}}

    Returns:
        dict con subtotal, iva_pct, iva_monto, total (todos Decimal).
    """
    config  = ConfiguracionERP.get_instance()
    iva_pct = config.iva_porcentaje / Decimal('100')

    subtotal = sum(
        (Decimal(datos['precio']) * int(datos['cantidad'])
         for datos in carrito.values()),
        Decimal('0.00')
    )
    iva_monto = (subtotal * iva_pct).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP
    )
    total = subtotal + iva_monto

    return {
        'subtotal':  subtotal,
        'iva_pct':   config.iva_porcentaje,
        'iva_monto': iva_monto,
        'total':     total,
    }
def construir_items(carrito: dict) -> list:
    """Convierte el carrito de sesión en una lista lista para el template.

    Calcula el subtotal de cada línea como Decimal. Esto reemplaza el
    uso de {% widthratio %} en el template, que falla con precios
    guardados como texto ("500.00").

    Returns:
        Lista de dicts con prod_id, nombre, cantidad, precio y subtotal.
    """
    items = []
    for prod_id, datos in carrito.items():
        precio   = Decimal(datos['precio'])
        cantidad = int(datos['cantidad'])
        items.append({
            'prod_id':  prod_id,
            'nombre':   datos['nombre'],
            'cantidad': cantidad,
            'precio':   precio,
            'subtotal': precio * cantidad,
        })
    return items

def construir_items(carrito: dict) -> list:
    """Convierte el carrito de sesión en una lista lista para el template.

    Calcula el subtotal de cada línea como Decimal. Esto reemplaza el
    uso de {% widthratio %} en el template, que falla con precios
    guardados como texto ("500.00").

    Returns:
        Lista de dicts con prod_id, nombre, cantidad, precio y subtotal.
    """
    items = []
    for prod_id, datos in carrito.items():
        precio   = Decimal(datos['precio'])
        cantidad = int(datos['cantidad'])
        items.append({
            'prod_id':  prod_id,
            'nombre':   datos['nombre'],
            'cantidad': cantidad,
            'precio':   precio,
            'subtotal': precio * cantidad,
        })
    return items


def obtener_o_crear_cliente(user) -> Cliente:
    """Obtiene o crea un Cliente del ERP vinculado al usuario Django.

    Usa el correo del usuario si existe; si no, genera uno temporal.

    Args:
        user: instancia de django.contrib.auth.models.User.

    Returns:
        Cliente: instancia del modelo Cliente del ERP.
    """
    correo = user.email or f"{user.username}@erp.local"
    nombre = user.get_full_name() or user.username

    cliente, _ = Cliente.objects.get_or_create(
        correo=correo,
        defaults={'nombre': nombre, 'activo': True}
    )
    # Actualizar nombre si el usuario tiene nombre completo
    if cliente.nombre != nombre and user.get_full_name():
        cliente.nombre = nombre
        cliente.save(update_fields=['nombre'])

    return cliente


def generar_numero_pedido() -> str:
    """Genera un número de pedido único con formato PED-YYYY-NNNN.

    Returns:
        str: por ejemplo 'PED-2026-0001'
    """
    anio      = date.today().year
    siguiente = Pedido.objects.filter(
        numero_pedido__startswith=f'PED-{anio}-'
    ).count() + 1
    return f'PED-{anio}-{siguiente:04d}'