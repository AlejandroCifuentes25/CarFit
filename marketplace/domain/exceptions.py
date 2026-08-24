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


class RecursoNoEncontradoError(ErrorDeDominio):
    """Se pidió operar sobre algo que no existe.

    La capa de presentación la traduce a HTTP 404. El dominio no conoce ese
    número: solo afirma que el recurso no está.
    """

    def __init__(self, recurso, identificador=None):
        self.recurso = recurso
        self.identificador = identificador
        detalle = f" '{identificador}'" if identificador is not None else ""
        super().__init__(f"No existe {recurso}{detalle}.")


# ----------------------------------------------------------------------
# Pagos
# ----------------------------------------------------------------------


class PagoInvalidoError(ErrorDeDominio):
    """La solicitud de pago no cumple las invariantes del dominio.

    Reúne *todos* los errores encontrados, no solo el primero: quien paga
    merece corregir el formulario de una sola vez.
    """

    def __init__(self, errores):
        self.errores = list(errores)
        super().__init__(" ".join(self.errores))


class MetodoPagoNoSoportadoError(PagoInvalidoError):
    """El método de pago solicitado no está en el catálogo."""

    def __init__(self, codigo, soportados):
        self.codigo = codigo
        self.soportados = list(soportados)
        super().__init__(
            [
                f"El método de pago '{codigo}' no está soportado. "
                f"Opciones: {', '.join(self.soportados)}."
            ]
        )


class PagoDuplicadoError(ErrorDeDominio):
    """Ya existe un pago con la misma referencia de idempotencia.

    Es la defensa contra el doble cobro: dos clics en "Pagar" o un reintento
    de la pasarela llegan con la misma referencia y el segundo no cobra.
    """

    def __init__(self, referencia):
        self.referencia = referencia
        super().__init__(f"Ya se registró un pago con la referencia '{referencia}'.")


class ArticuloNoDisponibleError(ErrorDeDominio):
    """El artículo ya tiene un pago aprobado o en curso: no se puede vender dos veces."""

    def __init__(self, articulo, motivo):
        self.articulo = articulo
        self.motivo = motivo
        super().__init__(motivo)


class TransicionPagoInvalidaError(ErrorDeDominio):
    """Se intentó llevar un pago a un estado imposible desde el actual.

    Por ejemplo confirmar un pago ya rechazado, o reembolsar uno que nunca
    se aprobó.
    """

    def __init__(self, referencia, estado_actual, estado_pretendido):
        self.referencia = referencia
        self.estado_actual = estado_actual
        self.estado_pretendido = estado_pretendido
        super().__init__(
            f"El pago '{referencia}' está en estado {estado_actual} y no puede "
            f"pasar a {estado_pretendido}."
        )


class PagoNoFacturableError(ErrorDeDominio):
    """Se pidió la factura de un pago que no está aprobado.

    Solo un pago aprobado tuvo un cobro real: uno pendiente todavía puede
    rechazarse, y uno rechazado nunca se cobró.
    """

    def __init__(self, referencia, estado_actual):
        self.referencia = referencia
        self.estado_actual = estado_actual
        super().__init__(
            f"El pago '{referencia}' está en estado {estado_actual}: "
            f"solo se factura un pago APROBADO."
        )


class PasarelaNoDisponibleError(ErrorDeDominio):
    """La pasarela de pagos no respondió o respondió con un error de su lado.

    No es culpa del cliente ni de sus datos: es una falla de infraestructura
    y por eso se distingue de un pago rechazado.
    """

    def __init__(self, pasarela, motivo):
        self.pasarela = pasarela
        self.motivo = motivo
        super().__init__(f"La pasarela {pasarela} no está disponible: {motivo}")
