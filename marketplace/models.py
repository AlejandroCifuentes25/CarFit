"""Modelos de persistencia de CarFit.

Corresponden al diagrama de clases del proyecto. Esta capa es *solo*
persistencia: no contiene reglas de negocio. Las invariantes del dominio
viven en `marketplace/domain/builders.py`.
"""

from django.utils.translation import gettext, gettext_lazy as _

from django.conf import settings
from django.db import models
from django.utils import timezone


class Vendedor(models.Model):
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name=_('Usuario'),
        on_delete=models.CASCADE,
        related_name="vendedor",
    )
    nombre = models.CharField(verbose_name=_('Nombre'), max_length=120)
    correo = models.EmailField(verbose_name=_('Correo'))
    direccion = models.CharField(verbose_name=_('Dirección'), max_length=200)
    numero_tel = models.CharField(verbose_name=_('Teléfono'), max_length=20)
    resena = models.PositiveIntegerField(verbose_name=_('Calificación'), default=0)

    class Meta:
        verbose_name = _('Vendedor')
        verbose_name_plural = _('Vendedores')

    def __str__(self):
        return self.nombre


class Cliente(models.Model):
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        verbose_name=_('Usuario'),
        on_delete=models.CASCADE,
        related_name="cliente",
    )
    nombre = models.CharField(verbose_name=_('Nombre'), max_length=120)
    correo = models.EmailField(verbose_name=_('Correo'))
    direccion = models.CharField(verbose_name=_('Dirección'), max_length=200)
    numero_tel = models.CharField(verbose_name=_('Teléfono'), max_length=20)

    class Meta:
        verbose_name = _('Cliente')
        verbose_name_plural = _('Clientes')

    def __str__(self):
        return self.nombre


class EventoNotificacion(models.Model):
    """Evento persistido en la misma transacción que el cambio de negocio."""

    clase = models.CharField(max_length=12)
    objeto_id = models.PositiveBigIntegerField()
    idioma = models.CharField(max_length=10)
    datos = models.JSONField(default=dict)
    creado_en = models.DateTimeField(verbose_name=_('Fecha de creación'), auto_now_add=True)
    enviado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["enviado_en", "id"], name="evento_pendiente_idx")]


class Carro(models.Model):
    class Estado(models.TextChoices):
        NUEVO = "NUEVO", _('Nuevo')
        USADO = "USADO", _('Usado')

    vendedor = models.ForeignKey(
        Vendedor, verbose_name=_('Vendedor'), on_delete=models.CASCADE, related_name="carros"
    )
    carrito_compra = models.ForeignKey(
        "CarritoCompra", verbose_name=_('Carrito'), on_delete=models.SET_NULL, related_name="carros",
        null=True, blank=True,
    )
    placa = models.CharField(verbose_name=_('Placa'), max_length=6, unique=True)
    marca = models.CharField(verbose_name=_('Marca'), max_length=60)
    modelo = models.CharField(verbose_name=_('Modelo'), max_length=60)
    estado = models.CharField(verbose_name=_('Estado'), max_length=10, choices=Estado.choices)
    color = models.CharField(verbose_name=_('Color'), max_length=40)
    kilometraje = models.PositiveIntegerField(verbose_name=_('Kilometraje'))
    descripcion = models.TextField(verbose_name=_('Descripción'), blank=True)
    precio = models.PositiveBigIntegerField(verbose_name=_('Precio'))
    puntaje = models.FloatField(verbose_name=_('Puntuación'), default=0.0)
    publicado_en = models.DateTimeField(verbose_name=_('Fecha de publicación'), auto_now_add=True)

    class Meta:
        verbose_name = _('Vehículo')
        verbose_name_plural = _('Vehículos')

    def __str__(self):
        return f"{self.marca} {self.modelo} ({self.placa})"


class Repuesto(models.Model):
    class Estado(models.TextChoices):
        NUEVO = "NUEVO", _('Nuevo')
        USADO = "USADO", _('Usado')

    vendedor = models.ForeignKey(
        Vendedor, verbose_name=_('Vendedor'), on_delete=models.CASCADE, related_name="repuestos"
    )
    carrito_compra = models.ForeignKey(
        "CarritoCompra", verbose_name=_('Carrito'), on_delete=models.SET_NULL, related_name="repuestos",
        null=True, blank=True,
    )
    tipo = models.CharField(verbose_name=_('Tipo'), max_length=80)
    modelo_carro = models.CharField(verbose_name=_('Modelo compatible'), max_length=80)
    precio = models.PositiveBigIntegerField(verbose_name=_('Precio'))
    numero_serie = models.CharField(verbose_name=_('Número de serie'), max_length=60, unique=True)
    estado = models.CharField(verbose_name=_('Estado'), max_length=10, choices=Estado.choices)

    class Meta:
        verbose_name = _('Repuesto')
        verbose_name_plural = _('Repuestos')

    def __str__(self):
        return f"{self.tipo} - {self.modelo_carro}"


