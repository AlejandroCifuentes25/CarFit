from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from ..models import Carro, Cliente, Pago, Repuesto, Vendedor


class CarritoFrontendTest(TestCase):
    def setUp(self):
        self.usuario_cliente = User.objects.create_user("comprador", password="clave")
        self.cliente = Cliente.objects.create(
            usuario=self.usuario_cliente,
            nombre="Comprador",
            correo="comprador@carfit.co",
            direccion="Calle 1",
            numero_tel="3000000000",
        )
        self.usuario_vendedor = User.objects.create_user("vendedor", password="clave")
        self.vendedor = Vendedor.objects.create(
            usuario=self.usuario_vendedor,
            nombre="Vendedor",
            correo="vendedor@carfit.co",
            direccion="Cra 10 #10-10",
            numero_tel="3001111111",
        )
        self.carro = Carro.objects.create(
            vendedor=self.vendedor,
            placa="ABC123",
            marca="Mazda",
            modelo="CX-30",
            estado="USADO",
            color="Rojo",
            kilometraje=15_000,
            precio=85_000_000,
        )
        self.repuesto = Repuesto.objects.create(
            vendedor=self.vendedor,
            tipo="Filtro de aceite",
            modelo_carro="CX-30",
            precio=120_000,
            numero_serie="REP-001",
            estado="NUEVO",
        )

    def test_catalogo_muestra_acciones_de_carrito_en_lugar_de_pago_directo(self):
        self.client.force_login(self.usuario_cliente)

        respuesta = self.client.get(reverse("marketplace:catalogo_compras"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Agregar al carrito")
        self.assertNotContains(respuesta, "Pagar")

    def test_carrito_muestra_el_total_y_permita_comprar_todo_el_carrito(self):
        self.client.force_login(self.usuario_cliente)

        self.client.post(
            reverse(
                "marketplace:agregar_articulo_carrito",
                kwargs={"tipo_articulo": "carro", "articulo_id": self.carro.pk},
            ),
            {},
        )
        self.client.post(
            reverse(
                "marketplace:agregar_articulo_carrito",
                kwargs={"tipo_articulo": "repuesto", "articulo_id": self.repuesto.pk},
            ),
            {},
        )

        respuesta = self.client.get(reverse("marketplace:carrito"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Carrito de compras")
        self.assertContains(respuesta, "Confirmar compra del carrito")
        self.assertContains(respuesta, "Mazda CX-30")
        self.assertContains(respuesta, "$85.000.000")

    def test_comprar_el_carrito_procesa_todos_los_articulos(self):
        self.client.force_login(self.usuario_cliente)

        self.client.post(
            reverse(
                "marketplace:agregar_articulo_carrito",
                kwargs={"tipo_articulo": "carro", "articulo_id": self.carro.pk},
            ),
            {},
        )
        self.client.post(
            reverse(
                "marketplace:agregar_articulo_carrito",
                kwargs={"tipo_articulo": "repuesto", "articulo_id": self.repuesto.pk},
            ),
            {},
        )

        respuesta = self.client.post(
            reverse("marketplace:carrito"),
            {
                "metodo_pago": Pago.Metodo.TARJETA_CREDITO,
                "token_tarjeta": "tok_prueba_123",
                "cuotas": 1,
            },
        )

        pagos = Pago.objects.all()
        self.assertEqual(pagos.count(), 2)
        self.assertRedirects(respuesta, respuesta.url)

    def test_el_total_del_carrito_se_puede_consultar_como_resumen(self):
        self.client.force_login(self.usuario_cliente)

        self.client.post(
            reverse(
                "marketplace:agregar_articulo_carrito",
                kwargs={"tipo_articulo": "carro", "articulo_id": self.carro.pk},
            ),
            {},
        )

        respuesta = self.client.post(reverse("marketplace:calcular_total_carrito"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()["precio_total"], 85_000_000)