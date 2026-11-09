from django.conf import settings
from django.contrib.auth.models import User
from django.test import Client, TestCase

import publications_microservice
from marketplace.domain.exceptions import ErrorDeDominio
from marketplace.models import Carro, Cliente, Repuesto, Vendedor
from publications_microservice import app

P = "/publicaciones/v2"


def _form_carro(**extra):
    datos = {
        "placa": "ABC123", "marca": "Mazda", "modelo": "CX-30", "color": "Rojo",
        "estado": "USADO", "kilometraje": "15000", "precio": "85000000",
        "descripcion": "ok",
        "soat_expedicion": "2026-01-10", "soat_vencimiento": "2027-01-10",
        "tecnomecanica_expedicion": "2026-02-01", "tecnomecanica_vencimiento": "2027-02-01",
    }
    datos.update(extra)
    return datos


class PublicacionesFlaskTest(TestCase):
    def setUp(self):
        self.flask = app.test_client()
        self.django = Client()
        self.user = User.objects.create_user("vend", password="clave-larga-123")
        self.vendedor = Vendedor.objects.create(
            usuario=self.user, nombre="V", correo="v@x.co", direccion="d", numero_tel="1")

    def _login(self, user=None):
        self.django.force_login(user or self.user)
        self.flask.set_cookie(
            settings.SESSION_COOKIE_NAME,
            self.django.cookies[settings.SESSION_COOKIE_NAME].value,
        )

    def _csrf(self, path=f"{P}/nuevo/"):
        html = self.flask.get(path).get_data(as_text=True)
        marker = 'name="_csrf_token" value="'
        return html.split(marker)[1].split('"')[0]

    def _post(self, path, data=None, csrf=True):
        data = dict(data or {})
        if csrf:
            data["_csrf_token"] = self._csrf()
        return self.flask.post(path, data=data)

    def test_anonymous_redirects_to_django_login(self):
        r = self.flask.get(f"{P}/nuevo/")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["Location"].startswith("/cuentas/login/?next="))

    def test_client_without_seller_profile_gets_403(self):
        cliente = User.objects.create_user("cli", password="clave-larga-123")
        Cliente.objects.create(usuario=cliente, nombre="C", correo="c@x.co", direccion="d", numero_tel="1")
        self._login(cliente)
        self.assertEqual(self.flask.get(f"{P}/nuevo/").status_code, 403)

    def test_seller_sees_form_and_shares_django_session(self):
        self._login()
        r = self.flask.get(f"{P}/nuevo/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Publicar vehículo", r.get_data(as_text=True))

    def test_post_without_csrf_is_rejected(self):
        self._login()
        r = self._post(f"{P}/nuevo/repuesto/", {"tipo": "Freno"}, csrf=False)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(Repuesto.objects.count(), 0)

    def test_creates_car_and_redirects(self):
        self._login()
        r = self._post(f"{P}/nuevo/", _form_carro())
        self.assertEqual(r.status_code, 302, r.get_data(as_text=True)[:500])
        self.assertEqual(r.headers["Location"], f"{P}/publicado/")
        self.assertEqual(Carro.objects.get().vendedor, self.vendedor)

    def test_invalid_car_rerenders_with_errors(self):
        self._login()
        r = self._post(f"{P}/nuevo/", _form_carro(kilometraje="-1"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Carro.objects.count(), 0)

    def test_domain_error_becomes_form_error(self):
        self._login()

        class Falso:
            def crear_articulo(self, *a):
                raise ErrorDeDominio("Placa duplicada")

        original = publications_microservice._service
        publications_microservice._service = lambda: Falso()
        try:
            r = self._post(f"{P}/nuevo/", _form_carro())
        finally:
            publications_microservice._service = original
        self.assertEqual(r.status_code, 200)
        self.assertIn("Placa duplicada", r.get_data(as_text=True))

    def test_creates_spare_part(self):
        self._login()
        r = self._post(f"{P}/nuevo/repuesto/", {
            "tipo": "Freno", "modelo_carro": "Mazda 3", "numero_serie": "S1",
            "estado": "NUEVO", "precio": "1000"})
        self.assertEqual(r.status_code, 302, r.get_data(as_text=True)[:500])
        self.assertEqual(Repuesto.objects.get().numero_serie, "S1")

    def test_listing_edit_and_delete_are_scoped_to_owner(self):
        self._login()
        propio = Repuesto.objects.create(vendedor=self.vendedor, tipo="A", modelo_carro="M",
                                         numero_serie="N1", estado="NUEVO", precio=10)
        otro_user = User.objects.create_user("otro", password="clave-larga-123")
        otro_v = Vendedor.objects.create(usuario=otro_user, nombre="O", correo="o@x.co",
                                         direccion="d", numero_tel="2")
        ajeno = Repuesto.objects.create(vendedor=otro_v, tipo="B", modelo_carro="M",
                                        numero_serie="N2", estado="NUEVO", precio=10)
        listado = self.flask.get(f"{P}/mis-publicaciones/").get_data(as_text=True)
        self.assertIn("A - M", listado)
        self.assertNotIn("B - M", listado)
        self.assertEqual(self.flask.get(f"{P}/editar/repuesto/{ajeno.pk}/").status_code, 404)

        r = self._post(f"{P}/editar/repuesto/{propio.pk}/", {
            "tipo": "A2", "modelo_carro": "M", "numero_serie": "N1",
            "estado": "NUEVO", "precio": "99"})
        self.assertEqual(r.status_code, 302)
        propio.refresh_from_db()
        self.assertEqual((propio.tipo, propio.precio), ("A2", 99))

        self.assertEqual(self._post(f"{P}/eliminar/repuesto/{ajeno.pk}/").status_code, 404)
        r = self._post(f"{P}/eliminar/repuesto/{propio.pk}/")
        self.assertEqual(r.status_code, 302)
        self.assertFalse(Repuesto.objects.filter(pk=propio.pk).exists())

    def test_legacy_django_routes_still_available(self):
        self.django.force_login(self.user)
        self.assertEqual(self.django.get("/articulos/nuevo/").status_code, 200)
        self.assertEqual(self.django.get("/mis-publicaciones/").status_code, 200)
