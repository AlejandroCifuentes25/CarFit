"""Factories de infraestructura.

Patrón Creacional: Factory Method.

Motivación: el Service Layer necesita *un* validador documental y *un*
notificador, pero no debe saber cuál. Sin Factory, el servicio tendría un
`if settings.DEBUG:` incrustado — lo que lo acopla al entorno y hace
imposible probarlo de forma aislada.

Estas factories son el único punto del sistema que conoce las clases
concretas. El comportamiento se cambia con **variables de entorno**, sin
tocar una línea de código:

    VALIDADOR_DOCUMENTAL=MOCK   # desarrollo: aprueba todo
    VALIDADOR_DOCUMENTAL=REAL   # producción: verifica vigencia real

    NOTIFICADOR=MOCK            # desarrollo: imprime en consola
    NOTIFICADOR=REAL            # producción: envía correo

El registro por diccionario mantiene la factory **abierta a extensión y
cerrada a modificación** (la O de SOLID): agregar un `NotificadorSMS` solo
requiere una entrada nueva en el mapa, no editar un `if/elif`.
"""

import os

from ..domain.ports import Notificador, ValidadorDocumental
from .notificadores import NotificadorConsola, NotificadorEmail
from .validadores import ValidadorDocumentalMock, ValidadorDocumentalRunt


class ValidadorDocumentalFactory:
    """Crea el validador documental que corresponde al entorno."""

    VARIABLE_ENTORNO = "VALIDADOR_DOCUMENTAL"
    POR_DEFECTO = "MOCK"

    _registro = {
        "MOCK": ValidadorDocumentalMock,
        "REAL": ValidadorDocumentalRunt,
    }

    @classmethod
    def crear(cls, tipo=None) -> ValidadorDocumental:
        clave = (tipo or os.getenv(cls.VARIABLE_ENTORNO, cls.POR_DEFECTO)).upper()
        try:
            return cls._registro[clave]()
        except KeyError:
            raise ValueError(
                f"{cls.VARIABLE_ENTORNO}='{clave}' no es válido. "
                f"Opciones: {', '.join(sorted(cls._registro))}."
            ) from None


class NotificadorFactory:
    """Crea el notificador que corresponde al entorno."""

    VARIABLE_ENTORNO = "NOTIFICADOR"
    POR_DEFECTO = "MOCK"

    _registro = {
        "MOCK": NotificadorConsola,
        "REAL": NotificadorEmail,
    }

    @classmethod
    def crear(cls, tipo=None) -> Notificador:
        clave = (tipo or os.getenv(cls.VARIABLE_ENTORNO, cls.POR_DEFECTO)).upper()
        try:
            return cls._registro[clave]()
        except KeyError:
            raise ValueError(
                f"{cls.VARIABLE_ENTORNO}='{clave}' no es válido. "
                f"Opciones: {', '.join(sorted(cls._registro))}."
            ) from None
