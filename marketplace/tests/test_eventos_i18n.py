from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import Client, TestCase, override_settings
from django.utils import translation

from marketplace.models import Cliente, EventoNotificacion, Vendedor
from marketplace.services import PublicacionArticuloService
from marketplace.tasks import enviar_notificacion
from shopping_microservice import app as compras_app


class IdiomaTest(TestCase):
    def test_selector_conserva_destino_y_traduce_la_interfaz_y_javascript(self):
        client = Client(enforce_csrf_checks=True)
        destino = "/registro/?rol=VENDEDOR"
        client.get(destino)
        csrf = client.cookies[settings.CSRF_COOKIE_NAME].value
        response = client.post(
            "/i18n/setlang/",
            {"language": "en", "next": destino, "csrfmiddlewaretoken": csrf},
        )
        self.assertRedirects(response, destino, fetch_redirect_response=False)
        registro = client.get(destino)
        self.assertContains(registro, 'lang="en"')
        self.assertContains(registro, "Create an account")
        self.assertContains(registro, "Confirm password")
        self.assertContains(client.get("/i18n/carfit.js"), "Item added to your cart.")

    def test_flask_usa_la_misma_cookie_y_catalogo(self):
        usuario = get_user_model().objects.create_user(username="cliente-idioma")
        Cliente.objects.create(usuario=usuario, nombre="Cliente", correo="test@example.invalid")
        self.client.force_login(usuario)
        flask = compras_app.test_client()
        flask.set_cookie(settings.SESSION_COOKIE_NAME, self.client.cookies[settings.SESSION_COOKIE_NAME].value)
        flask.set_cookie(settings.LANGUAGE_COOKIE_NAME, "en")
        response = flask.get("/compras/v2/catalogo/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Language"], "en")
        self.assertIn("Browse catalog", response.get_data(as_text=True))
        self.assertIn("Clear filters", response.get_data(as_text=True))


@override_settings(CELERY_BROKER_URL="redis://127.0.0.1:6379/0")
class EventosTest(TestCase):
    def setUp(self):
        usuario = get_user_model().objects.create_user(username="vendedor-evento")
        self.vendedor = Vendedor.objects.create(
            usuario=usuario, nombre="Vendedor", correo="test@example.invalid",
        )

    def publicar(self):
        return PublicacionArticuloService().crear_repuesto(self.vendedor, {
            "tipo": "Filtro", "modelo_carro": "Mazda 3", "numero_serie": "EVENTO-TEST",
            "estado": "NUEVO", "precio": 60000,
        })

    @patch("marketplace.infra.eventos.publicar_evento")
    def test_publica_despues_de_confirmar_y_procesa_una_vez(self, publicar_evento):
        with self.captureOnCommitCallbacks(execute=True):
            with translation.override("en"):
                articulo = self.publicar()
            publicar_evento.assert_not_called()

        evento = EventoNotificacion.objects.get()
        self.assertEqual(evento.objeto_id, articulo.pk)
        self.assertEqual(evento.idioma, "en")
        publicar_evento.assert_called_once_with(evento.pk)

        idiomas = []
        with patch("marketplace.tasks.NotificadorFactory.crear") as factory:
            envio = factory.return_value.notificar_publicacion
            envio.side_effect = lambda item: idiomas.append(translation.get_language())
            enviar_notificacion.run(evento.pk)
            enviar_notificacion.run(evento.pk)
            envio.assert_called_once_with(articulo)

        self.assertEqual(idiomas, ["en"])
        evento.refresh_from_db()
        self.assertIsNotNone(evento.enviado_en)

    @patch("marketplace.infra.eventos.publicar_evento")
    def test_rollback_descarta_evento_y_publicacion(self, publicar_evento):
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(RuntimeError), transaction.atomic():
                self.publicar()
                raise RuntimeError("rollback")
        publicar_evento.assert_not_called()
        self.assertFalse(EventoNotificacion.objects.exists())
        self.assertFalse(self.vendedor.repuestos.exists())
