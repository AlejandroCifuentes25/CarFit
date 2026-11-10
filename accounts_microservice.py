"""Flask API and administrative interface for account management.

The service shares Django's database-backed sessions and ORM so that
authentication established here is also valid in the remaining Django pages.
"""

import hmac
import os
from importlib import import_module
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "carfit.settings")

import django

django.setup()

from django.conf import settings
from django.contrib import auth
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import AnonymousUser, Group, Permission, User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models.deletion import ProtectedError
from django import forms
from django.forms import modelform_factory
from django.http import HttpRequest
from flask import Flask, abort, jsonify, make_response, redirect, render_template, request, url_for
from rest_framework.renderers import JSONRenderer
from rest_framework import serializers

from marketplace.api.serializers import (
    CarroSerializer,
    ClienteSerializer,
    LoginSerializer,
    VendedorSerializer,
)
from marketplace.domain.exceptions import ErrorDeDominio
from marketplace.forms import RegistroForm
from marketplace.models import (
    Carro,
    Cliente,
    DocumentoCarro,
    Inventario,
    Pago,
    Repuesto,
    Resena,
    TransaccionPago,
    Vendedor,
)
from marketplace.services import CatalogoComprasService, RegistroUsuarioService


app = Flask(
    __name__,
    template_folder=str(Path(__file__).parent / "marketplace/templates/flask_admin"),
)

SESSION_STORE = import_module(settings.SESSION_ENGINE).SessionStore
CSRF_SESSION_KEY = "_flask_csrf_token"


class AdminUserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)
    groups = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Group.objects.all(), required=False
    )
    user_permissions = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Permission.objects.all(),
        required=False,
    )

    class Meta:
        model = User
        fields = (
            "id", "username", "email", "first_name", "last_name", "is_active",
            "is_staff", "is_superuser", "groups", "user_permissions", "password",
        )
        read_only_fields = ("id",)

    def validate(self, attrs):
        if self.instance is None and not attrs.get("password"):
            raise serializers.ValidationError({"password": "Este campo es obligatorio al crear un usuario."})
        return attrs

    def validate_password(self, value):
        user = self.instance or User(username=self.initial_data.get("username", ""))
        try:
            validate_password(value, user)
        except ValidationError as error:
            raise serializers.ValidationError(error.messages) from error
        return value

    def create(self, validated_data):
        password = validated_data.pop("password")
        groups = validated_data.pop("groups", [])
        permissions = validated_data.pop("user_permissions", [])
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        user.groups.set(groups)
        user.user_permissions.set(permissions)
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        user = super().update(instance, validated_data)
        if password:
            user.set_password(password)
            user.save(update_fields=["password"])
        return user


class AdminGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ("id", "name", "permissions")
        read_only_fields = ("id",)


class AdminUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = (
            "username", "email", "first_name", "last_name",
            "is_active", "is_staff", "is_superuser",
        )


class AdminUserUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = (
            "username", "email", "first_name", "last_name",
            "is_active", "is_staff", "is_superuser", "groups", "user_permissions",
        )


API_RESOURCES = {
    "vendedores": (Vendedor, VendedorSerializer),
    "clientes": (Cliente, ClienteSerializer),
    "carros": (Carro, CarroSerializer),
    "usuarios": (User, AdminUserSerializer),
    "grupos": (Group, AdminGroupSerializer),
}

