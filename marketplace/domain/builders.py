"""Builder del dominio para la publicación de un carro.

Patrón Creacional: Builder con *Fluent Interface*.

Motivación: un `Carro` publicable tiene 9 atributos y varias invariantes
cruzadas (un carro NUEVO no puede tener 80.000 km, la placa debe cumplir el
formato colombiano, el precio no puede ser cero). Construirlo con
`Carro(**request.POST)` permite crear objetos inválidos y obliga a repartir
las validaciones por toda la aplicación.

`CarroBuilder` concentra esas invariantes en un único lugar y **garantiza que
`build()` solo devuelve instancias válidas**. La persistencia no es
responsabilidad del Builder: devuelve un objeto en memoria y es el Service
Layer quien decide cuándo llamar a `.save()`.
"""

import re

from ..models import Carro
from .exceptions import ArticuloInvalidoError

#: Placas colombianas: 3 letras + 2 dígitos + 1 dígito o letra (ABC123, ABC12D).
PATRON_PLACA = re.compile(r"^[A-Z]{3}\d{2}[A-Z0-9]$")

#: Un vehículo declarado NUEVO no puede superar este kilometraje.
KM_MAXIMO_NUEVO = 1_000

#: Documentos obligatorios para poder publicar un vehículo.
DOCUMENTOS_OBLIGATORIOS = frozenset({"SOAT", "TECNOMECANICA"})


class CarroBuilder:
    """Construye un `Carro` válido paso a paso.

    Uso::

        carro = (CarroBuilder()
                 .para_vendedor(vendedor)
                 .con_identificacion("ABC123", "Mazda", "CX-30")
                 .con_caracteristicas("Rojo", 15_000, "USADO")
                 .con_precio(85_000_000)
                 .con_documentos(documentos)
                 .build())
    """

    def __init__(self):
        self._vendedor = None
        self._placa = ""
        self._marca = ""
        self._modelo = ""
        self._color = ""
        self._estado = ""
        self._kilometraje = None
        self._precio = None
        self._descripcion = ""
        self._documentos = []

    # ------------------------------------------------------------------
    # Pasos de construcción (cada uno devuelve self -> Fluent Interface)
    # ------------------------------------------------------------------

    def para_vendedor(self, vendedor):
        self._vendedor = vendedor
        return self

    def con_identificacion(self, placa, marca, modelo):
        self._placa = (placa or "").strip().upper()
        self._marca = (marca or "").strip()
        self._modelo = (modelo or "").strip()
        return self

    def con_caracteristicas(self, color, kilometraje, estado):
        self._color = (color or "").strip()
        self._kilometraje = kilometraje
        self._estado = (estado or "").strip().upper()
        return self

    def con_precio(self, precio):
        self._precio = precio
        return self

    def con_descripcion(self, descripcion):
        self._descripcion = (descripcion or "").strip()
        return self

    def con_documentos(self, documentos):
        self._documentos = list(documentos or [])
        return self

    # ------------------------------------------------------------------
    # Construcción
    # ------------------------------------------------------------------

    def build(self) -> Carro:
        """Devuelve un `Carro` válido **sin persistir**.

        Raises:
            ArticuloInvalidoError: si alguna invariante no se cumple. Se
                reportan *todos* los errores encontrados, no solo el primero.
        """
        errores = self._validar()
        if errores:
            raise ArticuloInvalidoError(errores)

        return Carro(
            vendedor=self._vendedor,
            placa=self._placa,
            marca=self._marca,
            modelo=self._modelo,
            estado=self._estado,
            color=self._color,
            kilometraje=self._kilometraje,
            descripcion=self._descripcion,
            precio=self._precio,
        )

    # ------------------------------------------------------------------
    # Invariantes
    # ------------------------------------------------------------------

    def _validar(self):
        errores = []

        if self._vendedor is None:
            errores.append("El artículo debe pertenecer a un vendedor.")

        if not PATRON_PLACA.match(self._placa):
            errores.append(
                f"La placa '{self._placa}' no cumple el formato colombiano (ABC123)."
            )

        if not self._marca:
            errores.append("La marca es obligatoria.")
        if not self._modelo:
            errores.append("El modelo es obligatorio.")
        if not self._color:
            errores.append("El color es obligatorio.")

        if self._estado not in Carro.Estado.values:
            errores.append(f"El estado '{self._estado}' no es válido (NUEVO o USADO).")

        errores.extend(self._validar_kilometraje())
        errores.extend(self._validar_precio())
        errores.extend(self._validar_documentos())

        return errores

    def _validar_kilometraje(self):
        if not isinstance(self._kilometraje, int) or self._kilometraje < 0:
            return ["El kilometraje debe ser un entero mayor o igual a cero."]
        if self._estado == Carro.Estado.NUEVO and self._kilometraje > KM_MAXIMO_NUEVO:
            return [
                f"Un carro NUEVO no puede superar {KM_MAXIMO_NUEVO} km "
                f"(recibido: {self._kilometraje} km)."
            ]
        return []

    def _validar_precio(self):
        if not isinstance(self._precio, int) or self._precio <= 0:
            return ["El precio debe ser un entero positivo en pesos colombianos."]
        return []

    def _validar_documentos(self):
        tipos = {getattr(doc, "tipo_documento", None) for doc in self._documentos}
        faltantes = DOCUMENTOS_OBLIGATORIOS - tipos
        if faltantes:
            return [f"Faltan documentos obligatorios: {', '.join(sorted(faltantes))}."]
        return []
