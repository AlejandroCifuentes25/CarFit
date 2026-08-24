"""Implementaciones concretas del puerto `PasarelaPago`.

Las tres cumplen el mismo contrato, así que el Service Layer usa cualquiera
sin enterarse (Sustitución de Liskov). Quién se inyecta lo decide
`PasarelaPagoFactory` a partir del método de pago y del entorno.

Aquí, y solo aquí, vive el detalle sucio de cada proveedor: URLs, llaves,
tiempos de espera y la jerga de estados de cada uno ("APPROVED", "DECLINED",
"PENDING"). Todo eso se traduce a `ResultadoPago` antes de salir del módulo,
para que un cambio de proveedor no se filtre al negocio.
"""

import json
import logging
import os
import zlib
from datetime import timedelta
from urllib import error, parse, request

from django.utils import timezone

from ..domain.exceptions import PasarelaNoDisponibleError
from ..domain.ports import PasarelaPago, ResultadoPago

logger = logging.getLogger(__name__)

#: Token de prueba que la pasarela simulada rechaza siempre. Permite
#: demostrar el camino de rechazo sin depender del azar.
TOKEN_RECHAZO = "RECHAZAR"

#: Días que un cliente tiene para acercarse al corresponsal antes de que el
#: código de recaudo caduque.
DIAS_VIGENCIA_RECAUDO = 3


class PasarelaSimulada(PasarelaPago):
    """Pasarela de desarrollo: no sale a internet y es determinista.

    Reglas de simulación, pensadas para poder probar los tres desenlaces:

    * Si algún dato del método contiene ``RECHAZAR``, la transacción se
      rechaza.
    * Si el método no confirma en el momento (PSE, efectivo), queda
      PENDIENTE.
    * En cualquier otro caso, aprueba.

    Nada de esto usa aleatoriedad: la misma entrada produce siempre la misma
    salida, que es lo que hace útiles a las pruebas automatizadas.
    """

    nombre = "SIMULADA"

    #: Métodos que en la vida real no resuelven en la misma petición.
    METODOS_DIFERIDOS = frozenset({"PSE", "EFECTIVO"})

    def procesar(self, solicitud) -> ResultadoPago:
        referencia_pasarela = self._referencia_pasarela(solicitud.referencia)

        if self._pidieron_rechazo(solicitud):
            logger.info("[MOCK] Pago %s rechazado por dato de prueba.", solicitud.referencia)
            return ResultadoPago.rechazado(
                mensaje="Transacción rechazada por el emisor (simulación).",
                referencia_pasarela=referencia_pasarela,
            )

        if solicitud.metodo in self.METODOS_DIFERIDOS:
            logger.info("[MOCK] Pago %s queda pendiente.", solicitud.referencia)
            return ResultadoPago.pendiente(
                referencia_pasarela=referencia_pasarela,
                mensaje="A la espera de la confirmación del banco (simulación).",
            )

        logger.info(
            "[MOCK] Pago %s aprobado por $%s %s.",
            solicitud.referencia,
            f"{solicitud.monto:,}".replace(",", "."),
            solicitud.moneda,
        )
        return ResultadoPago.aprobado(
            referencia_pasarela=referencia_pasarela,
            codigo_autorizacion=self._codigo(solicitud.referencia),
            mensaje="Transacción aprobada (simulación).",
        )

    def consultar(self, referencia) -> ResultadoPago:
        """Simula que el banco ya resolvió la transacción diferida."""
        logger.info("[MOCK] Consulta de %s: aprobada.", referencia)
        return ResultadoPago.aprobado(
            referencia_pasarela=self._referencia_pasarela(referencia),
            codigo_autorizacion=self._codigo(referencia),
            mensaje="Confirmada por el banco (simulación).",
        )

    def _pidieron_rechazo(self, solicitud):
        valores = " ".join(str(valor) for valor in solicitud.datos_metodo.values())
        return TOKEN_RECHAZO in valores.upper()

    def _referencia_pasarela(self, referencia):
        return f"SIM-{self._huella(referencia)}"

    def _codigo(self, referencia):
        return f"AUT{self._huella(referencia)}"

    def _huella(self, referencia):
        """Identificador estable derivado de la referencia del pago."""
        return f"{zlib.crc32(str(referencia).encode()):08X}"