ADMIN_RESOURCES = {
    "vendedores": {
        "title": "Vendedores",
        "model": Vendedor,
        "columns": ("nombre", "correo", "numero_tel", "resena"),
        "form_fields": ("usuario", "nombre", "correo", "direccion", "numero_tel", "resena"),
    },
    "clientes": {
        "title": "Clientes",
        "model": Cliente,
        "columns": ("nombre", "correo", "numero_tel"),
        "form_fields": ("usuario", "nombre", "correo", "direccion", "numero_tel"),
    },
    "carros": {
        "title": "Carros",
        "model": Carro,
        "columns": ("placa", "marca", "modelo", "estado", "precio", "vendedor"),
        "form_fields": (
            "vendedor", "placa", "marca", "modelo", "estado", "color",
            "kilometraje", "descripcion", "precio", "puntaje",
        ),
    },
    "repuestos": {
        "title": "Repuestos",
        "model": Repuesto,
        "columns": ("tipo", "modelo_carro", "numero_serie", "estado", "precio"),
        "form_fields": (
            "vendedor", "tipo", "modelo_carro", "precio", "numero_serie", "estado",
        ),
    },
    "documentos": {
        "title": "Documentos de carros",
        "model": DocumentoCarro,
        "columns": ("carro", "tipo_documento", "fecha_expedicion", "fecha_vencimiento"),
        "form_fields": (
            "carro", "tipo_documento", "fecha_expedicion", "fecha_vencimiento",
        ),
    },
    "inventarios": {
        "title": "Inventarios",
        "model": Inventario,
        "columns": ("vendedor", "cantidad_repuesto", "cantidad_carro"),
        "form_fields": ("vendedor", "cantidad_repuesto", "cantidad_carro"),
    },
    "resenas": {
        "title": "Reseñas",
        "model": Resena,
        "columns": ("autor", "tipo", "carro"),
        "form_fields": ("contenido", "autor", "tipo", "carro"),
    },
    "pagos": {
        "title": "Pagos",
        "model": Pago,
        "columns": ("referencia", "cliente", "metodo_pago", "estado", "total", "fecha"),
        "form_fields": (
            "cliente", "carro", "repuesto", "cuotas", "metodo_pago", "estado", "mensaje",
        ),
        "allow_create": False,
    },
    "transacciones": {
        "title": "Transacciones de pago (solo lectura)",
        "model": TransaccionPago,
        "columns": ("pago", "operacion", "pasarela", "estado_resultante", "creado_en"),
        "form_fields": None,
    },
    "usuarios": {
        "title": "Usuarios",
        "model": User,
        "columns": ("username", "email", "is_staff", "is_active"),
        "form_fields": (
            "username", "email", "first_name", "last_name", "is_active",
            "is_staff", "is_superuser", "groups", "user_permissions",
        ),
    },
    "grupos": {
        "title": "Grupos",
        "model": Group,
        "columns": ("name",),
        "form_fields": ("name", "permissions"),
    },
}


def _session_request():
    session_key = request.cookies.get(settings.SESSION_COOKIE_NAME)
    session = SESSION_STORE(session_key) if session_key else SESSION_STORE()
    django_request = HttpRequest()
    django_request.method = request.method
    django_request.path = request.path
    django_request.META.update(
        {
            "HTTP_HOST": request.host,
            "REMOTE_ADDR": request.remote_addr or "",
            "wsgi.url_scheme": request.scheme,
        }
    )
    django_request.COOKIES = request.cookies.to_dict()
    django_request.session = session
    django_request.user = AnonymousUser()
    django_request.user = auth.get_user(django_request)
    return django_request


def _ensure_csrf_token(session):
    token = session.get(CSRF_SESSION_KEY)
    if token is None:
        import secrets

        token = secrets.token_urlsafe(32)
        session[CSRF_SESSION_KEY] = token
    return token


def _rotate_csrf_token(session):
    import secrets

    token = secrets.token_urlsafe(32)
    session[CSRF_SESSION_KEY] = token
    return token


def _csrf_is_valid(session):
    expected = session.get(CSRF_SESSION_KEY)
    supplied = request.headers.get("X-CSRFToken") or request.form.get("_csrf_token")
    return bool(expected and supplied and hmac.compare_digest(expected, supplied))


