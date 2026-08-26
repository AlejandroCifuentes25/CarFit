"""Pruebas de la capa de interfaz.

Verifican que la vista sea realmente delgada: delega en el servicio y
traduce los errores de dominio a errores de formulario, nada más.
"""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from ..domain.exceptions import DocumentacionInvalidaError
from ..models import Cliente, Vendedor
from ..views import CrearArticuloView
from .test_services import DATOS_VALIDOS


def datos_del_formulario():
    return {
        clave: valor
        for clave, valor in DATOS_VALIDOS.items()
        if valor is not None and not clave.endswith("_archivo")
    }


class ServicioFalso:
    def __init__(self, error=None):
        self.error = error
        self.llamadas = []

    def crear_articulo(self, vendedor, datos):
        self.llamadas.append((vendedor, datos))
        if self.error:
            raise self.error
        return object()


class CrearArticuloViewTest(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_user("alejandro", password="clave-de-prueba")
        self.vendedor = Vendedor.objects.create(
            usuario=self.usuario,
            nombre="Alejandro Cifuentes",
            correo="alejandro@carfit.co",
            direccion="Cra 43A #1-50",
            numero_tel="3001234567",
        )
        self.url = reverse("marketplace:crear_articulo")

    def test_exige_autenticacion(self):
        respuesta = self.client.get(self.url)

        self.assertEqual(respuesta.status_code, 302)
        self.assertIn("/cuentas/login/", respuesta["Location"])

    def test_muestra_el_formulario_al_vendedor_autenticado(self):
        self.client.force_login(self.usuario)

        respuesta = self.client.get(self.url)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Publicar vehículo")

    def test_rechaza_a_un_cliente_autenticado(self):
        usuario_cliente = User.objects.create_user("cliente", password="clave")
        Cliente.objects.create(
            usuario=usuario_cliente,
            nombre="Cliente de prueba",
            correo="cliente@carfit.co",
            direccion="Calle 1",
            numero_tel="3000000000",
        )
        self.client.force_login(usuario_cliente)

        respuesta = self.client.get(self.url)

        self.assertEqual(respuesta.status_code, 403)
        self.assertContains(respuesta, "perfil de vendedor", status_code=403)

    def test_delega_en_el_servicio_y_redirige(self):
        self.client.force_login(self.usuario)

        respuesta = self.client.post(self.url, datos_del_formulario())

        self.assertRedirects(respuesta, reverse("marketplace:articulo_publicado"))

    def test_traduce_el_error_de_dominio_a_error_de_formulario(self):
        servicio = ServicioFalso(error=DocumentacionInvalidaError(["SOAT vencido."]))
        vista = CrearArticuloView.as_view(service_factory=lambda: servicio)
        peticion = self._peticion_post(datos_del_formulario())

        respuesta = vista(peticion)

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("SOAT vencido.", respuesta.context_data["form"].non_field_errors())

    def test_inyecta_el_servicio_recibido_por_as_view(self):
        servicio = ServicioFalso()
        vista = CrearArticuloView.as_view(service_factory=lambda: servicio)

        vista(self._peticion_post(datos_del_formulario()))

        self.assertEqual(len(servicio.llamadas), 1)
        self.assertEqual(servicio.llamadas[0][0], self.vendedor)

    def _peticion_post(self, datos):
        from django.test import RequestFactory

        peticion = RequestFactory().post(self.url, datos)
        peticion.user = self.usuario
        return peticion


class IndexViewTest(TestCase):
    def test_muestra_iniciar_sesion_y_registrarse_a_un_anonimo(self):
        respuesta = self.client.get(reverse("marketplace:index"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Iniciar sesión")
        self.assertContains(respuesta, "Registrarse")

    def test_muestra_publicar_a_un_vendedor_autenticado(self):
        usuario = User.objects.create_user("alejandro", password="clave")
        Vendedor.objects.create(
            usuario=usuario,
            nombre="Alejandro",
            correo="alejandro@carfit.co",
            direccion="Calle 1",
            numero_tel="3000000000",
        )
        self.client.force_login(usuario)

        respuesta = self.client.get(reverse("marketplace:index"))

        self.assertContains(respuesta, "Publicar un vehículo")
        self.assertNotContains(respuesta, "Registrarse")

    def test_no_muestra_publicar_a_un_cliente_autenticado(self):
        usuario = User.objects.create_user("cliente", password="clave")
        Cliente.objects.create(
            usuario=usuario,
            nombre="Cliente",
            correo="cliente@carfit.co",
            direccion="Calle 1",
            numero_tel="3000000000",
        )
        self.client.force_login(usuario)

        respuesta = self.client.get(reverse("marketplace:index"))

        self.assertNotContains(respuesta, "Publicar un vehículo")


class RegistroViewTest(TestCase):
    def setUp(self):
        self.url = reverse("marketplace:registro")
        self.datos = {
            "rol": "CLIENTE",
            "username": "sofia",
            "password": "clave-segura",
            "password_confirmacion": "clave-segura",
            "nombre": "Sofía Restrepo",
            "correo": "sofia@carfit.co",
            "direccion": "Calle 10 #5-20",
            "numero_tel": "3011234567",
        }

    def test_muestra_el_formulario(self):
        respuesta = self.client.get(self.url)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Crear una cuenta")

    def test_registra_e_inicia_sesion(self):
        respuesta = self.client.post(self.url, self.datos)

        self.assertRedirects(respuesta, reverse("marketplace:catalogo_compras"))
        self.assertTrue(Cliente.objects.filter(usuario__username="sofia").exists())

    def test_rechaza_contrasenas_que_no_coinciden(self):
        self.datos["password_confirmacion"] = "otra-clave"

        respuesta = self.client.post(self.url, self.datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn(
            "Las contraseñas no coinciden.",
            respuesta.context_data["form"].errors["password_confirmacion"],
        )

    def test_rechaza_nombre_de_usuario_repetido(self):
        User.objects.create_user("sofia", password="lo-que-sea")

        respuesta = self.client.post(self.url, self.datos)

        self.assertEqual(respuesta.status_code, 200)
        self.assertIn(
            "ya está en uso", respuesta.context_data["form"].non_field_errors()[0]
        )
