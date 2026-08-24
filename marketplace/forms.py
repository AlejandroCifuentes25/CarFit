"""Formulario de captura para la publicación de un artículo.

Deliberadamente es un `forms.Form` y **no** un `ModelForm`: el formulario
solo valida el *formato* de la entrada (que la fecha sea una fecha, que el
kilometraje sea un entero). Las reglas de *negocio* (que un carro NUEVO no
tenga 80.000 km, que la placa cumpla el formato colombiano) pertenecen al
`CarroBuilder`, para que también se apliquen cuando el artículo se cree
desde un comando de consola o una API, sin pasar por este formulario.
"""

from django import forms

from .domain.metodos_pago import metodos_disponibles
from .models import Carro


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

    soat_expedicion = forms.DateField(label="SOAT: expedición")
    soat_vencimiento = forms.DateField(label="SOAT: vencimiento")
    soat_archivo = forms.FileField(required=False, label="SOAT: archivo")

    tecnomecanica_expedicion = forms.DateField(label="Tecnomecánica: expedición")
    tecnomecanica_vencimiento = forms.DateField(label="Tecnomecánica: vencimiento")
    tecnomecanica_archivo = forms.FileField(
        required=False, label="Tecnomecánica: archivo"
    )


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
