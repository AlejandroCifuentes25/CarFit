"""Catálogo de métodos de pago soportados por CarFit.

Cada método de pago no es solo una etiqueta en un `<select>`: trae consigo
reglas propias: cuánto cobra de comisión, qué datos exige, si acepta
cuotas, entre qué montos opera y si confirma en el momento o queda
pendiente. Dejar esas reglas repartidas entre la vista, el serializer y la
pasarela es justo lo que produce los `if metodo == "PSE"` regados por todo
el proyecto.

Aquí se modelan como *objetos de valor* inmutables. El resto del sistema
pregunta ("¿este método acepta cuotas?", "¿cuánta comisión cobra?") en vez
de decidir con condicionales. Agregar un método nuevo (Nequi, Daviplata,
criptomonedas) es añadir una entrada a `CATALOGO_METODOS`: ni el Builder,
ni el Service Layer, ni la API cambian (principio Abierto/Cerrado).

Este módulo no conoce HTTP ni pasarelas concretas: es dominio puro.
"""

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from ..models import Pago
from .exceptions import MetodoPagoNoSoportadoError

#: Pasarelas lógicas disponibles. La Factory de infraestructura traduce
#: estas claves a clases concretas según el entorno (ver `infra/factories.py`).
PASARELA_AGREGADOR = "AGREGADOR"
PASARELA_CORRESPONSAL = "CORRESPONSAL"


@dataclass(frozen=True)
class EspecificacionMetodoPago:
    """Reglas de negocio de un método de pago concreto.

    Attributes:
        codigo: valor almacenado en `Pago.metodo_pago`.
        etiqueta: nombre legible para el usuario final.
        pasarela: pasarela lógica que procesa este método.
        comision_porcentual: porcentaje sobre el monto, en tanto por uno.
        comision_fija: valor fijo en pesos que se suma a la comisión.
        monto_minimo / monto_maximo: rango operativo en pesos colombianos.
        campos_requeridos: datos que el pagador debe enviar sí o sí.
        permite_cuotas: si acepta diferir el pago.
        cuotas_maximas: tope de cuotas cuando las permite.
        confirmacion_inmediata: `False` cuando el pago nace PENDIENTE y la
            pasarela confirma después (PSE y efectivo).
    """

    codigo: str
    etiqueta: str
    pasarela: str
    comision_porcentual: Decimal
    comision_fija: int
    monto_minimo: int
    monto_maximo: int
    campos_requeridos: tuple = field(default_factory=tuple)
    permite_cuotas: bool = False
    cuotas_maximas: int = 1
    confirmacion_inmediata: bool = True

    def calcular_comision(self, monto: int) -> int:
        """Comisión en pesos colombianos, redondeada al peso más cercano.

        Se usa `Decimal` y no `float` porque son importes de dinero: con
        flotantes, 2.9% de 85.000.000 puede quedar en 2.464.999,9999.
        """
        variable = (Decimal(monto) * self.comision_porcentual).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
        return int(variable) + self.comision_fija

    def calcular_total(self, monto: int) -> int:
        """Lo que termina pagando el cliente: artículo más comisión."""
        return monto + self.calcular_comision(monto)

    @property
    def comision_porcentaje_legible(self) -> Decimal:
        """`comision_porcentual` expresado como número de porcentaje (2.90, no 0.0290).

        `comision_porcentual` se guarda como fracción porque así se calcula
        (`monto * comision_porcentual`). Mostrarla tal cual en pantalla dice
        "0,03%" en vez de "2,90%": esta propiedad es la que debe usar
        cualquier vista o plantilla para mostrarla a un humano.
        """
        return self.comision_porcentual * 100

    def esta_dentro_de_limites(self, monto: int) -> bool:
        return self.monto_minimo <= monto <= self.monto_maximo

    def cuotas_validas(self, cuotas: int) -> bool:
        if not self.permite_cuotas:
            return cuotas == 1
        return 1 <= cuotas <= self.cuotas_maximas

    def campos_faltantes(self, datos: dict) -> tuple:
        """Campos exigidos por este método que no llegaron o llegaron vacíos."""
        datos = datos or {}
        return tuple(
            campo
            for campo in self.campos_requeridos
            if not str(datos.get(campo) or "").strip()
        )