class DocumentoCarro(models.Model):
    class Tipo(models.TextChoices):
        SOAT = "SOAT", _('SOAT')
        TECNOMECANICA = "TECNOMECANICA", _('Revisión tecnomecánica')
        TARJETA_PROPIEDAD = "TARJETA_PROPIEDAD", _('Tarjeta de propiedad')

    carro = models.ForeignKey(
        Carro, verbose_name=_('Vehículo'), on_delete=models.CASCADE, related_name="documentos"
    )
    tipo_documento = models.CharField(verbose_name=_('Tipo de documento'), max_length=20, choices=Tipo.choices)
    fecha_expedicion = models.DateField(verbose_name=_('Fecha de expedición'))
    fecha_vencimiento = models.DateField(verbose_name=_('Fecha de vencimiento'))
    archivo = models.FileField(verbose_name=_('Archivo'), upload_to="documentos/", blank=True, null=True)

    class Meta:
        verbose_name = _('Documento del vehículo')
        verbose_name_plural = _('Documentos de carros')

    def __str__(self):
        return gettext("%(tipo)s de %(placa)s") % {"tipo": self.get_tipo_documento_display(), "placa": self.carro.placa}


class Inventario(models.Model):
    vendedor = models.OneToOneField(
        Vendedor, verbose_name=_('Vendedor'), on_delete=models.CASCADE, related_name="inventario"
    )
    cantidad_repuesto = models.PositiveIntegerField(verbose_name=_('Cantidad de repuestos'), default=0)
    cantidad_carro = models.PositiveIntegerField(verbose_name=_('Cantidad de vehículos'), default=0)

    class Meta:
        verbose_name = _('Inventario')
        verbose_name_plural = _('Inventarios')

    def __str__(self):
        return gettext("Inventario de %(vendedor)s") % {"vendedor": self.vendedor.nombre}


class Resena(models.Model):
    class Tipo(models.TextChoices):
        COMPRA = "COMPRA", _("Experiencia de compra")
        ATENCION = "ATENCION", _("Atención del vendedor")
        VEHICULO = "VEHICULO", _("Estado del vehículo / repuesto")
        GENERAL = "GENERAL", _("Comentario general")

    contenido = models.TextField(verbose_name=_('Contenido'))
    autor = models.CharField(verbose_name=_('Autor'), max_length=120)
    tipo = models.CharField(verbose_name=_('Tipo'), max_length=40, choices=Tipo.choices)
    calificacion = models.PositiveSmallIntegerField(verbose_name=_('Calificación'), default=5)
    vendedor = models.ForeignKey(
        Vendedor, verbose_name=_('Vendedor'), on_delete=models.CASCADE, related_name="resenas", null=True, blank=True
    )
    cliente = models.ForeignKey(
        Cliente, verbose_name=_('Cliente'), on_delete=models.SET_NULL, related_name="resenas", null=True, blank=True
    )
    carro = models.ForeignKey(
        Carro, verbose_name=_('Vehículo'), on_delete=models.CASCADE, related_name="resenas", null=True, blank=True
    )
    creado_en = models.DateTimeField(verbose_name=_('Fecha de creación'), default=timezone.now)

    class Meta:
        verbose_name = _('Reseña')
        verbose_name_plural = _('Reseñas')
        ordering = ["-creado_en", "-pk"]

    def __str__(self):
        return gettext("Reseña de %(autor)s") % {"autor": self.autor}


