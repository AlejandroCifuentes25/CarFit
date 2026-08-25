"""Excepciones del dominio.

Son independientes de Django y de HTTP: el dominio no sabe que existe una
petición web. La vista las traduce a errores de formulario.
"""


class ErrorDeDominio(Exception):
    """Raíz de todos los errores de negocio de CarFit."""


class ArticuloInvalidoError(ErrorDeDominio):
    """El artículo no cumple las invariantes exigidas para ser publicado."""

    def __init__(self, errores):
        self.errores = list(errores)
        super().__init__(" ".join(self.errores))


class DocumentacionInvalidaError(ErrorDeDominio):
    """La documentación legal del vehículo no es válida o está vencida."""

    def __init__(self, motivos):
        self.motivos = list(motivos)
        super().__init__(" ".join(self.motivos))


class CredencialesInvalidasError(ErrorDeDominio):
    """El usuario o la contraseña no son correctos."""

    def __init__(self):
        super().__init__("Usuario o contraseña incorrectos.")


class NombreDeUsuarioEnUsoError(ErrorDeDominio):
    """Ya existe una cuenta con ese nombre de usuario."""

    def __init__(self, username):
        self.username = username
        super().__init__(f"El usuario '{username}' ya está en uso.")
