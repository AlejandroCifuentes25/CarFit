"""Flask web flows for publishing and managing cars and spare parts.

Strangler-pattern slice: Nginx routes ``/publicaciones/v2/`` here while the
original Django pages (``/articulos/nuevo/``, ``/mis-publicaciones/`` ...) stay
untouched as legacy/rollback.

Like the accounts service, this app shares Django's database-backed sessions,
ORM, forms and service layer, so business rules live in one place
(``marketplace.services.PublicacionArticuloService``). CSRF protection uses the
same session-bound token helpers as ``accounts_microservice``.
"""

import os
from functools import wraps
from pathlib import Path
from urllib.parse import quote

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "carfit.settings")

import django

django.setup()

from django import forms
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.datastructures import MultiValueDict
from flask import Flask, abort, jsonify, redirect, render_template, request

# Shared session/CSRF behaviour: identical to the Flask accounts service.
from accounts_microservice import (
    _csrf_is_valid,
    _ensure_csrf_token,
    _save_session_cookie,
    _session_request,
)
from marketplace.domain.exceptions import ErrorDeDominio
from marketplace.forms import CrearArticuloForm
from marketplace.models import Carro, Repuesto
from marketplace.services import PublicacionArticuloService

PREFIX = "/publicaciones/v2"
LOGIN_URL = "/cuentas/login/"

app = Flask(
    __name__,
    template_folder=str(Path(__file__).parent / "marketplace/templates/flask_publicaciones"),
)

TIPOS = {"carro": Carro, "repuesto": Repuesto}


class RepuestoForm(forms.ModelForm):
    class Meta:
        model = Repuesto
        fields = ["tipo", "modelo_carro", "numero_serie", "estado", "precio"]


class CarroEdicionForm(forms.ModelForm):
    class Meta:
        model = Carro
        fields = ["placa", "marca", "modelo", "color", "estado", "kilometraje", "precio", "descripcion"]


def _service():
    # Resolved at call time so tests can patch the module attribute.
    return PublicacionArticuloService()


def _post_data():
    return MultiValueDict(request.form.to_dict(flat=False))


def _post_files():
    files = MultiValueDict()
    for name, storage in request.files.items(multi=True):
        if not storage.filename:
            continue
        files.appendlist(
            name,
            SimpleUploadedFile(storage.filename, storage.read(), storage.mimetype),
        )
    return files


def _render(dj_request, template, status=200, **context):
    context.setdefault("csrf_token", _ensure_csrf_token(dj_request.session))
    context.setdefault("user", dj_request.user)
    context.setdefault("prefix", PREFIX)
    response = app.response_class(render_template(template, **context), status=status)
    return _save_session_cookie(response, dj_request.session)


def _redirect(dj_request, location):
    return _save_session_cookie(redirect(location), dj_request.session)


def _login_redirect():
    return redirect(f"{LOGIN_URL}?next={quote(request.path)}")


def vendor_required(view):
    """Login + seller profile + CSRF on writes, mirroring the Django mixins."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        dj_request = _session_request()
        user = dj_request.user
        if not user.is_authenticated:
            return _login_redirect()
        if not hasattr(user, "vendedor"):
            return _render(dj_request, "sin_perfil_vendedor.html", status=403)
        if request.method == "POST" and not _csrf_is_valid(dj_request.session):
            return _render(dj_request, "csrf_error.html", status=403)
        return view(dj_request, *args, **kwargs)

    wrapper.unwrapped = view
    return wrapper


def _queryset(dj_request, tipo):
    model = TIPOS.get(tipo)
    if model is None:
        abort(404)
    return model.objects.filter(vendedor=dj_request.user.vendedor)


@app.get("/health")
@app.get(f"{PREFIX}/health")
def health():
    return jsonify({"servicio": "publicaciones", "estado": "ok"})


@app.route(f"{PREFIX}/nuevo/", methods=["GET", "POST"])
@vendor_required
def crear_articulo(dj_request):
    if request.method == "GET":
        return _render(dj_request, "crear_articulo.html", form=CrearArticuloForm())
    form = CrearArticuloForm(_post_data(), _post_files())
    if form.is_valid():
        try:
            _service().crear_articulo(dj_request.user.vendedor, form.cleaned_data)
            return _redirect(dj_request, f"{PREFIX}/publicado/")
        except (ValueError, ErrorDeDominio) as error:
            form.add_error(None, str(error))
    return _render(dj_request, "crear_articulo.html", form=form)


@app.route(f"{PREFIX}/nuevo/repuesto/", methods=["GET", "POST"])
@vendor_required
def crear_repuesto(dj_request):
    if request.method == "GET":
        return _render(dj_request, "crear_repuesto.html", form=RepuestoForm())
    form = RepuestoForm(_post_data())
    if form.is_valid():
        try:
            _service().crear_repuesto(dj_request.user.vendedor, form.cleaned_data)
            return _redirect(dj_request, f"{PREFIX}/publicado/")
        except (ValueError, ErrorDeDominio) as error:
            form.add_error(None, str(error))
    return _render(dj_request, "crear_repuesto.html", form=form)


@app.get(f"{PREFIX}/publicado/")
def articulo_publicado():
    dj_request = _session_request()
    if not dj_request.user.is_authenticated:
        return _login_redirect()
    return _render(dj_request, "articulo_publicado.html")


def _listado(dj_request, error=None):
    vendedor = dj_request.user.vendedor
    return _render(
        dj_request,
        "mis_publicaciones.html",
        carros=list(vendedor.carros.all()),
        repuestos=list(vendedor.repuestos.all()),
        error=error,
    )


@app.get(f"{PREFIX}/mis-publicaciones/")
@vendor_required
def mis_publicaciones(dj_request):
    return _listado(dj_request)


@app.route(f"{PREFIX}/editar/<tipo>/<int:pk>/", methods=["GET", "POST"])
@vendor_required
def editar_articulo(dj_request, tipo, pk):
    instance = _queryset(dj_request, tipo).filter(pk=pk).first()
    if instance is None:
        abort(404)
    form_class = CarroEdicionForm if tipo == "carro" else RepuestoForm
    if request.method == "GET":
        form = form_class(instance=instance)
    else:
        form = form_class(_post_data(), instance=instance)
        if form.is_valid():
            fresh = _queryset(dj_request, tipo).get(pk=pk)
            try:
                service = _service()
                if tipo == "carro":
                    service.editar_carro(fresh, form.cleaned_data)
                else:
                    service.editar_repuesto(fresh, form.cleaned_data)
                return _redirect(dj_request, f"{PREFIX}/mis-publicaciones/")
            except ErrorDeDominio as error:
                form.add_error(None, str(error))
    return _render(dj_request, "editar_articulo.html", form=form, tipo=tipo, object=instance)


@app.route(f"{PREFIX}/eliminar/<tipo>/<int:pk>/", methods=["GET", "POST"])
@vendor_required
def eliminar_articulo(dj_request, tipo, pk):
    instance = _queryset(dj_request, tipo).filter(pk=pk).first()
    if instance is None:
        abort(404)
    if request.method == "GET":
        return _render(dj_request, "confirmar_eliminar.html", tipo=tipo, object=instance)
    try:
        _service().eliminar_articulo(instance)
    except ErrorDeDominio as error:
        return _listado(dj_request, error=str(error))
    return _redirect(dj_request, f"{PREFIX}/mis-publicaciones/")


@app.errorhandler(404)
def not_found(_error):
    return jsonify({"detail": "No encontrado."}), 404