def _save_session_cookie(response, session):
    if session.session_key is None or session.modified:
        session.save()
    response.set_cookie(
        settings.SESSION_COOKIE_NAME,
        session.session_key,
        max_age=settings.SESSION_COOKIE_AGE,
        path=settings.SESSION_COOKIE_PATH,
        domain=settings.SESSION_COOKIE_DOMAIN,
        secure=settings.SESSION_COOKIE_SECURE,
        httponly=settings.SESSION_COOKIE_HTTPONLY,
        samesite=settings.SESSION_COOKIE_SAMESITE,
    )
    return response


def _set_csrf_cookie(response, session):
    if session.session_key is not None or session.modified:
        _save_session_cookie(response, session)
    return response


def _user_payload(user, csrf_token=None):
    result = {
        "id": user.pk,
        "username": user.get_username(),
        "is_staff": user.is_staff,
    }
    if csrf_token:
        result["csrf_token"] = csrf_token
    return result


def _json_response(data, status=200):
    rendered = JSONRenderer().render(data)
    return app.response_class(rendered, status=status, mimetype="application/json")


def _csrf_failure():
    return jsonify({"error": "Token CSRF ausente o inválido."}), 403


def _require_staff(resource=None):
    django_request = _session_request()
    user = django_request.user
    if not user.is_authenticated or not user.is_staff:
        return None, (jsonify({"detail": "Se requieren credenciales de administrador."}), 403)
    if resource in {"usuarios", "grupos"} and not user.is_superuser:
        return None, (jsonify({"detail": "Se requieren permisos de superusuario."}), 403)
    return django_request, None


@app.get("/health")
def health():
    return jsonify({"servicio": "cuentas", "estado": "ok"})


@app.get("/api/v2/sistema/")
def system_info():
    carros, repuestos = CatalogoComprasService().listar_disponibles(AnonymousUser())
    return jsonify(
        {
            "servicio": "CarFit Marketplace",
            "estado": "disponible",
            "version_api": "v2",
            "catalogo": {
                "carros_disponibles": carros.count(),
                "repuestos_disponibles": repuestos.count(),
            },
            "rutas": {
                "cuentas": "/api/v2/",
                "pagos": "/api/v2/pagos/",
                "publicaciones": "/publicaciones/v2/",
                "compras": "/compras/v2/catalogo/",
            },
        }
    )


@app.get("/api/v2/csrf/")
def csrf_token():
    django_request = _session_request()
    token = _ensure_csrf_token(django_request.session)
    response = jsonify({"csrf_token": token})
    return _set_csrf_cookie(response, django_request.session)


@app.post("/api/v2/login/")
def login():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "El cuerpo debe ser un objeto JSON."}), 400

    serializer = LoginSerializer(data=payload)
    if not serializer.is_valid():
        return _json_response(serializer.errors, 400)

    django_request = _session_request()
    user = auth.authenticate(django_request, **serializer.validated_data)
    if user is None:
        return jsonify({"error": "Usuario o contraseña incorrectos."}), 400

    auth.login(django_request, user)
    token = _rotate_csrf_token(django_request.session)
    response = jsonify(_user_payload(user, token))
    return _save_session_cookie(response, django_request.session)


@app.post("/api/v2/registro/")
def register():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "El cuerpo debe ser un objeto JSON."}), 400

    form = RegistroForm(data=payload)
    if not form.is_valid():
        return jsonify({"error": "Datos inválidos.", "detalles": form.errors.get_json_data()}), 400

    django_request = _session_request()
    try:
        user = RegistroUsuarioService().registrar(
            django_request,
            form.cleaned_data["rol"],
            form.cleaned_data,
        )
    except ValidationError as error:
        return jsonify({"error": "Datos inválidos.", "detalles": error.messages}), 400
    except ErrorDeDominio as error:
        return jsonify({"error": str(error)}), 400
    except IntegrityError:
        return jsonify({"error": "No se pudo crear la cuenta por una restricción de integridad."}), 400
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    token = _ensure_csrf_token(django_request.session)
    response = jsonify(_user_payload(user, token))
    response.status_code = 201
    return _save_session_cookie(response, django_request.session)


