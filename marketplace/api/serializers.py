"""Serializers de la API (cuentas, carrito y pagos).

Los serializers validan **formato**, no negocio: que `cuotas` sea un entero,
que `referencia` no pase de 60 caracteres, que `carro` venga como número.
Que 36 cuotas sean demasiadas para PSE, o que el monto quede fuera del rango
del método, lo decide el dominio (`domain/metodos_pago.py` y `PagoBuilder`).

Esa separación es deliberada: las mismas reglas de negocio deben aplicarse
cuando un pago entra por la API, por un comando de consola o por una tarea
programada, y ninguno de esos caminos pasa por un serializer.
"""

from rest_framework import serializers

from ..domain.builders import KM_MAXIMO_NUEVO
from ..models import Carro, Cliente, Pago, Vendedor


TIPOS_ARTICULO = (("carro", "Carro"), ("repuesto", "Repuesto"))


# ---------------------------------------------------------------------
# Cuentas: login y CRUD administrativo
# ---------------------------------------------------------------------


class LoginSerializer(serializers.Serializer):
    """Entrada del endpoint de inicio de sesión."""

    username = serializers.CharField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})


class VendedorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vendedor
        fields = ["id", "usuario", "nombre", "correo", "direccion", "numero_tel", "resena"]
        read_only_fields = ["resena"]


class ClienteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cliente
        fields = ["id", "usuario", "nombre", "correo", "direccion", "numero_tel"]


class CarroSerializer(serializers.ModelSerializer):
    class Meta:
        model = Carro
        fields = [
            "id",
            "vendedor",
            "placa",
            "marca",
            "modelo",
            "estado",
            "color",
            "kilometraje",
            "descripcion",
            "precio",
            "puntaje",
            "publicado_en",
        ]
        read_only_fields = ["puntaje", "publicado_en"]

    def validate_placa(self, valor):
        return valor.strip().upper()

    def validate(self, datos):
        instancia = self.instance
        estado = datos.get("estado", getattr(instancia, "estado", None))
        kilometraje = datos.get("kilometraje", getattr(instancia, "kilometraje", None))

        if estado == Carro.Estado.NUEVO and kilometraje is not None and kilometraje > KM_MAXIMO_NUEVO:
            raise serializers.ValidationError(
                f"Un carro NUEVO no puede superar {KM_MAXIMO_NUEVO} km "
                f"(recibido: {kilometraje} km)."
            )
        return datos


# ---------------------------------------------------------------------
# Carrito de compras
# ---------------------------------------------------------------------


class MovimientoCarritoSerializer(serializers.Serializer):
    tipo_articulo = serializers.ChoiceField(choices=TIPOS_ARTICULO)
    articulo_id = serializers.IntegerField(min_value=1)


class ArticuloCarritoSerializer(serializers.Serializer):
    accion = serializers.CharField()
    tipo_articulo = serializers.CharField()
    articulo_id = serializers.IntegerField()
    titulo = serializers.CharField()
    precio = serializers.IntegerField()
    vendedor_id = serializers.IntegerField()
    vendedor_nombre = serializers.CharField()
    detalle = serializers.DictField()


class ResumenCarritoSerializer(serializers.Serializer):
    carrito_id = serializers.IntegerField()
    cantidad_producto = serializers.IntegerField()
    precio_total = serializers.IntegerField()


class RespuestaMovimientoCarritoSerializer(serializers.Serializer):
    articulo = ArticuloCarritoSerializer()
    carrito = ResumenCarritoSerializer()


class RespuestaCarritoSerializer(serializers.Serializer):
    carrito = ResumenCarritoSerializer()


class RespuestaEstadoCarritoSerializer(serializers.Serializer):
    estado = serializers.CharField()
    carrito = ResumenCarritoSerializer()


class EspecificacionMetodoPagoSerializer(serializers.Serializer):
    """Expone un método del catálogo tal como lo define el dominio.

    No es un `ModelSerializer` porque un método de pago no es una tabla: es
    un objeto de valor del dominio.
    """

    codigo = serializers.CharField(read_only=True)
    etiqueta = serializers.CharField(read_only=True)
    comision_porcentual = serializers.DecimalField(
        max_digits=6, decimal_places=4, read_only=True
    )
    comision_fija = serializers.IntegerField(read_only=True)
    monto_minimo = serializers.IntegerField(read_only=True)
    monto_maximo = serializers.IntegerField(read_only=True)
    campos_requeridos = serializers.ListField(
        child=serializers.CharField(), read_only=True
    )
    permite_cuotas = serializers.BooleanField(read_only=True)
    cuotas_maximas = serializers.IntegerField(read_only=True)
    confirmacion_inmediata = serializers.BooleanField(read_only=True)


