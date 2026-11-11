"""Microservicio Flask para el modulo de pagos de CarFit.

Esta primera etapa expone la logica de pagos existente como API JSON sin
eliminar las vistas ni los servicios de Django. Flask actua como una frontera
de migracion: delega en los mismos servicios de aplicacion para conservar las
reglas de negocio, la persistencia y las pasarelas actuales.

Ejecutar desde la raiz del proyecto:

    flask --app payments_microservice run --port 5001
"""

from django.utils.translation import gettext as _

import os
from datetime import date, datetime
from decimal import Decimal

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "carfit.settings")

import django

django.setup()

from flask import Flask, jsonify, request

from marketplace.domain.exceptions import (
    ArticuloNoDisponibleError,
    ErrorDeDominio,
    PagoNoFacturableError,
    PasarelaNoDisponibleError,
    RecursoNoEncontradoError,
    TransicionPagoInvalidaError,
)
from marketplace.models import Cliente, Pago
from marketplace.services import (
    CatalogoMetodosPagoService,
    ConfirmarPagoService,
    ConsultarPagoService,
    FacturaService,
    ProcesarPagoService,
)


from marketplace.flask_i18n import instalar_i18n

app = Flask(__name__)

instalar_i18n(app)


def _json_value(value):
    """Convierte valores del dominio a tipos que Flask puede serializar."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "value"):
        return value.value
    return value


def _pago_json(pago):
    articulo = pago.carro or pago.repuesto
    return {
        "id": pago.id,
        "referencia": pago.referencia,
        "estado": pago.estado,
        "estado_etiqueta": pago.get_estado_display(),
        "metodo_pago": pago.metodo_pago,
        "metodo_pago_etiqueta": pago.get_metodo_pago_display(),
        "precio": pago.precio,
        "comision": pago.comision,
        "total": pago.total,
        "moneda": pago.moneda,
        "cuotas": pago.cuotas,
        "pasarela": pago.pasarela,
        "referencia_pasarela": pago.referencia_pasarela,
        "codigo_autorizacion": pago.codigo_autorizacion,
        "mensaje": pago.mensaje,
        "fecha": _json_value(pago.fecha),
        "actualizado_en": _json_value(pago.actualizado_en),
        "articulo": None
        if articulo is None
        else {
            "tipo": "CARRO" if pago.carro_id else "REPUESTO",
            "id": articulo.pk,
            "descripcion": str(articulo),
        },
    }


def _cliente_desde_request():
    """Obtiene el cliente de la peticion sin migrar aun autenticacion."""
    datos = request.get_json(silent=True) or {}
    cliente_id = request.args.get("cliente_id", datos.get("cliente_id"))
    if cliente_id is None:
        raise RecursoNoEncontradoError(_('un cliente autenticado'))
    try:
        return Cliente.objects.get(pk=int(cliente_id))
    except (Cliente.DoesNotExist, ValueError):
        raise RecursoNoEncontradoError(_('el cliente'), cliente_id) from None


def _error_response(error):
    if isinstance(error, RecursoNoEncontradoError):
        estado = 404
    elif isinstance(error, PasarelaNoDisponibleError):
        estado = 503
    elif isinstance(error, (ArticuloNoDisponibleError, TransicionPagoInvalidaError)):
        estado = 409
    elif isinstance(error, (PagoNoFacturableError, ErrorDeDominio)):
        estado = 400
    else:
        estado = 500
    return jsonify({"error": str(error)}), estado


@app.get("/health")
def health():
    return jsonify({"servicio": "pagos", "estado": "ok"})


@app.get("/api/v2/pagos/metodos", strict_slashes=False)
def metodos_pago():
    monto = request.args.get("monto")
    if monto is not None:
        try:
            monto = int(monto)
        except ValueError:
            return jsonify({"error": _('monto debe ser un entero.')}), 400
    metodos = CatalogoMetodosPagoService().listar(monto)
    return jsonify(
        {
            "metodos": [
                {
                    "codigo": metodo.codigo,
                    "etiqueta": metodo.etiqueta,
                    "comision_porcentual": str(metodo.comision_porcentual),
                    "comision_fija": metodo.comision_fija,
                    "monto_minimo": metodo.monto_minimo,
                    "monto_maximo": metodo.monto_maximo,
                    "campos_requeridos": list(metodo.campos_requeridos),
                    "permite_cuotas": metodo.permite_cuotas,
                    "cuotas_maximas": metodo.cuotas_maximas,
                    "confirmacion_inmediata": metodo.confirmacion_inmediata,
                }
                for metodo in metodos
            ]
        }
    )


@app.route("/api/v2/pagos", methods=["GET", "POST"], strict_slashes=False)
def pagos():
    try:
        cliente = _cliente_desde_request()
        if request.method == "GET":
            pagos_cliente = ConsultarPagoService().listar(cliente)
            return jsonify({"pagos": [_pago_json(pago) for pago in pagos_cliente]})

        datos = request.get_json(silent=True)
        if not isinstance(datos, dict):
            return jsonify({"error": _('El cuerpo debe ser un objeto JSON.')}), 400
        datos = dict(datos)
        datos.pop("cliente_id", None)
        pago = ProcesarPagoService().procesar(cliente, datos)
        estado = 409 if pago.estado == Pago.Estado.RECHAZADO else 201
        return jsonify(_pago_json(pago)), estado
    except ErrorDeDominio as error:
        return _error_response(error)


@app.get("/api/v2/pagos/<string:referencia>", strict_slashes=False)
def detalle_pago(referencia):
    try:
        cliente = _cliente_desde_request()
        pago = ConsultarPagoService().obtener(referencia, cliente)
        return jsonify(_pago_json(pago))
    except ErrorDeDominio as error:
        return _error_response(error)


@app.post("/api/v2/pagos/<string:referencia>/confirmar", strict_slashes=False)
def confirmar_pago(referencia):
    try:
        cliente = _cliente_desde_request()
        pago = ConfirmarPagoService().confirmar(referencia, cliente)
        return jsonify(_pago_json(pago))
    except ErrorDeDominio as error:
        return _error_response(error)


@app.get("/api/v2/pagos/<string:referencia>/factura", strict_slashes=False)
def factura_pago(referencia):
    try:
        cliente = _cliente_desde_request()
        factura = FacturaService().generar(referencia, cliente)
        return jsonify(
            {
                campo: _json_value(getattr(factura, campo))
                for campo in (
                    "numero",
                    "fecha_emision",
                    "referencia_pago",
                    "cliente_nombre",
                    "cliente_correo",
                    "vendedor_nombre",
                    "articulo_descripcion",
                    "metodo_pago",
                    "subtotal",
                    "comision",
                    "total",
                    "moneda",
                )
            }
        )
    except ErrorDeDominio as error:
        return _error_response(error)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5001")), debug=True)