"""Suite de pruebas W09 — Autenticación y Control de Acceso por Rol (RBAC).

Ejecutar con:
    python manage.py test tests.test_w09_auth_rbac --verbosity=2
"""
from decimal import Decimal

from django.contrib.auth.models import Group, Permission, User
from django.test import TestCase
from django.urls import reverse

from clientes.models    import Cliente
from productos.models   import Categoria, Producto


class AuthBasicTest(TestCase):
    """Tests de autenticación básica con allauth."""

    def test_login_page_http_200(self):
        r = self.client.get(reverse('account_login'))
        self.assertEqual(r.status_code, 200)

    def test_login_page_usa_template_fable5(self):
        r = self.client.get(reverse('account_login'))
        self.assertTemplateUsed(r, 'account/login.html')

    def test_login_correcto_redirige_a_productos(self):
        User.objects.create_user('testlogin', password='pass123')
        r = self.client.post(reverse('account_login'), {
            'login':    'testlogin',
            'password': 'pass123',
        })
        self.assertRedirects(r, '/productos/',
                             fetch_redirect_response=False)


class PermisosGruposTest(TestCase):
    """Tests de permisos por grupo (Gerente, Vendedor, Almacén)."""

    def setUp(self):
        self.cat  = Categoria.objects.create(nombre='Cat')
        self.prod = Producto.objects.create(
            nombre='Prod', precio=Decimal('100.00'),
            stock=5, categoria=self.cat
        )
        self.cli = Cliente.objects.create(nombre='C', correo='c@t.com')

    def _crear_usuario(self, username, grupo_name):
        user     = User.objects.create_user(username, password='pass')
        grupo, _ = Group.objects.get_or_create(name=grupo_name)
        if grupo_name == 'Gerente':
            perms = Permission.objects.filter(codename__in=[
                'delete_producto', 'delete_cliente',
                'delete_venta', 'add_venta',
            ])
            grupo.permissions.set(perms)
        elif grupo_name == 'Vendedor':
            perms = Permission.objects.filter(codename__in=[
                'add_venta', 'view_producto', 'view_cliente',
            ])
            grupo.permissions.set(perms)
        user.groups.add(grupo)
        return user

    def test_eliminar_producto_sin_auth_redirige_a_login(self):
        r = self.client.get(reverse('productos:eliminar', args=[self.prod.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertIn('/accounts/login/', r['Location'])

    def test_vendedor_no_puede_eliminar_producto_403(self):
        vendedor = self._crear_usuario('vendedor', 'Vendedor')
        self.client.force_login(vendedor)
        r = self.client.post(reverse('productos:eliminar', args=[self.prod.pk]))
        self.assertEqual(r.status_code, 403)

    def test_vendedor_puede_ver_lista_productos(self):
        vendedor = self._crear_usuario('vend2', 'Vendedor')
        self.client.force_login(vendedor)
        r = self.client.get(reverse('productos:lista'))
        self.assertEqual(r.status_code, 200)

    def test_vendedor_puede_crear_venta(self):
        vendedor = self._crear_usuario('vend3', 'Vendedor')
        self.client.force_login(vendedor)
        r = self.client.get(reverse('ventas:crear'))
        self.assertEqual(r.status_code, 200)

    def test_gerente_puede_eliminar_producto(self):
        gerente = self._crear_usuario('gerente', 'Gerente')
        self.client.force_login(gerente)
        pk = self.prod.pk
        r  = self.client.post(reverse('productos:eliminar', args=[pk]))
        self.assertEqual(r.status_code, 302)
        self.assertFalse(Producto.objects.filter(pk=pk).exists())

    def test_gerente_puede_eliminar_cliente(self):
        gerente = self._crear_usuario('gerente2', 'Gerente')
        self.client.force_login(gerente)
        r = self.client.post(reverse('clientes:eliminar', args=[self.cli.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertFalse(Cliente.objects.filter(pk=self.cli.pk).exists())

    def test_management_command_crea_grupos(self):
        from io import StringIO
        from django.core.management import call_command
        call_command('crear_grupos', stdout=StringIO())
        for nombre in ['Gerente', 'Vendedor', 'Almacén']:
            self.assertTrue(Group.objects.filter(name=nombre).exists())