@app.post("/api/v2/logout/")
def logout():
    django_request = _session_request()
    if not _csrf_is_valid(django_request.session):
        return _csrf_failure()
    auth.logout(django_request)
    response = jsonify({"detail": "Sesión cerrada."})
    response.delete_cookie(
        settings.SESSION_COOKIE_NAME,
        path=settings.SESSION_COOKIE_PATH,
        domain=settings.SESSION_COOKIE_DOMAIN,
        secure=settings.SESSION_COOKIE_SECURE,
        httponly=settings.SESSION_COOKIE_HTTPONLY,
        samesite=settings.SESSION_COOKIE_SAMESITE,
    )
    return response


@app.get("/api/v2/me/")
def current_user():
    django_request = _session_request()
    user = django_request.user
    if not user.is_authenticated:
        return jsonify({"detail": "Autenticación requerida."}), 401

    result = _user_payload(user)
    cliente = getattr(user, "cliente", None)
    vendedor = getattr(user, "vendedor", None)
    result["cliente_id"] = cliente.pk if cliente else None
    result["vendedor_id"] = vendedor.pk if vendedor else None
    return jsonify(result)


def _admin_api_resource(resource, pk=None):
    django_request, error_response = _require_staff(resource)
    if error_response:
        return error_response
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        if not _csrf_is_valid(django_request.session):
            return _csrf_failure()

    model, serializer_class = API_RESOURCES[resource]
    if pk is None and request.method == "GET":
        serializer = serializer_class(model.objects.all(), many=True)
        return _json_response(serializer.data)
    if pk is None and request.method == "POST":
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "El cuerpo debe ser un objeto JSON."}), 400
        serializer = serializer_class(data=payload)
        if not serializer.is_valid():
            return _json_response(serializer.errors, 400)
        try:
            serializer.save()
        except IntegrityError:
            return jsonify({"error": "El registro viola una restricción de integridad."}), 400
        return _json_response(serializer.data, 201)

    try:
        instance = model.objects.get(pk=pk)
    except model.DoesNotExist:
        return jsonify({"detail": "No encontrado."}), 404

    if request.method == "GET":
        return _json_response(serializer_class(instance).data)
    if request.method in {"PUT", "PATCH"}:
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "El cuerpo debe ser un objeto JSON."}), 400
        serializer = serializer_class(
            instance,
            data=payload,
            partial=request.method == "PATCH",
        )
        if not serializer.is_valid():
            return _json_response(serializer.errors, 400)
        try:
            serializer.save()
        except IntegrityError:
            return jsonify({"error": "El registro viola una restricción de integridad."}), 400
        return _json_response(serializer.data)
    if request.method == "DELETE":
        try:
            instance.delete()
        except ProtectedError:
            return jsonify({"error": "El registro tiene dependencias que impiden eliminarlo."}), 409
        return "", 204
    return jsonify({"detail": "Método no permitido."}), 405


def _register_api_resource(resource):
    def collection():
        return _admin_api_resource(resource)

    def detail(pk):
        return _admin_api_resource(resource, pk)

    collection.__name__ = f"{resource}_collection"
    detail.__name__ = f"{resource}_detail"
    app.add_url_rule(
        f"/api/v2/{resource}/",
        view_func=collection,
        methods=["GET", "POST"],
    )
    app.add_url_rule(
        f"/api/v2/{resource}/<int:pk>/",
        view_func=detail,
        methods=["GET", "PUT", "PATCH", "DELETE"],
    )


for _resource_name in API_RESOURCES:
    _register_api_resource(_resource_name)


@app.get("/admin/v2/")
def admin_dashboard():
    django_request, response = _admin_access_or_redirect()
    if response:
        return response
    resources = [
        {"slug": slug, "title": config["title"]}
        for slug, config in ADMIN_RESOURCES.items()
        if slug not in {"usuarios", "grupos"} or django_request.user.is_superuser
    ]
    token = _ensure_csrf_token(django_request.session)
    response = make_response(render_template("dashboard.html", resources=resources, csrf_token=token))
    return _set_csrf_cookie(response, django_request.session)


