"""Traducción de errores de dominio a respuestas HTTP.

El dominio no sabe que existe HTTP: lanza `PagoDuplicadoError`, no "409".
Esta tabla es el único lugar del proyecto donde ese vocabulario se cruza,
de modo que las vistas no repitan el mismo `except ... return Response(...)`
cuatro veces ni inventen códigos distintos para el mismo problema.

Códigos usados:

* **400** los datos enviados no cumplen las reglas de negocio.
* **404** el recurso referenciado no existe (o no le pertenece a quien pregunta).
* **409** el recurso existe pero su estado impide la operación: pago
  duplicado, artículo ya vendido, pago que ya estaba resuelto.
* **503** la pasarela de pagos no respondió. No es culpa del cliente, así
  que reintentar la misma petición tiene sentido.
"""

from rest_framework import status
from rest_framework.response import Response

from ..domain.exceptions import (
    ArticuloNoDisponibleError,
    ErrorDeDominio,
    PagoDuplicadoError,
    PagoInvalidoError,
    PagoNoFacturableError,
    PasarelaNoDisponibleError,
    RecursoNoEncontradoError,
    TransicionPagoInvalidaError,
)

#: Se recorre en orden y gana la primera coincidencia, así que las
#: excepciones más específicas van primero.
CODIGOS_HTTP = (
    (PagoDuplicadoError, status.HTTP_409_CONFLICT),
    (ArticuloNoDisponibleError, status.HTTP_409_CONFLICT),
    (TransicionPagoInvalidaError, status.HTTP_409_CONFLICT),
    (PagoNoFacturableError, status.HTTP_409_CONFLICT),
    (RecursoNoEncontradoError, status.HTTP_404_NOT_FOUND),
    (PasarelaNoDisponibleError, status.HTTP_503_SERVICE_UNAVAILABLE),
    (PagoInvalidoError, status.HTTP_400_BAD_REQUEST),
    (ErrorDeDominio, status.HTTP_400_BAD_REQUEST),
)


def codigo_para(error) -> int:
    """Código HTTP que corresponde a `error`."""
    for clase, codigo in CODIGOS_HTTP:
        if isinstance(error, clase):
            return codigo
    return status.HTTP_400_BAD_REQUEST


def respuesta_de_error(error) -> Response:
    """Respuesta HTTP con el formato de error uniforme de la API."""
    cuerpo = {"error": str(error)}

    # Los errores que agrupan varias causas (invariantes del Builder,
    # documentos vencidos) las exponen para que el cliente corrija todo de
    # una sola vez en lugar de descubrirlas de a una.
    detalles = getattr(error, "errores", None) or getattr(error, "motivos", None)
    if detalles:
        cuerpo["detalles"] = list(detalles)

    return Response(cuerpo, status=codigo_para(error))
