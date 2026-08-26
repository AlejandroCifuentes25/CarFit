"""Serializers de DRF.

Igual que forms.py, solo validan *formato* de entrada/salida. Las
invariantes de negocio de Carro viven en domain/builders.py.
"""

from rest_framework import serializers
from .models import Carro, Repuesto, Cliente, Vendedor


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


class RepuestoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Repuesto
        fields = ["id", "vendedor", "tipo", "modelo_carro", "numero_serie", "estado", "precio"]
        read_only_fields = ["id", "vendedor"]
