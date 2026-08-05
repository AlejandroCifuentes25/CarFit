"""Modelos de persistencia de CarFit.

Corresponden al diagrama de clases del proyecto. Esta capa es *solo*
persistencia: no contiene reglas de negocio. Las invariantes del dominio
viven en `marketplace/domain/builders.py`.
"""

from django.conf import settings
from django.db import models


class Vendedor(models.Model):
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="vendedor",
    )
    nombre = models.CharField(max_length=120)
    correo = models.EmailField()
    direccion = models.CharField(max_length=200)
    numero_tel = models.CharField(max_length=20)
    resena = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.nombre


class Cliente(models.Model):
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cliente",
    )
    nombre = models.CharField(max_length=120)
    correo = models.EmailField()
    direccion = models.CharField(max_length=200)
    numero_tel = models.CharField(max_length=20)

    def __str__(self):
        return self.nombre


class Carro(models.Model):
    class Estado(models.TextChoices):
        NUEVO = "NUEVO", "Nuevo"
        USADO = "USADO", "Usado"

    vendedor = models.ForeignKey(
        Vendedor, on_delete=models.CASCADE, related_name="carros"
    )
    placa = models.CharField(max_length=6, unique=True)
    marca = models.CharField(max_length=60)
    modelo = models.CharField(max_length=60)
    estado = models.CharField(max_length=10, choices=Estado.choices)
    color = models.CharField(max_length=40)
    kilometraje = models.PositiveIntegerField()
    descripcion = models.TextField(blank=True)
    precio = models.PositiveBigIntegerField()
    puntaje = models.FloatField(default=0.0)
    publicado_en = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.marca} {self.modelo} ({self.placa})"


class Repuesto(models.Model):
    class Estado(models.TextChoices):
        NUEVO = "NUEVO", "Nuevo"
        USADO = "USADO", "Usado"

    vendedor = models.ForeignKey(
        Vendedor, on_delete=models.CASCADE, related_name="repuestos"
    )
    tipo = models.CharField(max_length=80)
    modelo_carro = models.CharField(max_length=80)
    precio = models.PositiveBigIntegerField()
    numero_serie = models.CharField(max_length=60, unique=True)
    estado = models.CharField(max_length=10, choices=Estado.choices)

    def __str__(self):
        return f"{self.tipo} - {self.modelo_carro}"


class DocumentoCarro(models.Model):
    class Tipo(models.TextChoices):
        SOAT = "SOAT", "SOAT"
        TECNOMECANICA = "TECNOMECANICA", "Revisión tecnomecánica"
        TARJETA_PROPIEDAD = "TARJETA_PROPIEDAD", "Tarjeta de propiedad"

    carro = models.ForeignKey(
        Carro, on_delete=models.CASCADE, related_name="documentos"
    )
    tipo_documento = models.CharField(max_length=20, choices=Tipo.choices)
    fecha_expedicion = models.DateField()
    fecha_vencimiento = models.DateField()
    archivo = models.FileField(upload_to="documentos/", blank=True, null=True)

    def __str__(self):
        return f"{self.tipo_documento} de {self.carro.placa}"


class Inventario(models.Model):
    vendedor = models.OneToOneField(
        Vendedor, on_delete=models.CASCADE, related_name="inventario"
    )
    cantidad_repuesto = models.PositiveIntegerField(default=0)
    cantidad_carro = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"Inventario de {self.vendedor.nombre}"


class Resena(models.Model):
    contenido = models.TextField()
    autor = models.CharField(max_length=120)
    tipo = models.CharField(max_length=40)
    carro = models.ForeignKey(
        Carro, on_delete=models.CASCADE, related_name="resenas", null=True, blank=True
    )

    def __str__(self):
        return f"Reseña de {self.autor}"


class Pago(models.Model):
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="pagos")
    carro = models.ForeignKey(
        Carro, on_delete=models.PROTECT, related_name="pagos", null=True, blank=True
    )
    precio = models.PositiveBigIntegerField()
    fecha = models.DateTimeField(auto_now_add=True)
    metodo_pago = models.CharField(max_length=40)
    estado = models.CharField(max_length=20, default="PENDIENTE")

    def __str__(self):
        return f"Pago #{self.pk} - {self.estado}"
