"""Flask storefront and shopping-cart slice sharing Django's domain services."""

import os
from functools import wraps
from pathlib import Path
from urllib.parse import quote

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "carfit.settings")

import django

django.setup()

from flask import Flask, jsonify, redirect, render_template, request

from accounts_microservice import (
    _csrf_is_valid,
    _ensure_csrf_token,
    _save_session_cookie,
    _session_request,
)
from marketplace.domain.exceptions import ErrorDeDominio
from marketplace.forms import PagoForm
from marketplace.models import Cliente
from marketplace.services import (
    CarritoComprasService,
    CatalogoComprasService,
    PagarCarritoService,
)

PREFIX = "/compras/v2"
LOGIN_URL = "/cuentas/login/"

app = Flask(
    __name__,
    template_folder=str(Path(__file__).parent / "marketplace/templates/flask_compras"),
)


@app.template_filter("cop")
def formatear_pesos(valor):
    return f"{int(valor):,}".replace(",", ".")


def _login_redirect():
    return redirect(f"{LOGIN_URL}?next={quote(request.full_path.rstrip('?'))}")


def _cliente_de(django_request):
    user = django_request.user
    cliente = getattr(user, "cliente", None)
    if cliente is None:
        vendedor = getattr(user, "vendedor", None)
        cliente, _ = Cliente.objects.get_or_create(
            usuario=user,
            defaults={
                "nombre": vendedor.nombre if vendedor else user.username,
                "correo": vendedor.correo if vendedor else user.email,
                "direccion": vendedor.direccion if vendedor else "",
                "numero_tel": vendedor.numero_tel if vendedor else "",
            },
        )
        django_request.user.cliente = cliente
    return cliente


def _resumen(usuario):
    resumen = CarritoComprasService().obtener_resumen(usuario)
    carrito = resumen["carrito"]
    return {
        "carrito": {
            "carrito_id": carrito.pk,
            "cantidad_producto": carrito.cantidad_producto,
            "precio_total": carrito.precio_total,
        },
        "articulos": resumen["articulos"],
    }


def _render(django_request, template, status=200, **context):
    context.setdefault("csrf_token", _ensure_csrf_token(django_request.session))
    context.setdefault("user", django_request.user)
    context.setdefault("prefix", PREFIX)
    response = app.response_class(
        render_template(template, **context),
        status=status,
    )
    return _save_session_cookie(response, django_request.session)


def _redirect(django_request, location):
    return _save_session_cookie(redirect(location), django_request.session)


def _require_login(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        django_request = _session_request()
        if not django_request.user.is_authenticated:
            return _login_redirect()
        _cliente_de(django_request)
        return view(django_request, *args, **kwargs)

    return wrapper


def _require_json_login():
    django_request = _session_request()
    if not django_request.user.is_authenticated:
        return None, (jsonify({"detail": "Se requiere iniciar sesión."}), 401)
    _cliente_de(django_request)
    return django_request, None


def _require_csrf():
    if not _csrf_is_valid(_session_request().session):
        return jsonify({"detail": "Token CSRF ausente o inválido."}), 403
    return None


def _carrito_json(usuario):
    return jsonify({"carrito": _resumen(usuario)["carrito"]})


@app.get("/health")
@app.get(f"{PREFIX}/health")
def health():
    return jsonify({"servicio": "compras", "estado": "ok"})


@app.get(f"{PREFIX}/catalogo/")
@_require_login
def catalogo(django_request):
    carros, repuestos = CatalogoComprasService().listar_disponibles(
        django_request.user
    )
    resumen = _resumen(django_request.user)
    carrito_carros_ids = {
        item.articulo_id
        for item in resumen["articulos"]
        if item.tipo_articulo == "carro"
    }
    carrito_repuestos_ids = {
        item.articulo_id
        for item in resumen["articulos"]
        if item.tipo_articulo == "repuesto"
    }
    return _render(
        django_request,
        "catalogo.html",
        carros=carros,
        repuestos=repuestos,
        carrito_carros_ids=carrito_carros_ids,
        carrito_repuestos_ids=carrito_repuestos_ids,
        carrito=resumen["carrito"],
    )


@app.route(f"{PREFIX}/carrito/", methods=["GET", "POST"])
@_require_login
def carrito(django_request):
    resumen = _resumen(django_request.user)
    form = PagoForm(
        request.form if request.method == "POST" else None,
        monto=resumen["carrito"]["precio_total"],
    )
    if request.method == "POST":
        if not _csrf_is_valid(django_request.session):
            return _render(
                django_request,
                "carrito.html",
                status=403,
                form=form,
                **resumen,
            )
        if form.is_valid():
            try:
                resultado = PagarCarritoService().procesar(
                    django_request.user.cliente,
                    form.cleaned_data,
                )
            except ErrorDeDominio as error:
                form.add_error(None, str(error))
            else:
                pagos = resultado.get("pagos", [])
                if pagos:
                    return _redirect(
                        django_request,
                        f"/pagos/{quote(pagos[0].referencia, safe='')}/",
                    )
                return _redirect(django_request, "/pagos/")
        resumen = _resumen(django_request.user)

    return _render(
        django_request,
        "carrito.html",
        form=form,
        metodo_inicial=form.metodos[0].codigo if form.metodos else None,
        **resumen,
    )


@app.get(f"{PREFIX}/api/carrito/total/")
def obtener_total_carrito():
    django_request, error = _require_json_login()
    if error:
        return error
    return _carrito_json(django_request.user)


@app.post(f"{PREFIX}/api/carrito/agregar/<tipo_articulo>/<int:articulo_id>/")
def agregar_articulo_carrito(tipo_articulo, articulo_id):
    django_request, error = _require_json_login()
    if error:
        return error
    csrf_error = _require_csrf()
    if csrf_error:
        return csrf_error
    return _mover_articulo(django_request, "agregar", tipo_articulo, articulo_id)


@app.post(f"{PREFIX}/api/carrito/quitar/<tipo_articulo>/<int:articulo_id>/")
def quitar_articulo_carrito(tipo_articulo, articulo_id):
    django_request, error = _require_json_login()
    if error:
        return error
    csrf_error = _require_csrf()
    if csrf_error:
        return csrf_error
    return _mover_articulo(django_request, "quitar", tipo_articulo, articulo_id)


def _mover_articulo(django_request, accion, tipo_articulo, articulo_id):
    servicio = CarritoComprasService()
    try:
        operacion = (
            servicio.agregar_articulo
            if accion == "agregar"
            else servicio.quitar_articulo
        )
        articulo = operacion(django_request.user, tipo_articulo, articulo_id)
    except ErrorDeDominio as error:
        return jsonify({"detail": str(error)}), 400
    return jsonify(
        {
            "articulo": {
                "accion": articulo.accion,
                "tipo_articulo": articulo.tipo_articulo,
                "articulo_id": articulo.articulo_id,
                "titulo": articulo.titulo,
                "precio": articulo.precio,
                "vendedor_id": articulo.vendedor_id,
                "vendedor_nombre": articulo.vendedor_nombre,
                "detalle": articulo.detalle,
            },
            "carrito": _resumen(django_request.user)["carrito"],
        }
    )


@app.post(f"{PREFIX}/api/carrito/vaciar/")
def vaciar_carrito():
    django_request, error = _require_json_login()
    if error:
        return error
    csrf_error = _require_csrf()
    if csrf_error:
        return csrf_error
    CarritoComprasService().vaciar_carrito(django_request.user)
    return _carrito_json(django_request.user)


@app.errorhandler(404)
def not_found(_error):
    return jsonify({"detail": "No encontrado."}), 404