#: Comisiones tomadas de las tarifas públicas típicas de los agregadores de
#: pago colombianos (Wompi, PayU, ePayco) para 2026. Se declaran aquí, no en
#: la pasarela, porque son una regla comercial de CarFit: si mañana se
#: negocia otra tarifa, cambia este catálogo y nada más.
CATALOGO_METODOS = {
    Pago.Metodo.TARJETA_CREDITO: EspecificacionMetodoPago(
        codigo=Pago.Metodo.TARJETA_CREDITO,
        etiqueta="Tarjeta de crédito",
        pasarela=PASARELA_AGREGADOR,
        comision_porcentual=Decimal("0.0290"),
        comision_fija=900,
        monto_minimo=1_500,
        monto_maximo=200_000_000,
        campos_requeridos=("token_tarjeta",),
        permite_cuotas=True,
        cuotas_maximas=36,
    ),
    Pago.Metodo.TARJETA_DEBITO: EspecificacionMetodoPago(
        codigo=Pago.Metodo.TARJETA_DEBITO,
        etiqueta="Tarjeta débito",
        pasarela=PASARELA_AGREGADOR,
        comision_porcentual=Decimal("0.0190"),
        comision_fija=900,
        monto_minimo=1_500,
        monto_maximo=50_000_000,
        campos_requeridos=("token_tarjeta",),
    ),
    Pago.Metodo.PSE: EspecificacionMetodoPago(
        codigo=Pago.Metodo.PSE,
        etiqueta="PSE (débito desde cuenta bancaria)",
        pasarela=PASARELA_AGREGADOR,
        comision_porcentual=Decimal("0.0000"),
        comision_fija=2_500,
        monto_minimo=5_000,
        monto_maximo=500_000_000,
        campos_requeridos=("banco", "tipo_persona", "documento_pagador"),
        confirmacion_inmediata=False,
    ),
    Pago.Metodo.BILLETERA_DIGITAL: EspecificacionMetodoPago(
        codigo=Pago.Metodo.BILLETERA_DIGITAL,
        etiqueta="Billetera digital",
        pasarela=PASARELA_AGREGADOR,
        comision_porcentual=Decimal("0.0175"),
        comision_fija=0,
        monto_minimo=1_000,
        monto_maximo=10_000_000,
        campos_requeridos=("telefono",),
    ),
    Pago.Metodo.EFECTIVO: EspecificacionMetodoPago(
        codigo=Pago.Metodo.EFECTIVO,
        etiqueta="Efectivo en corresponsal",
        pasarela=PASARELA_CORRESPONSAL,
        comision_porcentual=Decimal("0.0000"),
        comision_fija=4_500,
        monto_minimo=5_000,
        # Los corresponsales bancarios no reciben sumas grandes en efectivo:
        # el tope existe por control de lavado de activos, no por capricho.
        monto_maximo=4_000_000,
        campos_requeridos=("documento_pagador",),
        confirmacion_inmediata=False,
    ),
}


def obtener_especificacion(codigo) -> EspecificacionMetodoPago:
    """Devuelve la especificación de `codigo`.

    Raises:
        MetodoPagoNoSoportadoError: el código no está en el catálogo.
    """
    clave = str(codigo or "").strip().upper()
    try:
        return CATALOGO_METODOS[clave]
    except KeyError:
        raise MetodoPagoNoSoportadoError(clave, sorted(CATALOGO_METODOS)) from None


def metodos_disponibles(monto=None) -> list:
    """Métodos del catálogo, filtrados por el monto cuando se indica.

    Sirve para que la interfaz no ofrezca "efectivo en corresponsal" para un
    carro de $85.000.000: el método existe, pero no aplica a ese monto.
    """
    especificaciones = list(CATALOGO_METODOS.values())
    if monto is None:
        return especificaciones
    return [
        especificacion
        for especificacion in especificaciones
        if especificacion.esta_dentro_de_limites(monto)
    ]
