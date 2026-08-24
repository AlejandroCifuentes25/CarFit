"""Pruebas de la capa de presentación de la API (DRF).

Verifican los códigos de estado HTTP y el control de acceso: el CRUD
administrativo exige `is_staff` y el login delega en `AutenticacionService`.
"""

from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from ..models import Carro, Cliente, Vendedor


class LoginAPIViewTest(APITestCase):
    def setUp(self):
        self.usuario = User.objects.create_user("alejandro", password="clave-correcta")
        self.url = reverse("marketplace_api:login")

    def test_credenciales_correctas_inicia_sesion(self):
        respuesta = self.client.post(
            self.url, {"username": "alejandro", "password": "clave-correcta"}
        )

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(respuesta.data["username"], "alejandro")

    def test_credenciales_incorrectas_devuelve_400(self):
        respuesta = self.client.post(
            self.url, {"username": "alejandro", "password": "clave-mala"}
        )

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_datos_incompletos_devuelve_400(self):
        respuesta = self.client.post(self.url, {"username": "alejandro"})

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)


class AdminCRUDPermisosTest(APITestCase):
    """Un mismo caso (Vendedor) alcanza para probar el control de acceso;
    Cliente y Carro siguen exactamente el mismo patrón de permisos."""

    def setUp(self):
        self.url = reverse("marketplace_api:vendedores_lista")

    def test_anonimo_no_puede_listar(self):
        respuesta = self.client.get(self.url)

        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)

    def test_usuario_no_staff_no_puede_listar(self):
        usuario = User.objects.create_user("cliente1", password="clave")
        self.client.force_login(usuario)

        respuesta = self.client.get(self.url)

        self.assertEqual(respuesta.status_code, status.HTTP_403_FORBIDDEN)

    def test_administrador_puede_listar(self):
        admin = User.objects.create_user("admin1", password="clave", is_staff=True)
        self.client.force_login(admin)

        respuesta = self.client.get(self.url)

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)


class VendedorAdminAPITest(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin2", password="clave", is_staff=True)
        self.client.force_login(self.admin)
        self.usuario_vendedor = User.objects.create_user("vendedor1", password="clave")

    def test_crea_vendedor(self):
        respuesta = self.client.post(
            reverse("marketplace_api:vendedores_lista"),
            {
                "usuario": self.usuario_vendedor.id,
                "nombre": "Alejandro Cifuentes",
                "correo": "alejandro@carfit.co",
                "direccion": "Cra 43A #1-50",
                "numero_tel": "3001234567",
            },
        )

        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Vendedor.objects.filter(correo="alejandro@carfit.co").exists())

    def test_actualiza_vendedor(self):
        vendedor = Vendedor.objects.create(
            usuario=self.usuario_vendedor,
            nombre="Alejandro Cifuentes",
            correo="alejandro@carfit.co",
            direccion="Cra 43A #1-50",
            numero_tel="3001234567",
        )

        respuesta = self.client.patch(
            reverse("marketplace_api:vendedor_detalle", args=[vendedor.id]),
            {"numero_tel": "3009999999"},
        )

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        vendedor.refresh_from_db()
        self.assertEqual(vendedor.numero_tel, "3009999999")

    def test_elimina_vendedor(self):
        vendedor = Vendedor.objects.create(
            usuario=self.usuario_vendedor,
            nombre="Alejandro Cifuentes",
            correo="alejandro@carfit.co",
            direccion="Cra 43A #1-50",
            numero_tel="3001234567",
        )

        respuesta = self.client.delete(
            reverse("marketplace_api:vendedor_detalle", args=[vendedor.id])
        )

        self.assertEqual(respuesta.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Vendedor.objects.filter(id=vendedor.id).exists())

    def test_detalle_inexistente_devuelve_404(self):
        respuesta = self.client.get(
            reverse("marketplace_api:vendedor_detalle", args=[999999])
        )

        self.assertEqual(respuesta.status_code, status.HTTP_404_NOT_FOUND)


class ClienteAdminAPITest(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin3", password="clave", is_staff=True)
        self.client.force_login(self.admin)
        self.usuario_cliente = User.objects.create_user("cliente2", password="clave")

    def test_crea_cliente(self):
        respuesta = self.client.post(
            reverse("marketplace_api:clientes_lista"),
            {
                "usuario": self.usuario_cliente.id,
                "nombre": "Sofía Restrepo",
                "correo": "sofia@carfit.co",
                "direccion": "Calle 10 #5-20",
                "numero_tel": "3011234567",
            },
        )

        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Cliente.objects.filter(correo="sofia@carfit.co").exists())


class CarroAdminAPITest(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin4", password="clave", is_staff=True)
        self.client.force_login(self.admin)
        usuario_vendedor = User.objects.create_user("vendedor2", password="clave")
        self.vendedor = Vendedor.objects.create(
            usuario=usuario_vendedor,
            nombre="Alejandro Cifuentes",
            correo="alejandro@carfit.co",
            direccion="Cra 43A #1-50",
            numero_tel="3001234567",
        )

    def _datos_validos(self, **overrides):
        datos = {
            "vendedor": self.vendedor.id,
            "placa": "ABC123",
            "marca": "Mazda",
            "modelo": "CX-30",
            "estado": Carro.Estado.USADO,
            "color": "Rojo",
            "kilometraje": 15000,
            "descripcion": "Excelente estado",
            "precio": 85000000,
        }
        datos.update(overrides)
        return datos

    def test_crea_carro(self):
        respuesta = self.client.post(
            reverse("marketplace_api:carros_lista"), self._datos_validos()
        )

        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Carro.objects.filter(placa="ABC123").exists())

    def test_rechaza_carro_nuevo_con_kilometraje_alto(self):
        respuesta = self.client.post(
            reverse("marketplace_api:carros_lista"),
            self._datos_validos(estado=Carro.Estado.NUEVO, kilometraje=50000),
        )

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_placa_duplicada_devuelve_400(self):
        self.client.post(reverse("marketplace_api:carros_lista"), self._datos_validos())

        respuesta = self.client.post(
            reverse("marketplace_api:carros_lista"), self._datos_validos()
        )

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
