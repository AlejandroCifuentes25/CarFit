"""Serializers de cuentas (login) y del CRUD administrativo.

Antes vivían en `marketplace/serializers.py`, fuera de la carpeta `api/`,
mientras que los de pagos y carrito sí estaban aquí: dos convenciones para
el mismo tipo de cosa. Se unifican en un solo lugar para que toda la API
cuelgue de `marketplace/api/`, tal como ya lo describe la wiki del proyecto.
"""

from rest_framework import serializers

from ..domain.builders import KM_MAXIMO_NUEVO
from ..models import Carro, Cliente, Vendedor


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
