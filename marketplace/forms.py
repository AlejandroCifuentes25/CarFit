"""Formulario de captura para la publicación de un artículo.

Deliberadamente es un `forms.Form` y **no** un `ModelForm`: el formulario
solo valida el *formato* de la entrada (que la fecha sea una fecha, que el
kilometraje sea un entero). Las reglas de *negocio* — que un carro NUEVO no
tenga 80.000 km, que la placa cumpla el formato colombiano — pertenecen al
`CarroBuilder`, para que también se apliquen cuando el artículo se cree
desde un comando de consola o una API, sin pasar por este formulario.
"""

from django import forms

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

    soat_expedicion = forms.DateField(label="SOAT — expedición")
    soat_vencimiento = forms.DateField(label="SOAT — vencimiento")
    soat_archivo = forms.FileField(required=False, label="SOAT — archivo")

    tecnomecanica_expedicion = forms.DateField(label="Tecnomecánica — expedición")
    tecnomecanica_vencimiento = forms.DateField(label="Tecnomecánica — vencimiento")
    tecnomecanica_archivo = forms.FileField(
        required=False, label="Tecnomecánica — archivo"
    )