class PasarelaAgregador(PasarelaPago):
    """Pasarela real contra un agregador de pagos (Wompi, PayU, ePayco).

    Los agregadores colombianos exponen una API REST muy parecida: se envía
    la transacción, responden con un identificador y un estado, y se puede
    consultar ese identificador después. Esta clase habla ese dialecto
    común; el endpoint y la llave se configuran por variables de entorno,
    así que apuntar a otro proveedor con el mismo contrato no requiere
    recompilar nada.

    Se usa `urllib` de la biblioteca estándar a propósito: el proyecto no
    agrega dependencias de red para una integración que en la entrega corre
    en modo simulado.
    """

    nombre = "AGREGADOR"

    #: Traducción de la jerga del proveedor al vocabulario del dominio.
    ESTADOS_APROBADOS = frozenset({"APPROVED", "APROBADA", "SUCCESS"})
    ESTADOS_PENDIENTES = frozenset({"PENDING", "PENDIENTE", "IN_PROGRESS"})
    ESTADOS_RECHAZADOS = frozenset({"DECLINED", "RECHAZADA", "VOIDED", "FAILED"})

    def __init__(self, url_base=None, llave=None, timeout=None):
        # Inyectables para poder probar contra un servidor falso sin tocar
        # el entorno del sistema.
        self._url_base = (url_base or os.getenv("PASARELA_URL", "")).rstrip("/")
        self._llave = llave or os.getenv("PASARELA_LLAVE", "")
        self._timeout = int(timeout or os.getenv("PASARELA_TIMEOUT", "10"))

    def procesar(self, solicitud) -> ResultadoPago:
        cuerpo = {
            "reference": solicitud.referencia,
            # Los agregadores manejan importes en centavos para no arrastrar
            # decimales: $85.000 COP se envían como 8500000.
            "amount_in_cents": solicitud.monto * 100,
            "currency": solicitud.moneda,
            "payment_method_type": solicitud.metodo,
            "installments": solicitud.cuotas,
            "customer_email": solicitud.correo_pagador,
            "description": solicitud.descripcion,
            "payment_method": solicitud.datos_metodo,
        }
        datos = self._peticion("POST", "/transactions", cuerpo)
        return self._interpretar(datos)

    def consultar(self, referencia) -> ResultadoPago:
        ruta = f"/transactions/{parse.quote(str(referencia), safe='')}"
        datos = self._peticion("GET", ruta)
        return self._interpretar(datos)

    # ------------------------------------------------------------------
    # Detalle del transporte
    # ------------------------------------------------------------------

    def _peticion(self, metodo_http, ruta, cuerpo=None):
        if not self._url_base:
            raise PasarelaNoDisponibleError(
                self.nombre, "falta configurar la variable PASARELA_URL."
            )

        peticion = request.Request(
            url=f"{self._url_base}{ruta}",
            method=metodo_http,
            data=json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else None,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._llave}",
            },
        )

        try:
            with request.urlopen(peticion, timeout=self._timeout) as respuesta:
                return json.loads(respuesta.read().decode("utf-8"))
        except error.HTTPError as fallo:
            raise PasarelaNoDisponibleError(
                self.nombre, f"respondió HTTP {fallo.code}."
            ) from fallo
        except error.URLError as fallo:
            raise PasarelaNoDisponibleError(
                self.nombre, f"no hubo conexión ({fallo.reason})."
            ) from fallo
        except (json.JSONDecodeError, UnicodeDecodeError) as fallo:
            raise PasarelaNoDisponibleError(
                self.nombre, "devolvió una respuesta ilegible."
            ) from fallo

    def _interpretar(self, datos) -> ResultadoPago:
        """Traduce la respuesta del proveedor a vocabulario del dominio."""
        transaccion = (datos or {}).get("data", datos) or {}
        estado = str(transaccion.get("status", "")).upper()
        mensaje = transaccion.get("status_message") or ""
        referencia_pasarela = str(transaccion.get("id", ""))

        if estado in self.ESTADOS_APROBADOS:
            return ResultadoPago.aprobado(
                referencia_pasarela=referencia_pasarela,
                codigo_autorizacion=str(transaccion.get("authorization_code", "")),
                mensaje=mensaje,
            )
        if estado in self.ESTADOS_PENDIENTES:
            return ResultadoPago.pendiente(
                referencia_pasarela=referencia_pasarela, mensaje=mensaje
            )
        if estado in self.ESTADOS_RECHAZADOS:
            return ResultadoPago.rechazado(
                mensaje=mensaje or "Transacción rechazada por el emisor.",
                referencia_pasarela=referencia_pasarela,
            )

        # Un estado que no se reconoce no se asume aprobado ni rechazado:
        # dar por bueno lo desconocido es como se entregan carros sin cobrar.
        raise PasarelaNoDisponibleError(
            self.nombre, f"devolvió un estado desconocido: '{estado}'."
        )


class PasarelaCorresponsalEfectivo(PasarelaPago):
    """Pago en efectivo en un corresponsal bancario.

    No mueve dinero en línea: genera un código de recaudo con vencimiento
    para que el cliente lo pague en una tienda o corresponsal. El pago nace
    PENDIENTE por definición y solo se aprueba cuando el corresponsal
    reporta el recaudo.
    """

    nombre = "CORRESPONSAL"

    def __init__(self, dias_vigencia=DIAS_VIGENCIA_RECAUDO):
        self._dias_vigencia = dias_vigencia

    def procesar(self, solicitud) -> ResultadoPago:
        vence = timezone.localtime() + timedelta(days=self._dias_vigencia)
        codigo = f"{zlib.crc32(solicitud.referencia.encode()) % 10**10:010d}"

        logger.info(
            "[REAL] Recaudo %s generado por $%s, vence el %s.",
            codigo,
            f"{solicitud.monto:,}".replace(",", "."),
            vence.strftime("%d/%m/%Y"),
        )
        return ResultadoPago.pendiente(
            referencia_pasarela=codigo,
            mensaje=(
                f"Pague ${solicitud.monto:,} COP con el código {codigo} en cualquier "
                f"corresponsal antes del {vence:%d/%m/%Y a las %I:%M %p}."
            ).replace(",", "."),
        )

    def consultar(self, referencia) -> ResultadoPago:
        """Mientras el corresponsal no reporte, el pago sigue pendiente.

        La aprobación real llega por la notificación del recaudador, no por
        consulta: por eso aquí nunca se aprueba solo.
        """
        return ResultadoPago.pendiente(
            referencia_pasarela=str(referencia),
            mensaje="El corresponsal aún no reporta el recaudo.",
        )