def _admin_access_or_redirect(resource=None):
    django_request = _session_request()
    user = django_request.user
    if not user.is_authenticated:
        return None, redirect("/cuentas/login/?next=/admin/v2/")
    if not user.is_staff:
        return None, abort(403)
    if resource in {"usuarios", "grupos"} and not user.is_superuser:
        return None, abort(403)
    return django_request, None


@app.route("/admin/v2/<resource>/", methods=["GET"])
def admin_resource_list(resource):
    if resource not in ADMIN_RESOURCES:
        abort(404)
    django_request, response = _admin_access_or_redirect(resource)
    if response:
        return response
    config = ADMIN_RESOURCES[resource]
    config = {
        **config,
        "allow_create": config.get("allow_create", True),
        "allow_delete": config.get("allow_delete", True),
    }
    rows = config["model"].objects.all()[:200]
    token = _ensure_csrf_token(django_request.session)
    result = make_response(
        render_template(
            "resource_list.html",
            resource=resource,
            config=config,
            rows=rows,
            csrf_token=token,
        )
    )
    return _set_csrf_cookie(result, django_request.session)


@app.route("/admin/v2/<resource>/new/", defaults={"pk": None}, methods=["GET", "POST"])
@app.route("/admin/v2/<resource>/<int:pk>/edit/", methods=["GET", "POST"])
def admin_resource_form(resource, pk):
    if resource not in ADMIN_RESOURCES:
        abort(404)
    django_request, response = _admin_access_or_redirect(resource)
    if response:
        return response
    config = ADMIN_RESOURCES[resource]
    if pk is None and not config.get("allow_create", True):
        abort(405)
    form_fields = config["form_fields"]
    if form_fields is None:
        abort(405)
    model = config["model"]
    instance = None
    if pk is not None:
        try:
            instance = model.objects.get(pk=pk)
        except model.DoesNotExist:
            abort(404)

    if resource == "usuarios":
        form_class = AdminUserCreationForm if instance is None else AdminUserUpdateForm
    else:
        form_class = modelform_factory(model, fields=form_fields)
    form = form_class(
        data=request.form if request.method == "POST" else None,
        instance=instance,
    )
    token = _ensure_csrf_token(django_request.session)
    if request.method == "POST":
        if not _csrf_is_valid(django_request.session):
            return _csrf_failure()
        if form.is_valid():
            try:
                form.save()
            except IntegrityError:
                form.add_error(None, "El registro viola una restricción de integridad.")
            except ValidationError as error:
                form.add_error(None, error)
            else:
                return redirect(url_for("admin_resource_list", resource=resource))
    result = make_response(
        render_template(
            "resource_form.html",
            resource=resource,
            config=config,
            form=form,
            csrf_token=token,
        )
    )
    return _set_csrf_cookie(result, django_request.session)


@app.post("/admin/v2/<resource>/<int:pk>/delete/")
def admin_resource_delete(resource, pk):
    if resource not in ADMIN_RESOURCES:
        abort(404)
    django_request, response = _admin_access_or_redirect(resource)
    if response:
        return response
    if (
        not ADMIN_RESOURCES[resource]["form_fields"]
        or not ADMIN_RESOURCES[resource].get("allow_delete", True)
    ):
        abort(405)
    if not _csrf_is_valid(django_request.session):
        return _csrf_failure()
    try:
        instance = ADMIN_RESOURCES[resource]["model"].objects.get(pk=pk)
    except ADMIN_RESOURCES[resource]["model"].DoesNotExist:
        abort(404)
    try:
        instance.delete()
    except ProtectedError:
        abort(409)
    return redirect(url_for("admin_resource_list", resource=resource))
