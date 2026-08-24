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


class RegistroForm(forms.Form):
    """Formulario de registro de cuenta (Cliente o Vendedor).

    Igual que `CrearArticuloForm`, solo valida formato: que las contraseñas
    coincidan y que los campos requeridos estén presentes. La regla de
    negocio "el nombre de usuario debe ser único" vive en
    `RegistroUsuarioService`.
    """

    ROL_CHOICES = [
        ("CLIENTE", "Cliente — quiero comprar"),
        ("VENDEDOR", "Vendedor — quiero publicar vehículos"),
    ]

    rol = forms.ChoiceField(choices=ROL_CHOICES, label="Tipo de cuenta")
    username = forms.CharField(max_length=150, label="Usuario")
    password = forms.CharField(widget=forms.PasswordInput, label="Contraseña")
    password_confirmacion = forms.CharField(
        widget=forms.PasswordInput, label="Confirmar contraseña"
    )
    nombre = forms.CharField(max_length=120, label="Nombre completo")
    correo = forms.EmailField(label="Correo")
    direccion = forms.CharField(max_length=200, label="Dirección")
    numero_tel = forms.CharField(max_length=20, label="Teléfono")

    def clean(self):
        datos = super().clean()
        password = datos.get("password")
        confirmacion = datos.get("password_confirmacion")
        if password and confirmacion and password != confirmacion:
            self.add_error("password_confirmacion", "Las contraseñas no coinciden.")
        return datos
