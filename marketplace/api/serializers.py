"""Serializadores de la API del marketplace.

Estos serializadores usan la forma básica de DRF: los campos se declaran
directamente en la clase y solo se encargan de validar la entrada y traducir
la salida. No usamos una clase `Meta` personalizada porque eso no aporta valor
en `Serializer`; `Meta` es útil principalmente en `ModelSerializer`.

`TIPOS_ARTICULO` define las opciones permitidas para `tipo_articulo` y sirve
para validar la entrada con `ChoiceField`.
"""

from rest_framework import serializers

TIPOS_ARTICULO = (
    ("carro", "Carro"),
    ("repuesto", "Repuesto"),
)

class MovimientoCarritoSerializer(serializers.Serializer):
    """Valida la información recibida por el cliente."""

    tipo_articulo = serializers.ChoiceField(choices=TIPOS_ARTICULO)
    articulo_id = serializers.IntegerField(min_value=1)


class ArticuloCarritoSerializer(serializers.Serializer):
    """Transforma un artículo del carrito a JSON."""

    accion = serializers.CharField()
    tipo_articulo = serializers.CharField()
    articulo_id = serializers.IntegerField()
    titulo = serializers.CharField()
    precio = serializers.IntegerField()
    vendedor_id = serializers.IntegerField()
    vendedor_nombre = serializers.CharField()
    detalle = serializers.DictField()