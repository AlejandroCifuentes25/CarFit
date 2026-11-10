from django.conf import settings
from django.contrib.auth.models import User
from django.test import Client, TestCase

from marketplace.models import Carro, CarritoCompra, Cliente, Pago, Repuesto, Vendedor
from shopping_microservice import app

PREFIX = "/compras/v2"


class ComprasFlaskTest(TestCase):
    def setUp(self):
        self.flask = app.test_client()
        self.django = Client()
        self.user = User.objects.create_user(
            username="cliente-compras", password="clave-correcta"
        )
        self.cliente = Cliente.objects.create(
            usuario=self.user,
            nombre="Cliente",
            correo="cliente@carfit.co",
            direccion="Calle 1",
            numero_tel="3000000000",
        )
        seller_user = User.objects.create_user(
            username="vendedor-compras", password="clave-correcta"
        )
        self.vendedor = Vendedor.objects.create(
            usuario=seller_user,
            nombre="Vendedor",
            correo="vendedor@carfit.co",
            direccion="Calle 2",
            numero_tel="3000000001",
        )
        self.carro = Carro.objects.create(
            vendedor=self.vendedor,
            placa="ABC123",
            marca="Mazda",
            modelo="CX-30",
            color="Rojo",
            estado="USADO",
            kilometraje=15000,
            precio=85000000,
        )
        self.repuesto = Repuesto.objects.create(
            vendedor=self.vendedor,
            tipo="Filtro",
            modelo_carro="CX-30",
            numero_serie="REP-001",
            estado="NUEVO",
            precio=120000,
        )
        self._login(self.user, self.django, self.flask)

    def _login(self, user, django_client, flask_client):
        django_client.force_login(user)
        flask_client.set_cookie(
            settings.SESSION_COOKIE_NAME,
            django_client.cookies[settings.SESSION_COOKIE_NAME].value,
        )

    def _csrf(self, path=f"{PREFIX}/carrito/"):
        response = self.flask.get(path)
        html = response.get_data(as_text=True)
        marker = '<meta name="csrf-token" content="'
        return html.split(marker, 1)[1].split('"', 1)[0]

    def test_anonymous_customer_is_redirected_to_django_login(self):
        client = app.test_client()
        response = client.get(f"{PREFIX}/catalogo/")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].startswith("/cuentas/login/"))

    def test_catalog_lists_articles_and_uses_flask_cart_routes(self):
        response = self.flask.get(f"{PREFIX}/catalogo/")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Mazda CX-30", html)
        self.assertIn("Filtro", html)
        self.assertIn(f"{PREFIX}/api/carrito/agregar/carro/{self.carro.pk}/", html)

    def test_cart_mutations_require_csrf_and_are_customer_isolated(self):
        url = f"{PREFIX}/api/carrito/agregar/carro/{self.carro.pk}/"
        rejected = self.flask.post(url)
        self.assertEqual(rejected.status_code, 403)

        csrf = self._csrf()
        added = self.flask.post(url, headers={"X-CSRFToken": csrf})
        self.assertEqual(added.status_code, 200)
        self.assertEqual(added.json["articulo"]["titulo"], "Mazda CX-30")
        self.assertEqual(added.json["carrito"]["cantidad_producto"], 1)

        other_user = User.objects.create_user(
            username="otro-cliente-compras", password="clave-correcta"
        )
        Cliente.objects.create(
            usuario=other_user,
            nombre="Otro",
            correo="otro@carfit.co",
            direccion="Calle 3",
            numero_tel="3000000002",
        )
        other_django = Client()
        other_flask = app.test_client()
        self._login(other_user, other_django, other_flask)
        other_cart = other_flask.get(f"{PREFIX}/api/carrito/total/")
        self.assertEqual(other_cart.status_code, 200)
        self.assertEqual(other_cart.json["carrito"]["cantidad_producto"], 0)
        self.assertNotEqual(
            CarritoCompra.objects.get(cliente=self.cliente).pk,
            CarritoCompra.objects.get(cliente__usuario=other_user).pk,
        )
        other_token = other_flask.get(f"{PREFIX}/carrito/").get_data(as_text=True)
        other_csrf = other_token.split(
            '<meta name="csrf-token" content="', 1
        )[1].split('"', 1)[0]
        stolen_item = other_flask.post(
            url,
            headers={"X-CSRFToken": other_csrf},
        )
        self.assertEqual(stolen_item.status_code, 400)

    def test_customer_can_remove_and_clear_items(self):
        csrf = self._csrf()
        add_url = f"{PREFIX}/api/carrito/agregar/repuesto/{self.repuesto.pk}/"
        remove_url = f"{PREFIX}/api/carrito/quitar/repuesto/{self.repuesto.pk}/"
        self.assertEqual(
            self.flask.post(add_url, headers={"X-CSRFToken": csrf}).status_code,
            200,
        )
        removed = self.flask.post(remove_url, headers={"X-CSRFToken": csrf})
        self.assertEqual(removed.status_code, 200)
        self.assertEqual(removed.json["carrito"]["cantidad_producto"], 0)

        self.flask.post(add_url, headers={"X-CSRFToken": csrf})
        cleared = self.flask.post(
            f"{PREFIX}/api/carrito/vaciar/",
            headers={"X-CSRFToken": csrf},
        )
        self.assertEqual(cleared.status_code, 200)
        self.assertEqual(cleared.json["carrito"]["precio_total"], 0)

    def test_checkout_processes_payment_and_keeps_django_payment_page(self):
        csrf = self._csrf()
        self.flask.post(
            f"{PREFIX}/api/carrito/agregar/repuesto/{self.repuesto.pk}/",
            headers={"X-CSRFToken": csrf},
        )

        response = self.flask.post(
            f"{PREFIX}/carrito/",
            data={
                "_csrf_token": csrf,
                "metodo_pago": Pago.Metodo.TARJETA_CREDITO,
                "token_tarjeta": "tok_prueba_123",
                "cuotas": "1",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertRegex(response.headers["Location"], r"^/pagos/[^/]+/$")
        pago = Pago.objects.get(cliente=self.cliente, repuesto=self.repuesto)
        self.assertTrue(pago.referencia)
        self.assertEqual(CarritoCompra.objects.get(cliente=self.cliente).cantidad_producto, 0)

    def test_checkout_rejects_empty_cart_without_creating_a_payment(self):
        csrf = self._csrf()
        response = self.flask.post(
            f"{PREFIX}/carrito/",
            data={
                "_csrf_token": csrf,
                "metodo_pago": Pago.Metodo.TARJETA_CREDITO,
                "token_tarjeta": "tok_prueba_123",
                "cuotas": "1",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Tu carrito está vacío.", response.get_data(as_text=True))
        self.assertFalse(Pago.objects.exists())

    def test_legacy_django_catalog_and_cart_routes_remain_available(self):
        self.assertEqual(self.django.get("/comprar/").status_code, 200)
        self.assertEqual(self.django.get("/carrito/").status_code, 200)

    def test_django_navigation_opens_migrated_flask_catalog_and_cart(self):
        html = self.django.get("/comprar/").content.decode()
        self.assertIn(f'href="{PREFIX}/catalogo/"', html)
        self.assertIn(f'href="{PREFIX}/carrito/"', html)

    def test_unassigned_legacy_cart_items_are_not_claimed_by_a_customer(self):
        legacy_cart = CarritoCompra.objects.create()
        self.carro.carrito_compra = legacy_cart
        self.carro.save(update_fields=["carrito_compra"])

        summary = self.flask.get(f"{PREFIX}/api/carrito/total/").json["carrito"]

        self.assertEqual(summary["cantidad_producto"], 0)
        self.assertIsNone(legacy_cart.cliente_id)
        self.assertEqual(self.carro.carrito_compra_id, legacy_cart.pk)
        catalog = self.flask.get(f"{PREFIX}/catalogo/").get_data(as_text=True)
        self.assertNotIn("Mazda CX-30", catalog)
