"""Pruebas de la capa de interfaz.

Verifican que la vista sea realmente delgada: delega en el servicio y
traduce los errores de dominio a errores de formulario, nada más.
"""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from ..domain.exceptions import DocumentacionInvalidaError
from ..models import Vendedor
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
