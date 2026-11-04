"""Suite de pruebas W12 — Factura PDF (xhtml2pdf) y exportación Excel.

Motor de PDF: xhtml2pdf (WeasyPrint/Docker no disponible en el equipo).
Se ejecuta en el entorno normal, sin Docker.

Ejecutar con:
    python manage.py test tests.test_w12_documentos --verbosity=2

Resultado esperado:
    Ran 8 tests in X.XXXs
    OK
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from clientes.models      import Cliente
from configuracion.models import ConfiguracionERP
from productos.models     import Categoria, Producto
from ventas.models        import DetalleVenta, Venta


class VentaPDFTest(TestCase):
    """Tests de la vista venta_pdf y de la exportación a Excel."""

    def setUp(self):
        ConfiguracionERP.get_instance()
        self.user = User.objects.create_user('pdfuser', password='pass')
        cat        = Categoria.objects.create(nombre='Cat PDF')
        prod       = Producto.objects.create(
            nombre='Producto PDF', precio=Decimal('500.00'),
            stock=5, categoria=cat
        )
        cli        = Cliente.objects.create(
            nombre='Cliente PDF', correo='pdf@test.com'
        )
        self.venta = Venta.objects.create(cliente=cli)
        DetalleVenta.objects.create(
            venta=self.venta, producto=prod,
            cantidad=2, precio_unitario=Decimal('500.00')
        )

    def test_pdf_sin_auth_redirige_a_login(self):
        """GET /ventas/<id>/pdf/ sin login → 302 al login."""
        r = self.client.get(
            reverse('ventas:pdf', args=[self.venta.pk])
        )
        self.assertEqual(r.status_code, 302)
        self.assertIn('/accounts/login/', r['Location'])

    def test_pdf_con_auth_devuelve_200(self):
        """GET /ventas/<id>/pdf/ con login → 200."""
        self.client.force_login(self.user)
        r = self.client.get(
            reverse('ventas:pdf', args=[self.venta.pk])
        )
        self.assertEqual(r.status_code, 200)

    def test_pdf_content_type_application_pdf(self):
        """La respuesta debe tener Content-Type application/pdf."""
        self.client.force_login(self.user)
        r = self.client.get(
            reverse('ventas:pdf', args=[self.venta.pk])
        )
        self.assertIn('application/pdf', r.get('Content-Type', ''))

    def test_pdf_empieza_con_header_pdf(self):
        """El contenido del PDF debe empezar con '%PDF' (PDF válido)."""
        self.client.force_login(self.user)
        r = self.client.get(
            reverse('ventas:pdf', args=[self.venta.pk])
        )
        self.assertTrue(
            r.content[:4] == b'%PDF',
            "La respuesta no es un PDF válido (no empieza con %PDF)"
        )

    def test_pdf_content_disposition_attachment(self):
        """La respuesta debe ser descarga directa (attachment)."""
        self.client.force_login(self.user)
        r = self.client.get(
            reverse('ventas:pdf', args=[self.venta.pk])
        )
        disposition = r.get('Content-Disposition', '')
        self.assertIn('attachment', disposition)
        self.assertIn('.pdf', disposition)

    def test_pdf_venta_inexistente_devuelve_404(self):
        """GET /ventas/9999/pdf/ → 404 Not Found."""
        self.client.force_login(self.user)
        r = self.client.get(
            reverse('ventas:pdf', args=[9999])
        )
        self.assertEqual(r.status_code, 404)

    def test_pdf_es_mayor_que_1kb(self):
        """Un PDF real debe tener al menos 1 KB."""
        self.client.force_login(self.user)
        r = self.client.get(
            reverse('ventas:pdf', args=[self.venta.pk])
        )
        self.assertGreater(
            len(r.content), 1024,
            "El PDF parece demasiado pequeño para ser real"
        )

    def test_pdf_excel_exportacion_tambien_funciona(self):
        """La exportación de Excel (openpyxl) debe funcionar."""
        self.client.force_login(self.user)
        r = self.client.get(reverse('productos:exportar_excel'))
        self.assertEqual(r.status_code, 200)
        self.assertIn('spreadsheetml', r.get('Content-Type', ''))