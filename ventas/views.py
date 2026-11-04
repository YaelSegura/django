# ventas/views.py
"""Vistas de la app ventas — W07 + W08.

Lectura (W07): VentaListView y VentaDetailView.
Escritura (W08): crear_venta (función) y VentaDeleteView.
"""
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.generic import DeleteView, DetailView, ListView

from .forms  import DetalleVentaForm, VentaForm
from .models import DetalleVenta, Venta


class VentaListView(ListView):
    """Lista paginada de ventas en orden cronológico inverso."""

    model               = Venta
    template_name       = 'ventas/lista.html'
    context_object_name = 'ventas'
    paginate_by         = 20

    def get_queryset(self):
        """Pre-carga cliente para evitar N+1 en la tabla de ventas."""
        return (
            Venta.objects
            .select_related('cliente')
            .order_by('-fecha')
        )


class VentaDetailView(DetailView):
    """Detalle de una venta con todas sus líneas de producto."""

    model               = Venta
    template_name       = 'ventas/detalle.html'
    context_object_name = 'venta'
    pk_url_kwarg        = 'venta_id'

    def get_queryset(self):
        """Pre-carga cliente y prefetch líneas de detalle."""
        return (
            Venta.objects
            .select_related('cliente')
            .prefetch_related('detalles__producto')
        )


@login_required
@permission_required('ventas.add_venta', raise_exception=True)
def crear_venta(request):
    """Crea un encabezado de venta con una línea de detalle.

    @login_required            → verifica autenticación
    @permission_required(...)  → verifica permiso add_venta (403 si no lo tiene)
    """
    venta_form   = VentaForm(request.POST or None)
    detalle_form = DetalleVentaForm(request.POST or None)

    if request.method == 'POST':
        if venta_form.is_valid() and detalle_form.is_valid():
            venta         = venta_form.save()
            detalle       = detalle_form.save(commit=False)
            detalle.venta = venta
            detalle.save()
            messages.success(
                request,
                f'Venta #{venta.pk} registrada. '
                f'Total: ${venta.total:.2f}'
            )
            return redirect('ventas:detalle', venta_id=venta.pk)

    return render(request, 'ventas/crear.html', {
        'venta_form':   venta_form,
        'detalle_form': detalle_form,
    })


class VentaDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    """Confirmación y borrado de una venta (y sus detalles en cascada)."""

    model         = Venta
    template_name = 'ventas/eliminar.html'
    pk_url_kwarg  = 'venta_id'
    success_url   = reverse_lazy('ventas:lista')
    permission_required = 'ventas.delete_venta'


    def form_valid(self, form):
        pk       = self.object.pk
        response = super().form_valid(form)
        messages.success(self.request, f'Venta #{pk} eliminada.')
        return response

# ── Factura en PDF — W12 (motor: xhtml2pdf) ───────────────────────────────
import os
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string


def _resolver_ruta_media(uri, rel):
    """Convierte /media/... en ruta de disco para que xhtml2pdf cargue imágenes."""
    if uri.startswith(settings.MEDIA_URL):
        return os.path.join(settings.MEDIA_ROOT, uri[len(settings.MEDIA_URL):])
    return uri


@login_required
def venta_pdf(request, venta_id: int) -> HttpResponse:
    """Genera y descarga la factura de una venta en PDF.

    Motor: xhtml2pdf (WeasyPrint/Docker no disponible en el equipo).

    Raises:
        Http404: si la venta no existe.
    """
    from xhtml2pdf import pisa
    from configuracion.models import ConfiguracionERP

    venta = get_object_or_404(
        Venta.objects
        .select_related('cliente')
        .prefetch_related('detalles__producto'),
        pk=venta_id
    )
    config = ConfiguracionERP.get_instance()

    centavo      = Decimal('0.01')
    subtotal     = venta.total
    iva          = (subtotal * config.iva_porcentaje / Decimal('100')).quantize(
        centavo, rounding=ROUND_HALF_UP
    )
    total_con_iva = subtotal + iva

    html = render_to_string('ventas/factura_pdf.html', {
        'venta':         venta,
        'config':        config,
        'hoy':           date.today(),
        'subtotal':      subtotal,
        'iva':           iva,
        'total_con_iva': total_con_iva,
    })

    buffer    = BytesIO()
    resultado = pisa.CreatePDF(
        src=html, dest=buffer, link_callback=_resolver_ruta_media
    )
    if resultado.err:
        return HttpResponse('No se pudo generar el PDF.', status=500)

    respuesta = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    respuesta['Content-Disposition'] = (
        f'attachment; filename="factura_{venta.pk:05d}.pdf"'
    )
    return respuesta    