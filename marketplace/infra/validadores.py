"""Implementaciones concretas del puerto `ValidadorDocumental`.

Ambas cumplen el mismo contrato, así que el Service Layer puede usar
cualquiera sin enterarse (Sustitución de Liskov). Quién se inyecta lo decide
`ValidadorDocumentalFactory` según la variable de entorno.
"""

import logging
from datetime import date

from ..domain.ports import ResultadoValidacion, ValidadorDocumental

logger = logging.getLogger(__name__)


class ValidadorDocumentalMock(ValidadorDocumental):
    """Aprueba siempre. Para desarrollo local y pruebas automatizadas.

    Evita depender del RUNT (servicio externo, lento y con cuota) mientras se
    trabaja en la interfaz o se corren los tests.
    """

    def validar(self, placa, documentos) -> ResultadoValidacion:
        logger.info("[MOCK] Documentos de %s aprobados sin verificar.", placa)
        return ResultadoValidacion.ok()


class ValidadorDocumentalRunt(ValidadorDocumental):
    """Verifica vigencia real de los documentos contra la fecha actual.

    En producción este validador además consultaría el RUNT para confirmar
    que la placa no tenga reporte de hurto ni embargos.
    """

    def __init__(self, hoy=None):
        # Inyectable para poder probar el vencimiento sin congelar el reloj.
        self._hoy = hoy or date.today

    def validar(self, placa, documentos) -> ResultadoValidacion:
        hoy = self._hoy()
        vencidos = [
            f"{doc.tipo_documento} vencido el {doc.fecha_vencimiento:%d/%m/%Y}."
            for doc in documentos
            if doc.fecha_vencimiento < hoy
        ]
        futuros = [
            f"{doc.tipo_documento} tiene fecha de expedición futura."
            for doc in documentos
            if doc.fecha_expedicion > hoy
        ]

        motivos = vencidos + futuros
        if motivos:
            logger.warning("[REAL] Documentos de %s rechazados: %s", placa, motivos)
            return ResultadoValidacion.rechazado(*motivos)

        logger.info("[REAL] Documentos de %s verificados y vigentes.", placa)
        return ResultadoValidacion.ok()
