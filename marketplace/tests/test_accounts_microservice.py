from django.conf import settings
from django.contrib.auth.models import User
from django.test import Client, TestCase

from accounts_microservice import app


class AccountsMicroserviceTest(TestCase):
    def setUp(self):
        self.flask = app.test_client()
        self.django = Client()

    def _use_django_session(self, user):
        self.django.force_login(user)
        session_cookie = self.django.cookies[settings.SESSION_COOKIE_NAME].value
        self.flask.set_cookie(settings.SESSION_COOKIE_NAME, session_cookie)

    def test_flask_login_creates_session_usable_by_django(self):
        User.objects.create_user(username="ana", password="clave-correcta")

        response = self.flask.post(
            "/api/v2/login/",
            json={"username": "ana", "password": "clave-correcta"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["username"], "ana")
        self.assertIn("csrf_token", response.json)
        session_cookie = self.flask.get_cookie(settings.SESSION_COOKIE_NAME)
        self.django.cookies[settings.SESSION_COOKIE_NAME] = session_cookie.value
        django_response = self.django.get("/cuentas/password_change/")
        self.assertEqual(django_response.status_code, 200)

    def test_django_login_accepts_local_nginx_origin_with_csrf_checks(self):
        User.objects.create_user(username="local-login", password="ClaveSegura-2026")
        client = Client(enforce_csrf_checks=True)
        login_page = client.get("/cuentas/login/")
        csrf_token = client.cookies["csrftoken"].value

        response = client.post(
            "/cuentas/login/",
            {
                "username": "local-login",
                "password": "ClaveSegura-2026",
                "csrfmiddlewaretoken": csrf_token,
            },
            HTTP_ORIGIN="http://127.0.0.1:8000",
        )

        self.assertEqual(login_page.status_code, 200)
        self.assertEqual(response.status_code, 302)

    def test_flask_accepts_existing_django_session_and_admin_api(self):
        admin = User.objects.create_user(
            username="admin-flask",
            password="clave-correcta",
            is_staff=True,
        )
        self._use_django_session(admin)

        response = self.flask.get("/api/v2/clientes/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, [])

    def test_non_staff_cannot_access_admin_api(self):
        user = User.objects.create_user(username="cliente-flask", password="clave")
        self._use_django_session(user)

        response = self.flask.get("/api/v2/clientes/")

        self.assertEqual(response.status_code, 403)

    def test_admin_api_requires_csrf_for_writes(self):
        admin = User.objects.create_user(
            username="admin-csrf",
            password="clave-correcta",
            is_staff=True,
        )
        self._use_django_session(admin)
        response = self.flask.post("/api/v2/clientes/", json={})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json["error"], "Token CSRF ausente o inválido.")

    def test_staff_without_superuser_cannot_manage_users(self):
        admin = User.objects.create_user(
            username="staff-not-superuser",
            password="clave-correcta",
            is_staff=True,
        )
        self._use_django_session(admin)

        response = self.flask.get("/api/v2/usuarios/")

        self.assertEqual(response.status_code, 403)

    def test_staff_can_create_user_with_hashed_password(self):
        admin = User.objects.create_user(
            username="admin-create-user",
            password="clave-correcta",
            is_staff=True,
            is_superuser=True,
        )
        self._use_django_session(admin)
        csrf = self.flask.get("/api/v2/csrf/").json["csrf_token"]

        response = self.flask.post(
            "/api/v2/usuarios/",
            json={
                "username": "managed-user",
                "email": "managed@example.com",
                "is_active": True,
                "is_staff": False,
                "is_superuser": False,
                "password": "Violet*Plane-82Quartz",
            },
            headers={"X-CSRFToken": csrf},
        )

        self.assertEqual(response.status_code, 201)
        user = User.objects.get(username="managed-user")
        self.assertTrue(user.check_password("Violet*Plane-82Quartz"))
        self.assertNotIn("password", response.json)

    def test_register_creates_user_and_django_session(self):
        response = self.flask.post(
            "/api/v2/registro/",
            json={
                "rol": "CLIENTE",
                "username": "nueva-cliente",
                "password": "clave-segura",
                "password_confirmacion": "clave-segura",
                "nombre": "Nueva Cliente",
                "correo": "nueva@example.com",
                "direccion": "Calle 1",
                "numero_tel": "3001234567",
            },
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(User.objects.filter(username="nueva-cliente").exists())
        self.assertEqual(response.json["username"], "nueva-cliente")
        self.assertIn("csrf_token", response.json)
        session_cookie = self.flask.get_cookie(settings.SESSION_COOKIE_NAME)
        self.django.cookies[settings.SESSION_COOKIE_NAME] = session_cookie.value
        self.assertEqual(self.django.get("/cuentas/password_change/").status_code, 200)

    def test_flask_admin_panel_uses_staff_session(self):
        admin = User.objects.create_user(
            username="admin-panel",
            password="clave-correcta",
            is_staff=True,
        )
        self._use_django_session(admin)

        response = self.flask.get("/admin/v2/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Administraci", response.data)

    def test_logout_clears_shared_django_session(self):
        User.objects.create_user(username="logout-user", password="clave")
        login = self.flask.post(
            "/api/v2/login/",
            json={"username": "logout-user", "password": "clave"},
        )
        csrf = login.json["csrf_token"]

        response = self.flask.post(
            "/api/v2/logout/",
            headers={"X-CSRFToken": csrf},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.flask.get("/api/v2/me/").status_code, 401)

    def test_legacy_django_admin_api_remains_available(self):
        admin = User.objects.create_user(
            username="admin-legacy",
            password="clave-correcta",
            is_staff=True,
        )
        self._use_django_session(admin)
        response = self.django.get("/api/clientes/")

        self.assertEqual(response.status_code, 200)
