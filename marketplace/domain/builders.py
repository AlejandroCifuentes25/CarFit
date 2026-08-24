"""Builders del dominio: publicación de un carro y registro de un pago.

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
import uuid

from ..models import Carro, Pago
from .exceptions import ArticuloInvalidoError, PagoInvalidoError
from .metodos_pago import obtener_especificacion

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


#: Prefijo de las referencias de pago generadas por CarFit. Facilita
#: rastrearlas en los paneles de la pasarela entre miles de transacciones.
PREFIJO_REFERENCIA = "CF"


class PagoBuilder:
    """Construye un `Pago` válido y con importes ya calculados.

    Un pago es la entidad con más invariantes cruzadas del sistema: el monto
    depende del artículo, la comisión depende del método, los datos
    obligatorios dependen del método, las cuotas dependen de si el método
    las acepta y el artículo comprado puede ser un carro o un repuesto pero
    nunca ambos. Armarlo con `Pago(**request.data)` significa aceptar cobros
    de $0, tarjetas sin token o pagos a 48 cuotas por PSE.

    El Builder reúne esas reglas en un solo lugar y garantiza que `build()`
    solo devuelva pagos consistentes. No persiste ni habla con la pasarela:
    eso lo decide el Service Layer.

    Uso::

        pago = (PagoBuilder()
                .para_cliente(cliente)
                .por_carro(carro)
                .con_metodo("TARJETA_CREDITO", {"token_tarjeta": "tok_123"})
                .con_cuotas(12)
                .build())
    """

    def __init__(self):
        self._cliente = None
        self._carro = None
        self._repuesto = None
        self._metodo = ""
        self._datos_metodo = {}
        self._cuotas = 1
        self._referencia = ""
        self._moneda = "COP"

    # ------------------------------------------------------------------
    # Pasos de construcción (cada uno devuelve self -> Fluent Interface)
    # ------------------------------------------------------------------

    def para_cliente(self, cliente):
        self._cliente = cliente
        return self

    def por_carro(self, carro):
        self._carro = carro
        return self

    def por_repuesto(self, repuesto):
        self._repuesto = repuesto
        return self

    def con_metodo(self, metodo, datos=None):
        self._metodo = str(metodo or "").strip().upper()
        self._datos_metodo = dict(datos or {})
        return self

    def con_cuotas(self, cuotas):
        self._cuotas = cuotas
        return self

    def con_referencia(self, referencia):
        """Fija la referencia de idempotencia.

        Si no se llama, `build()` genera una. Enviarla desde el cliente es
        lo que permite reintentar un pago sin riesgo de cobrar dos veces.
        """
        self._referencia = str(referencia or "").strip()
        return self

    def con_moneda(self, moneda):
        self._moneda = str(moneda or "").strip().upper()
        return self

    # ------------------------------------------------------------------
    # Construcción
    # ------------------------------------------------------------------

    def build(self) -> Pago:
        """Devuelve un `Pago` en estado PENDIENTE y **sin persistir**.

        Raises:
            PagoInvalidoError: si alguna invariante no se cumple. Se
                reportan *todos* los errores encontrados, no solo el primero.
        """
        errores = self._validar()
        if errores:
            raise PagoInvalidoError(errores)

        especificacion = self._especificacion()
        monto = self._monto()

        return Pago(
            cliente=self._cliente,
            carro=self._carro,
            repuesto=self._repuesto,
            referencia=self._referencia or self._generar_referencia(),
            precio=monto,
            comision=especificacion.calcular_comision(monto),
            total=especificacion.calcular_total(monto),
            moneda=self._moneda,
            cuotas=self._cuotas,
            metodo_pago=especificacion.codigo,
            estado=Pago.Estado.PENDIENTE,
        )

    def datos_metodo(self) -> dict:
        """Datos sensibles del método (token, banco, teléfono).

        Viajan a la pasarela pero **no** se guardan en la base de datos: un
        token de tarjeta almacenado es una fuga de datos esperando ocurrir.
        Por eso el `Pago` que devuelve `build()` no los contiene.
        """
        return dict(self._datos_metodo)

    # ------------------------------------------------------------------
    # Invariantes
    # ------------------------------------------------------------------

    def _especificacion(self):
        """Especificación del método, o `None` si el método no es válido."""
        try:
            return obtener_especificacion(self._metodo)
        except PagoInvalidoError:
            return None

    def _articulo(self):
        return self._carro or self._repuesto

    def _monto(self):
        """El monto no lo elige el comprador: lo fija el precio publicado."""
        articulo = self._articulo()
        return getattr(articulo, "precio", None)

    def _generar_referencia(self):
        return f"{PREFIJO_REFERENCIA}-{uuid.uuid4().hex[:20]}".upper()

    def _validar(self):
        errores = []

        if self._cliente is None:
            errores.append("El pago debe estar asociado a un cliente.")

        errores.extend(self._validar_articulo())
        errores.extend(self._validar_referencia())

        especificacion = self._especificacion()
        if especificacion is None:
            # Sin método válido no tiene sentido validar comisión ni cuotas:
            # se reporta lo que se sabe y se corta aquí.
            errores.append(
                f"El método de pago '{self._metodo}' no está soportado."
            )
            return errores

        errores.extend(self._validar_monto(especificacion))
        errores.extend(self._validar_cuotas(especificacion))
        errores.extend(self._validar_datos_metodo(especificacion))

        return errores

    def _validar_articulo(self):
        if self._carro is not None and self._repuesto is not None:
            return ["Un pago cubre un solo artículo: o un carro o un repuesto."]
        if self._articulo() is None:
            return ["El pago debe referirse a un carro o a un repuesto."]
        return self._validar_no_es_venta_a_si_mismo()

    def _validar_no_es_venta_a_si_mismo(self):
        """Nadie se compra su propio artículo para inflarse las reseñas."""
        vendedor = getattr(self._articulo(), "vendedor", None)
        usuario_vendedor = getattr(vendedor, "usuario_id", None)
        usuario_comprador = getattr(self._cliente, "usuario_id", None)
        if usuario_vendedor is not None and usuario_vendedor == usuario_comprador:
            return ["Un usuario no puede comprar su propio artículo."]
        return []

    def _validar_referencia(self):
        if self._referencia and len(self._referencia) > 60:
            return ["La referencia de pago no puede superar los 60 caracteres."]
        return []

    def _validar_monto(self, especificacion):
        monto = self._monto()
        if not isinstance(monto, int) or isinstance(monto, bool) or monto <= 0:
            return ["El artículo no tiene un precio válido en pesos colombianos."]
        if not especificacion.esta_dentro_de_limites(monto):
            return [
                f"{especificacion.etiqueta} solo opera entre "
                f"${especificacion.monto_minimo:,} y "
                f"${especificacion.monto_maximo:,} COP "
                f"(monto recibido: ${monto:,})."
            ]
        return []

    def _validar_cuotas(self, especificacion):
        if not isinstance(self._cuotas, int) or isinstance(self._cuotas, bool):
            return ["El número de cuotas debe ser un entero."]
        if especificacion.cuotas_validas(self._cuotas):
            return []
        if not especificacion.permite_cuotas:
            return [f"{especificacion.etiqueta} no permite diferir el pago a cuotas."]
        return [
            f"{especificacion.etiqueta} admite entre 1 y "
            f"{especificacion.cuotas_maximas} cuotas (recibido: {self._cuotas})."
        ]

    def _validar_datos_metodo(self, especificacion):
        faltantes = especificacion.campos_faltantes(self._datos_metodo)
        if faltantes:
            return [
                f"{especificacion.etiqueta} exige estos datos: "
                f"{', '.join(faltantes)}."
            ]
        return []
