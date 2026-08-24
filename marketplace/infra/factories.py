"""Factories de infraestructura.

Patrón Creacional: Factory Method.

Motivación: el Service Layer necesita *un* validador documental y *un*
notificador, pero no debe saber cuál. Sin Factory, el servicio tendría un
`if settings.DEBUG:` incrustado, lo que lo acopla al entorno y hace
imposible probarlo de forma aislada.

Estas factories son el único punto del sistema que conoce las clases
concretas. El comportamiento se cambia con **variables de entorno**, sin
tocar una línea de código:

    VALIDADOR_DOCUMENTAL=MOCK   # desarrollo: aprueba todo
    VALIDADOR_DOCUMENTAL=REAL   # producción: verifica vigencia real

    NOTIFICADOR=MOCK            # desarrollo: imprime en consola
    NOTIFICADOR=REAL            # producción: envía correo

    PASARELA_PAGO=MOCK          # desarrollo: pasarela simulada, sin red
    PASARELA_PAGO=REAL          # producción: agregador y corresponsal reales

    NOTIFICADOR_PAGOS=MOCK      # desarrollo: comprobante por consola
    NOTIFICADOR_PAGOS=REAL      # producción: comprobante por correo

El registro por diccionario mantiene la factory **abierta a extensión y
cerrada a modificación** (la O de SOLID): agregar un `NotificadorSMS` solo
requiere una entrada nueva en el mapa, no editar un `if/elif`.
"""

import os

from ..domain.metodos_pago import (
    PASARELA_AGREGADOR,
    PASARELA_CORRESPONSAL,
    obtener_especificacion,
)
from ..domain.ports import (
    Notificador,
    NotificadorPagos,
    PasarelaPago,
    ValidadorDocumental,
)
from .notificadores import (
    NotificadorConsola,
    NotificadorEmail,
    NotificadorPagoConsola,
    NotificadorPagoEmail,
)
from .pasarelas import (
    PasarelaAgregador,
    PasarelaCorresponsalEfectivo,
    PasarelaSimulada,
)
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


class NotificadorPagosFactory:
    """Crea el notificador de comprobantes de pago según el entorno."""

    VARIABLE_ENTORNO = "NOTIFICADOR_PAGOS"
    POR_DEFECTO = "MOCK"

    _registro = {
        "MOCK": NotificadorPagoConsola,
        "REAL": NotificadorPagoEmail,
    }

    @classmethod
    def crear(cls, tipo=None) -> NotificadorPagos:
        clave = (tipo or os.getenv(cls.VARIABLE_ENTORNO, cls.POR_DEFECTO)).upper()
        try:
            return cls._registro[clave]()
        except KeyError:
            raise ValueError(
                f"{cls.VARIABLE_ENTORNO}='{clave}' no es válido. "
                f"Opciones: {', '.join(sorted(cls._registro))}."
            ) from None


class PasarelaPagoFactory:
    """Crea la pasarela que corresponde a un método de pago.

    Es la Factory con más trabajo del sistema porque decide en dos ejes:

    1. **Qué método se está pagando.** Una tarjeta se cobra contra un
       agregador; el efectivo se cobra generando un código de recaudo. Son
       integraciones distintas, no dos ramas de la misma.
    2. **En qué entorno corre.** En desarrollo y en las pruebas nadie quiere
       golpear la API del agregador: `PASARELA_PAGO=MOCK` sustituye ambas
       por una pasarela simulada sin cambiar una línea del servicio.

    Ese doble eje es justo lo que produciría un `if metodo == ... elif
    entorno == ...` incrustado en `services.py`. Aquí queda como un mapa de
    dos niveles: agregar un método nuevo es apuntarlo a una pasarela lógica
    en el catálogo del dominio, y agregar un proveedor nuevo es una entrada
    más en este registro (Abierto/Cerrado).
    """

    VARIABLE_ENTORNO = "PASARELA_PAGO"
    POR_DEFECTO = "MOCK"

    _registro = {
        "MOCK": {
            PASARELA_AGREGADOR: PasarelaSimulada,
            PASARELA_CORRESPONSAL: PasarelaSimulada,
        },
        "REAL": {
            PASARELA_AGREGADOR: PasarelaAgregador,
            PASARELA_CORRESPONSAL: PasarelaCorresponsalEfectivo,
        },
    }

    @classmethod
    def crear(cls, metodo, modo=None) -> PasarelaPago:
        """Devuelve la pasarela capaz de cobrar `metodo`.

        Raises:
            MetodoPagoNoSoportadoError: el método no está en el catálogo.
            ValueError: la variable de entorno tiene un valor inválido.
        """
        clave_modo = (modo or os.getenv(cls.VARIABLE_ENTORNO, cls.POR_DEFECTO)).upper()
        if clave_modo not in cls._registro:
            raise ValueError(
                f"{cls.VARIABLE_ENTORNO}='{clave_modo}' no es válido. "
                f"Opciones: {', '.join(sorted(cls._registro))}."
            )

        # El dominio es quien sabe qué pasarela lógica atiende cada método:
        # la Factory solo traduce esa decisión a una clase concreta.
        especificacion = obtener_especificacion(metodo)
        return cls._registro[clave_modo][especificacion.pasarela]()
