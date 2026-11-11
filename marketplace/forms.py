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
from .models import Carro, DocumentoCarro, Resena


class CrearArticuloForm(forms.Form):
    placa = forms.CharField(max_length=6, label=_('Placa'))
    marca = forms.CharField(max_length=60, label=_('Marca'))
    modelo = forms.CharField(max_length=60, label=_('Modelo'))
    color = forms.CharField(max_length=40, label=_('Color'))
    estado = forms.ChoiceField(choices=Carro.Estado.choices, label=_('Estado'))
    kilometraje = forms.IntegerField(min_value=0, label=_('Kilometraje'))
    precio = forms.IntegerField(min_value=1, label=_('Precio (COP)'))
    descripcion = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        label=_('Descripción'),
    )

    soat_expedicion = forms.DateField(
        label=_('SOAT: expedición'),
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
    )
    soat_vencimiento = forms.DateField(
        label=_('SOAT: vencimiento'),
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
    )
    soat_archivo = forms.FileField(required=False, label=_('SOAT: archivo'))

    tecnomecanica_expedicion = forms.DateField(
        label=_('Tecnomecánica: expedición'),
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
    )
    tecnomecanica_vencimiento = forms.DateField(
        label=_('Tecnomecánica: vencimiento'),
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
    )
    tecnomecanica_archivo = forms.FileField(
        required=False, label=_('Tecnomecánica: archivo')
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
                    _('SOAT: La fecha de expedición no puede ser futura.'),
                )
            if soat_ven <= soat_exp:
                self.add_error(
                    "soat_vencimiento",
                    _('SOAT: La fecha de vencimiento debe ser posterior a la fecha de expedición.'),
                )

        tec_exp = datos.get("tecnomecanica_expedicion")
        tec_ven = datos.get("tecnomecanica_vencimiento")
        if tec_exp and tec_ven:
            if tec_exp > hoy:
                self.add_error(
                    "tecnomecanica_expedicion",
                    _('Revisión técnico-mecánica: La fecha de expedición no puede ser futura.'),
                )
            if tec_ven <= tec_exp:
                self.add_error(
                    "tecnomecanica_vencimiento",
                    _('Revisión técnico-mecánica: La fecha de vencimiento debe ser posterior a la fecha de expedición.'),
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
        label=_('Método de pago'), widget=forms.RadioSelect
    )
    cuotas = forms.IntegerField(
        min_value=1, required=False, initial=1, label=_('Cuotas')
    )
    referencia = forms.CharField(
        max_length=60, required=False, label=_('Referencia (opcional)')
    )

    # Datos propios de cada método. Cuáles son obligatorios lo decide la
    # especificación del método en el dominio, no este formulario.
    token_tarjeta = forms.CharField(
        max_length=120, required=False, label=_('Número de tarjeta / token')
    )
    banco = forms.CharField(max_length=60, required=False, label=_('Banco'))
    tipo_persona = forms.ChoiceField(
        choices=[("NATURAL", _('Persona natural')), ("JURIDICA", _('Persona jurídica'))],
        required=False,
        label=_('Tipo de persona'),
    )
    documento_pagador = forms.CharField(
        max_length=20, required=False, label=_('Documento del pagador')
    )
    telefono = forms.CharField(max_length=20, required=False, label=_('Teléfono'))

    def __init__(self, *args, monto=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.metodos = metodos_disponibles(monto)
        self.fields["metodo_pago"].choices = [
            (metodo.codigo, metodo.etiqueta) for metodo in self.metodos
        ]


class RegistroForm(forms.Form):
    ROL_CHOICES = [("CLIENTE", _('Cliente — quiero comprar')), ("VENDEDOR", _('Vendedor — quiero publicar vehículos'))]
    rol = forms.ChoiceField(choices=ROL_CHOICES, label=_('Tipo de cuenta'))
    username = forms.CharField(max_length=150, label=_('Usuario'))
    password = forms.CharField(widget=forms.PasswordInput, label=_('Contraseña'))
    password_confirmacion = forms.CharField(widget=forms.PasswordInput, label=_('Confirmar contraseña'))
    nombre = forms.CharField(max_length=120, label=_('Nombre completo'))
    correo = forms.EmailField(label=_('Correo'))
    direccion = forms.CharField(max_length=200, label=_('Dirección'))
    numero_tel = forms.CharField(max_length=20, label=_('Teléfono'))

    def clean(self):
        datos = super().clean()
        if datos.get("password") and datos.get("password") != datos.get("password_confirmacion"):
            self.add_error("password_confirmacion", _('Las contraseñas no coinciden.'))
        return datos


class DocumentoCarroForm(forms.Form):
    tipo_documento = forms.ChoiceField(
        choices=DocumentoCarro.Tipo.choices,
        label=_("Tipo de documento"),
    )
    fecha_expedicion = forms.DateField(
        label=_("Fecha de expedición"),
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
    )
    fecha_vencimiento = forms.DateField(
        label=_("Fecha de vencimiento"),
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
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
                    _('%(etiqueta)s: La fecha de expedición no puede ser futura.') % {'etiqueta': etiqueta},
                )
            if ven <= exp:
                self.add_error(
                    "fecha_vencimiento",
                    _('%(etiqueta)s: La fecha de vencimiento debe ser posterior a la fecha de expedición.') % {'etiqueta': etiqueta},
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

    calificacion = forms.TypedChoiceField(
        choices=CALIFICACION_CHOICES,
        coerce=int,
        initial=5,
        label=_("Calificación"),
    )
    tipo = forms.ChoiceField(
        choices=Resena.Tipo.choices,
        initial="COMPRA",
        label=_("Tipo de reseña"),
    )
    contenido = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        label=_("Tu reseña"),
    )
