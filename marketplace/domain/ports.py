"""Puertos (interfaces) del dominio.

Aplican el principio de Inversión de Dependencias (la D de SOLID): el
Service Layer depende de estas abstracciones, nunca de las implementaciones
concretas de `infra/`. Las Factories son las que deciden qué implementación
se inyecta en tiempo de ejecución.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum


@dataclass(frozen=True)
class ResultadoValidacion:
    """Respuesta de un validador documental."""

    es_valido: bool
    motivos: tuple = field(default_factory=tuple)

    @classmethod
    def ok(cls):
        return cls(es_valido=True)

    @classmethod
    def rechazado(cls, *motivos):
        return cls(es_valido=False, motivos=tuple(motivos))


class ValidadorDocumental(ABC):
    """Verifica que los documentos legales del vehículo estén vigentes."""

    @abstractmethod
    def validar(self, placa, documentos) -> ResultadoValidacion:
        """Devuelve el resultado de validar `documentos` para `placa`."""


class Notificador(ABC):
    """Avisa al vendedor que su artículo quedó publicado."""

    @abstractmethod
    def notificar_publicacion(self, articulo) -> None:
        """Envía la confirmación de publicación de `articulo`."""


# ----------------------------------------------------------------------
# Pagos
# ----------------------------------------------------------------------


class ResultadoTransaccion(Enum):
    """Los tres desenlaces posibles de una operación contra una pasarela.

    Es vocabulario del dominio, deliberadamente independiente de los estados
    que guarda la base de datos: una pasarela nunca devuelve "REEMBOLSADO"
    ni "ANULADO", esos son estados internos de CarFit. El Service Layer se
    encarga de traducir de este enum al `Pago.Estado` correspondiente.
    """

    APROBADA = "APROBADA"
    PENDIENTE = "PENDIENTE"
    RECHAZADA = "RECHAZADA"


@dataclass(frozen=True)
class SolicitudPago:
    """Lo que la pasarela necesita saber para intentar cobrar.

    Es un objeto plano y sin Django a propósito: una pasarela no debe
    recibir un modelo de la base de datos ni un `request`, solo el dato
    mínimo del cobro. Así se puede probar sin tocar la BD.
    """

    referencia: str
    monto: int
    moneda: str
    metodo: str
    cuotas: int = 1
    descripcion: str = ""
    correo_pagador: str = ""
    datos_metodo: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ResultadoPago:
    """Respuesta normalizada de una pasarela.

    Cada proveedor responde con su propio formato ("APPROVED", "success",
    códigos numéricos). Las implementaciones de `PasarelaPago` traducen esa
    jerga a este objeto, que es lo único que ve el Service Layer.
    """

    resultado: ResultadoTransaccion
    referencia_pasarela: str = ""
    codigo_autorizacion: str = ""
    mensaje: str = ""

    @property
    def fue_aprobado(self) -> bool:
        return self.resultado is ResultadoTransaccion.APROBADA

    @property
    def quedo_pendiente(self) -> bool:
        return self.resultado is ResultadoTransaccion.PENDIENTE

    @property
    def fue_rechazado(self) -> bool:
        return self.resultado is ResultadoTransaccion.RECHAZADA

    @classmethod
    def aprobado(cls, referencia_pasarela="", codigo_autorizacion="", mensaje=""):
        return cls(
            resultado=ResultadoTransaccion.APROBADA,
            referencia_pasarela=referencia_pasarela,
            codigo_autorizacion=codigo_autorizacion,
            mensaje=mensaje or "Transacción aprobada.",
        )

    @classmethod
    def pendiente(cls, referencia_pasarela="", mensaje=""):
        return cls(
            resultado=ResultadoTransaccion.PENDIENTE,
            referencia_pasarela=referencia_pasarela,
            mensaje=mensaje or "Transacción pendiente de confirmación.",
        )

    @classmethod
    def rechazado(cls, mensaje, referencia_pasarela=""):
        return cls(
            resultado=ResultadoTransaccion.RECHAZADA,
            referencia_pasarela=referencia_pasarela,
            mensaje=mensaje,
        )


class PasarelaPago(ABC):
    """Puerto de salida hacia un proveedor de pagos.

    Toda pasarela (tarjetas, PSE, corresponsal en efectivo, la simulada de
    desarrollo) cumple este contrato. El Service Layer depende de esta
    abstracción y jamás de una clase concreta: cambiar de proveedor no
    debería obligar a tocar la lógica de negocio (Inversión de Dependencias).
    """

    #: Nombre con el que la pasarela queda registrada en la bitácora.
    nombre = "PASARELA"

    @abstractmethod
    def procesar(self, solicitud: SolicitudPago) -> ResultadoPago:
        """Intenta cobrar `solicitud` y devuelve el desenlace normalizado.

        Raises:
            PasarelaNoDisponibleError: el proveedor falló o no respondió.
                Un cobro *rechazado* no es una excepción: es un
                `ResultadoPago` con resultado RECHAZADA.
        """

    @abstractmethod
    def consultar(self, referencia: str) -> ResultadoPago:
        """Consulta en qué quedó la transacción `referencia`.

        Necesario para los métodos que no confirman en el momento: PSE y
        efectivo pueden tardar minutos u horas en resolverse.
        """


class NotificadorPagos(ABC):
    """Avisa al cliente en qué terminó su pago.

    Es un puerto aparte de `Notificador` y no un método más dentro de él:
    quien notifica publicaciones no tiene por qué saber de pagos
    (Segregación de Interfaces). Agregar el método al puerto existente
    obligaría a `NotificadorConsola` y `NotificadorEmail` a implementar algo
    que no les corresponde.
    """

    @abstractmethod
    def notificar_resultado(self, pago) -> None:
        """Informa al cliente el estado final de `pago`."""
