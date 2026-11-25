# ventas/admin.py
"""Configuración del panel admin para la app ventas."""
from django.contrib import admin, messages


from .models import DetalleVenta, Pedido, Venta
from .tasks import enviar_confirmacion_pedido




class DetalleVentaInline(admin.TabularInline):
    """Líneas de detalle dentro del admin de Venta."""


    model       = DetalleVenta
    extra       = 1            # mostrar 1 fila vacía para agregar
    fields      = ['producto', 'cantidad', 'precio_unitario']
    readonly_fields = []




@admin.register(Venta)
class VentaAdmin(admin.ModelAdmin):
    """Admin de ventas con detalles inline y total calculado."""


    list_display    = ['pk', 'cliente', 'fecha', 'total_admin']
    search_fields   = ['cliente__nombre', 'cliente__correo']
    readonly_fields = ['fecha']
    inlines         = [DetalleVentaInline]
    date_hierarchy  = 'fecha'


    @admin.display(description='Total ($)')
    def total_admin(self, obj: Venta) -> str:
        """Muestra el total calculado de la venta en la lista."""
        return f"${obj.total:.2f}"




@admin.register(DetalleVenta)
class DetalleVentaAdmin(admin.ModelAdmin):
    """Admin de líneas de detalle (vista independiente)."""


    list_display  = ['pk', 'venta', 'producto', 'cantidad',
                     'precio_unitario', 'subtotal_admin']
    search_fields = ['producto__nombre', 'venta__pk']
    readonly_fields = ['precio_unitario']


    @admin.display(description='Subtotal ($)')
    def subtotal_admin(self, obj: DetalleVenta) -> str:
        return f"${obj.subtotal:.2f}"




@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):
    list_display   = ['numero_pedido', 'cliente', 'estado',
                      'fecha_pedido', 'total_pagado', 'correo_enviado']
    search_fields  = ['numero_pedido', 'cliente__nombre']
    list_filter    = ['estado', 'correo_enviado']
    readonly_fields = ['fecha_pedido']
    
    # Agregamos las dos acciones
    actions        = ['reenviar_confirmacion', 'enviar_reporte_manual']

    @admin.action(description='Enviar correo de confirmación (pagados sin correo)')
    def reenviar_confirmacion(self, request, queryset):
        # ... (tu código actual de reenviar_confirmacion) ...
        pendientes = queryset.filter(estado='pagado', correo_enviado=False)
        encolados, errores = 0, 0
        for pedido in pendientes:
            try:
                from ventas.tasks import enviar_confirmacion_pedido
                enviar_confirmacion_pedido.apply(args=[pedido.pk]) # Usamos apply
                encolados += 1
            except Exception as exc:
                errores += 1
                self.message_user(request, f'{pedido.numero_pedido}: {exc}', messages.ERROR)
        omitidos = queryset.count() - pendientes.count()
        self.message_user(request, f'Correos encolados: {encolados}. Errores: {errores}. Omitidos: {omitidos}.', messages.SUCCESS if not errores else messages.WARNING)

    @admin.action(description='Enviar REPORTE DIARIO de ventas (Prueba manual)')
    def enviar_reporte_manual(self, request, queryset):
        from ventas.tasks import reporte_ventas_diario
        try:
            # Ejecutamos la tarea síncronamente
            resultado = reporte_ventas_diario.apply().get()
            self.message_user(
                request, 
                f"Reporte enviado con éxito. Pedidos hoy: {resultado['total_pedidos']}, Facturado: ${resultado['total_facturado']}", 
                messages.SUCCESS
            )
        except Exception as exc:
            self.message_user(request, f"Error al enviar reporte: {exc}", messages.ERROR)