class Pago(models.Model):
    """Pago de un artículo del marketplace.

    Persistencia pura. Los importes (`comision`, `total`) llegan ya
    calculados por la especificación del método de pago
    (`domain/metodos_pago.py`) y el `estado` lo fija el Service Layer con la
    respuesta de la pasarela: este modelo no calcula ni decide nada.

    `referencia` es la clave de idempotencia del pago. Es única, así que dos
    envíos del mismo formulario (o un reintento de la pasarela) no pueden
    generar dos cobros: la base de datos lo impide.
    """

    class Metodo(models.TextChoices):
        TARJETA_CREDITO = "TARJETA_CREDITO", _('Tarjeta de crédito')
        TARJETA_DEBITO = "TARJETA_DEBITO", _('Tarjeta débito')
        PSE = "PSE", _('PSE (débito desde cuenta bancaria)')
        BILLETERA_DIGITAL = "BILLETERA_DIGITAL", _('Billetera digital')
        EFECTIVO = "EFECTIVO", _('Efectivo en corresponsal')

    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", _('Pendiente de confirmación')
        APROBADO = "APROBADO", _('Aprobado')
        RECHAZADO = "RECHAZADO", _('Rechazado')
        ANULADO = "ANULADO", _('Anulado')
        REEMBOLSADO = "REEMBOLSADO", _('Reembolsado')

    cliente = models.ForeignKey(Cliente, verbose_name=_('Cliente'), on_delete=models.PROTECT, related_name="pagos")
    carro = models.ForeignKey(
        Carro, verbose_name=_('Vehículo'), on_delete=models.PROTECT, related_name="pagos", null=True, blank=True
    )
    repuesto = models.ForeignKey(
        Repuesto, verbose_name=_('Repuesto'), on_delete=models.PROTECT, related_name="pagos", null=True, blank=True
    )
    referencia = models.CharField(verbose_name=_('Referencia'), max_length=60, unique=True)
    precio = models.PositiveBigIntegerField(verbose_name=_('Precio'))
    comision = models.PositiveBigIntegerField(verbose_name=_('Comisión'), default=0)
    total = models.PositiveBigIntegerField(verbose_name=_('Total'), default=0)
    moneda = models.CharField(verbose_name=_('Moneda'), max_length=3, default="COP")
    cuotas = models.PositiveSmallIntegerField(verbose_name=_('Cuotas'), default=1)
    metodo_pago = models.CharField(verbose_name=_('Método de pago'), max_length=30, choices=Metodo.choices)
    estado = models.CharField(
        verbose_name=_('Estado'),
        max_length=20, choices=Estado.choices, default=Estado.PENDIENTE
    )
    pasarela = models.CharField(verbose_name=_('Pasarela de pago'), max_length=40, blank=True)
    referencia_pasarela = models.CharField(verbose_name=_('Referencia de la pasarela'), max_length=80, blank=True)
    codigo_autorizacion = models.CharField(verbose_name=_('Autorización'), max_length=60, blank=True)
    mensaje = models.CharField(verbose_name=_('Mensaje'), max_length=200, blank=True)
    fecha = models.DateTimeField(verbose_name=_('Fecha'), auto_now_add=True)
    actualizado_en = models.DateTimeField(verbose_name=_('Última actualización'), auto_now=True)

    class Meta:
        verbose_name = _('Pago')
        verbose_name_plural = _('Pagos')
        ordering = ["-fecha"]
        # El historial de un cliente y el tablero de pagos por estado son las
        # dos consultas que la API hace todo el tiempo.
        indexes = [
            models.Index(fields=["cliente", "estado"], name="pago_cliente_estado_idx")
        ]

    @property
    def mensaje_localizado(self):
        return gettext(self.mensaje) if self.mensaje else ""

    def __str__(self):
        return gettext("Pago %(referencia)s - %(estado)s") % {"referencia": self.referencia, "estado": self.get_estado_display()}


class TransaccionPago(models.Model):
    """Bitácora de cada interacción con una pasarela de pago.

    Un `Pago` puede tener varias transacciones: el intento inicial, las
    consultas de estado y la confirmación asíncrona (PSE y efectivo no
    responden aprobado en el momento). Sirve de evidencia de auditoría
    cuando un cliente reclama por un cobro.
    """

    class Operacion(models.TextChoices):
        PROCESAR = "PROCESAR", _('Procesar')
        CONSULTAR = "CONSULTAR", _('Consultar')
        CONFIRMAR = "CONFIRMAR", _('Confirmar')

    pago = models.ForeignKey(
        Pago, verbose_name=_('Pago'), on_delete=models.CASCADE, related_name="transacciones"
    )
    operacion = models.CharField(verbose_name=_('Operación'), max_length=20, choices=Operacion.choices)
    pasarela = models.CharField(verbose_name=_('Pasarela de pago'), max_length=40)
    estado_resultante = models.CharField(verbose_name=_('Estado resultante'), max_length=20, choices=Pago.Estado.choices)
    codigo_autorizacion = models.CharField(verbose_name=_('Autorización'), max_length=60, blank=True)
    mensaje = models.CharField(verbose_name=_('Mensaje'), max_length=200, blank=True)
    creado_en = models.DateTimeField(verbose_name=_('Fecha de creación'), auto_now_add=True)

    class Meta:
        verbose_name = _('Transacción de pago')
        verbose_name_plural = _('Transacciones de pago')
        ordering = ["creado_en"]

    def __str__(self):
        return gettext("%(operacion)s de %(referencia)s → %(estado)s") % {
            "operacion": self.get_operacion_display(), "referencia": self.pago.referencia,
            "estado": self.get_estado_resultante_display(),
        }


class CarritoCompra(models.Model):
    cliente = models.OneToOneField(
        Cliente,
        verbose_name=_('Cliente'),
        on_delete=models.CASCADE,
        related_name="carrito_compra",
        null=True,
        blank=True,
    )
    cantidad_producto = models.PositiveIntegerField(verbose_name=_('Cantidad de artículos'), default=0)
    precio_total = models.PositiveBigIntegerField(verbose_name=_('Precio total'), default=0)

    class Meta:
        verbose_name = _('Carrito de compras')
        verbose_name_plural = _('Carritos de compras')

    def __str__(self):
        return gettext("Carrito de compras #%(id)s") % {"id": self.pk}
