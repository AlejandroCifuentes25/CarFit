"""Formulario de captura para la publicación de un artículo.

Deliberadamente es un `forms.Form` y **no** un `ModelForm`: el formulario
solo valida el *formato* de la entrada (que la fecha sea una fecha, que el
kilometraje sea un entero). Las reglas de *negocio* (que un carro NUEVO no
tenga 80.000 km, que la placa cumpla el formato colombiano) pertenecen al
`CarroBuilder`, para que también se apliquen cuando el artículo se cree
desde un comando de consola o una API, sin pasar por este formulario.
"""

from django import forms
from django.utils.translation import gettext_lazy as _

from .domain.metodos_pago import metodos_disponibles
from .models import Carro, DocumentoCarro


class CrearArticuloForm(forms.Form):
    placa = forms.CharField(max_length=6, label="Placa")
    marca = forms.CharField(max_length=60, label="Marca")
    modelo = forms.CharField(max_length=60, label="Modelo")
    color = forms.CharField(max_length=40, label="Color")
    estado = forms.ChoiceField(choices=Carro.Estado.choices, label="Estado")
    kilometraje = forms.IntegerField(min_value=0, label="Kilometraje")
    precio = forms.IntegerField(min_value=1, label="Precio (COP)")
    descripcion = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        label="Descripción",
    )

    soat_expedicion = forms.DateField(
        label="SOAT: expedición",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    soat_vencimiento = forms.DateField(
        label="SOAT: vencimiento",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    soat_archivo = forms.FileField(required=False, label="SOAT: archivo")

    tecnomecanica_expedicion = forms.DateField(
        label="Tecnomecánica: expedición",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    tecnomecanica_vencimiento = forms.DateField(
        label="Tecnomecánica: vencimiento",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    tecnomecanica_archivo = forms.FileField(
        required=False, label="Tecnomecánica: archivo"
    )

    def clean(self):
        from datetime import date

        datos = super().clean()
        hoy = date.today()

        soat_exp = datos.get("soat_expedicion")
        soat_ven = datos.get("soat_vencimiento")
        if soat_exp and soat_ven:
            if soat_exp > hoy:
                self.add_error(
                    "soat_expedicion",
                    "SOAT: La fecha de expedición no puede ser futura.",
                )
            if soat_ven <= soat_exp:
                self.add_error(
                    "soat_vencimiento",
                    "SOAT: La fecha de vencimiento debe ser posterior a la fecha de expedición.",
                )

        tec_exp = datos.get("tecnomecanica_expedicion")
        tec_ven = datos.get("tecnomecanica_vencimiento")
        if tec_exp and tec_ven:
            if tec_exp > hoy:
                self.add_error(
                    "tecnomecanica_expedicion",
                    "Revisión técnico-mecánica: La fecha de expedición no puede ser futura.",
                )
            if tec_ven <= tec_exp:
                self.add_error(
                    "tecnomecanica_vencimiento",
                    "Revisión técnico-mecánica: La fecha de vencimiento debe ser posterior a la fecha de expedición.",
                )
        return datos


class PagoForm(forms.Form):
    """Formulario para pagar un artículo publicado.

    Igual que `CrearArticuloForm`: valida formato, no negocio. Que un método
    exija un token de tarjeta, que el rango de cuotas dependa del método o
    que el monto esté fuera de límite lo decide `PagoBuilder`. Este
    formulario ni siquiera conoce esas reglas: solo pasa los datos.

    `metodo_pago` se filtra por el precio del artículo al construir el
    formulario: no tiene sentido ofrecerle a alguien pagar $85.000.000 en
    efectivo en un corresponsal.
    """

    metodo_pago = forms.ChoiceField(
        label="Método de pago", widget=forms.RadioSelect
    )
    cuotas = forms.IntegerField(
        min_value=1, required=False, initial=1, label="Cuotas"
    )
    referencia = forms.CharField(
        max_length=60, required=False, label="Referencia (opcional)"
    )

    # Datos propios de cada método. Cuáles son obligatorios lo decide la
    # especificación del método en el dominio, no este formulario.
    token_tarjeta = forms.CharField(
        max_length=120, required=False, label="Número de tarjeta / token"
    )
    banco = forms.CharField(max_length=60, required=False, label="Banco")
    tipo_persona = forms.ChoiceField(
        choices=[("NATURAL", "Persona natural"), ("JURIDICA", "Persona jurídica")],
        required=False,
        label="Tipo de persona",
    )
    documento_pagador = forms.CharField(
        max_length=20, required=False, label="Documento del pagador"
    )
    telefono = forms.CharField(max_length=20, required=False, label="Teléfono")

    def __init__(self, *args, monto=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.metodos = metodos_disponibles(monto)
        self.fields["metodo_pago"].choices = [
            (metodo.codigo, metodo.etiqueta) for metodo in self.metodos
        ]


class RegistroForm(forms.Form):
    ROL_CHOICES = [("CLIENTE", "Cliente — quiero comprar"), ("VENDEDOR", "Vendedor — quiero publicar vehículos")]
    rol = forms.ChoiceField(choices=ROL_CHOICES, label="Tipo de cuenta")
    username = forms.CharField(max_length=150, label="Usuario")
    password = forms.CharField(widget=forms.PasswordInput, label="Contraseña")
    password_confirmacion = forms.CharField(widget=forms.PasswordInput, label="Confirmar contraseña")
    nombre = forms.CharField(max_length=120, label="Nombre completo")
    correo = forms.EmailField(label="Correo")
    direccion = forms.CharField(max_length=200, label="Dirección")
    numero_tel = forms.CharField(max_length=20, label="Teléfono")

    def clean(self):
        datos = super().clean()
        if datos.get("password") and datos.get("password") != datos.get("password_confirmacion"):
            self.add_error("password_confirmacion", "Las contraseñas no coinciden.")
        return datos


class DocumentoCarroForm(forms.Form):
    tipo_documento = forms.ChoiceField(
        choices=DocumentoCarro.Tipo.choices,
        label=_("Tipo de documento"),
    )
    fecha_expedicion = forms.DateField(
        label=_("Fecha de expedición"),
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    fecha_vencimiento = forms.DateField(
        label=_("Fecha de vencimiento"),
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    archivo = forms.FileField(
        required=False,
        label=_("Archivo soporte (PDF o imagen)"),
    )

    def clean(self):
        from datetime import date

        datos = super().clean()
        hoy = date.today()
        exp = datos.get("fecha_expedicion")
        ven = datos.get("fecha_vencimiento")
        tipo = datos.get("tipo_documento")
        etiqueta = dict(DocumentoCarro.Tipo.choices).get(tipo, "Documento")

        if exp and ven:
            if exp > hoy:
                self.add_error(
                    "fecha_expedicion",
                    f"{etiqueta}: La fecha de expedición no puede ser futura.",
                )
            if ven <= exp:
                self.add_error(
                    "fecha_vencimiento",
                    f"{etiqueta}: La fecha de vencimiento debe ser posterior a la fecha de expedición.",
                )
        return datos


class ResenaForm(forms.Form):
    CALIFICACION_CHOICES = [
        (5, _("5 estrellas — Excelente")),
        (4, _("4 estrellas — Muy bueno")),
        (3, _("3 estrellas — Regular")),
        (2, _("2 estrellas — Malo")),
        (1, _("1 estrella — Muy malo")),
    ]
    TIPO_CHOICES = [
        ("COMPRA", _("Experiencia de compra")),
        ("ATENCION", _("Atención del vendedor")),
        ("VEHICULO", _("Estado del vehículo / repuesto")),
        ("GENERAL", _("Comentario general")),
    ]

    calificacion = forms.TypedChoiceField(
        choices=CALIFICACION_CHOICES,
        coerce=int,
        initial=5,
        label=_("Calificación"),
    )
    tipo = forms.ChoiceField(
        choices=TIPO_CHOICES,
        initial="COMPRA",
        label=_("Tipo de reseña"),
    )
    contenido = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        label=_("Tu reseña"),
    )
