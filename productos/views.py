# productos/views.py
"""Vistas de la app productos — W07 + W08 + W12.

Lectura (W07): ListView y DetailView con select_related y paginación.
Escritura (W08): CreateView, UpdateView y DeleteView con login.
Exportación (W12): exportar_excel (openpyxl).
"""
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.urls import reverse_lazy
from django.views.generic import (
    CreateView, DeleteView, DetailView, ListView, UpdateView
)

from .forms import ProductoForm
from .models import Producto


class ProductoListView(ListView):
    """Lista paginada de productos activos."""

    model               = Producto
    template_name       = 'productos/lista.html'
    context_object_name = 'productos'
    paginate_by         = 20

    def get_queryset(self):
        """Devuelve productos activos con FKs pre-cargadas (evita N+1)."""
        return (
            Producto.objects
            .select_related('categoria', 'proveedor')
            .filter(activo=True)
            .order_by('nombre')
        )


class ProductoDetailView(DetailView):
    """Detalle de un producto por ID de URL."""

    model               = Producto
    template_name       = 'productos/detalle.html'
    context_object_name = 'producto'
    pk_url_kwarg        = 'producto_id'

    def get_queryset(self):
        """Pre-carga FKs para evitar queries adicionales en el template."""
        return Producto.objects.select_related('categoria', 'proveedor')


class ProductoCreateView(LoginRequiredMixin, CreateView):
    """Formulario para crear un nuevo producto."""

    model         = Producto
    form_class    = ProductoForm
    template_name = 'productos/crear.html'
    success_url   = reverse_lazy('productos:lista')

    def form_valid(self, form):
        """Agrega mensaje flash de éxito al guardar."""
        response = super().form_valid(form)
        messages.success(
            self.request,
            f'Producto "{self.object.nombre}" creado exitosamente.'
        )
        return response


class ProductoUpdateView(LoginRequiredMixin, UpdateView):
    """Formulario para editar un producto existente."""

    model         = Producto
    form_class    = ProductoForm
    template_name = 'productos/editar.html'
    pk_url_kwarg  = 'producto_id'
    success_url   = reverse_lazy('productos:lista')

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            f'Producto "{self.object.nombre}" actualizado.'
        )
        return response


class ProductoDeleteView(LoginRequiredMixin, DeleteView):
    """Confirmación y borrado de un producto (solo POST)."""

    model         = Producto
    template_name = 'productos/eliminar.html'
    pk_url_kwarg  = 'producto_id'
    success_url   = reverse_lazy('productos:lista')

    def form_valid(self, form):
        nombre   = self.object.nombre
        response = super().form_valid(form)
        messages.success(
            self.request,
            f'Producto "{nombre}" eliminado.'
        )
        return response


@login_required
def exportar_excel(request) -> HttpResponse:
    """Exporta el inventario de productos activos a un archivo .xlsx.

    Returns:
        HttpResponse con el archivo Excel como descarga directa.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = 'Inventario'

    encabezados = ['ID', 'Producto', 'Categoría', 'Proveedor',
                   'Precio', 'Stock', 'Activo']
    ws.append(encabezados)

    # Estilo Fable 5 AzulERP: encabezado azul marino con texto blanco
    relleno = PatternFill('solid', fgColor='0A2342')
    for celda in ws[1]:
        celda.font      = Font(bold=True, color='FFFFFF')
        celda.fill      = relleno
        celda.alignment = Alignment(horizontal='center')

    productos = (
        Producto.objects
        .select_related('categoria', 'proveedor')
        .filter(activo=True)
        .order_by('nombre')
    )
    for p in productos:
        ws.append([
            p.pk,
            p.nombre,
            p.categoria.nombre,
            p.proveedor.nombre if p.proveedor else '-',
            float(p.precio),
            p.stock,
            'Sí' if p.activo else 'No',
        ])

    for col, ancho in zip('ABCDEFG', (8, 34, 22, 26, 14, 10, 10)):
        ws.column_dimensions[col].width = ancho

    respuesta = HttpResponse(
        content_type=(
            'application/vnd.openxmlformats-officedocument'
            '.spreadsheetml.sheet'
        )
    )
    respuesta['Content-Disposition'] = (
        f'attachment; filename="inventario_{date.today():%Y%m%d}.xlsx"'
    )
    wb.save(respuesta)
    return respuesta