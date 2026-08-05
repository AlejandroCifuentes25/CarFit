"""Puertos (interfaces) del dominio.

Aplican el principio de Inversión de Dependencias (la D de SOLID): el
Service Layer depende de estas abstracciones, nunca de las implementaciones
concretas de `infra/`. Las Factories son las que deciden qué implementación
se inyecta en tiempo de ejecución.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


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