class CrearPagoSerializer(serializers.Serializer):
    """Entrada de `POST /api/pagos/`.

    `metodo_pago` es un `CharField` y no un `ChoiceField` a propósito: el
    catálogo de métodos soportados pertenece al dominio, y es él quien debe
    rechazar un método desconocido con su propio mensaje. Duplicar la lista
    aquí obligaría a mantener dos fuentes de verdad.
    """

    metodo_pago = serializers.CharField(max_length=30)
    carro = serializers.IntegerField(required=False, min_value=1)
    repuesto = serializers.IntegerField(required=False, min_value=1)
    cuotas = serializers.IntegerField(required=False, min_value=1, default=1)
    referencia = serializers.CharField(
        required=False, max_length=60, allow_blank=True,
        help_text="Referencia de idempotencia. Si no se envía, CarFit la genera.",
    )

    # Datos propios de cada método. Se declaran opcionales porque cuáles son
    # obligatorios depende del método elegido, y esa es una regla de negocio:
    # la aplica la especificación del método, no este formulario.
    token_tarjeta = serializers.CharField(
        required=False, max_length=120, allow_blank=True
    )
    banco = serializers.CharField(required=False, max_length=60, allow_blank=True)
    tipo_persona = serializers.CharField(
        required=False, max_length=20, allow_blank=True
    )
    documento_pagador = serializers.CharField(
        required=False, max_length=20, allow_blank=True
    )
    telefono = serializers.CharField(required=False, max_length=20, allow_blank=True)


#: Campos que salen tal cual de la tabla de pagos.
CAMPOS_DEL_PAGO = (
    "id",
    "referencia",
    "estado",
    "metodo_pago",
    "precio",
    "comision",
    "total",
    "moneda",
    "cuotas",
    "pasarela",
    "referencia_pasarela",
    "codigo_autorizacion",
    "mensaje",
    "fecha",
    "actualizado_en",
)

#: Campos derivados que la interfaz agradece recibir ya resueltos.
CAMPOS_DERIVADOS = ("estado_etiqueta", "metodo_pago_etiqueta", "articulo")


class PagoSerializer(serializers.ModelSerializer):
    """Salida de la API. Solo lectura: un pago no se edita por PATCH.

    Un pago se corrige con otra operación de negocio (una anulación, un
    reembolso), nunca reescribiendo sus campos. Por eso todos los campos
    del modelo van como solo lectura.

    Nunca expone los datos sensibles del método (token de tarjeta, cuenta
    bancaria): esos ni siquiera se guardan.
    """

    metodo_pago_etiqueta = serializers.CharField(
        source="get_metodo_pago_display", read_only=True
    )
    estado_etiqueta = serializers.CharField(source="get_estado_display", read_only=True)
    articulo = serializers.SerializerMethodField()

    class Meta:
        model = Pago
        fields = CAMPOS_DEL_PAGO + CAMPOS_DERIVADOS
        read_only_fields = CAMPOS_DEL_PAGO

    def get_articulo(self, pago) -> dict:
        """Descripción del artículo pagado, sea carro o repuesto."""
        articulo = pago.carro or pago.repuesto
        if articulo is None:
            return None
        return {
            "tipo": "CARRO" if pago.carro_id else "REPUESTO",
            "id": articulo.pk,
            "descripcion": str(articulo),
        }


class FacturaSerializer(serializers.Serializer):
    """Salida de `GET /api/pagos/<referencia>/factura/`.

    Serializa el objeto de valor `Factura` del dominio (no un modelo): no
    hay tabla de facturas, se reconstruye a partir del `Pago` cada vez.
    """

    numero = serializers.CharField(read_only=True)
    fecha_emision = serializers.DateTimeField(read_only=True)
    referencia_pago = serializers.CharField(read_only=True)
    cliente_nombre = serializers.CharField(read_only=True)
    cliente_correo = serializers.CharField(read_only=True)
    vendedor_nombre = serializers.CharField(read_only=True)
    articulo_descripcion = serializers.CharField(read_only=True)
    metodo_pago = serializers.CharField(read_only=True)
    subtotal = serializers.IntegerField(read_only=True)
    comision = serializers.IntegerField(read_only=True)
    total = serializers.IntegerField(read_only=True)
    moneda = serializers.CharField(read_only=True)
    cuotas = serializers.IntegerField(read_only=True)
    codigo_autorizacion = serializers.CharField(read_only=True)
