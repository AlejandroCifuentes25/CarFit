"""Implementaciones concretas de los puertos `Notificador` y `NotificadorPagos`."""

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.utils import formats
from django.utils.translation import gettext as _, gettext_lazy

from ..domain.ports import Notificador, NotificadorPagos
from ..models import Pago

logger = logging.getLogger(__name__)

#: Qué se le dice al cliente según cómo terminó su pago. Tenerlo en un mapa
#: y no en un `if/elif` deja que un estado nuevo sea una línea más.
MENSAJES_POR_ESTADO = {
    Pago.Estado.APROBADO: gettext_lazy("Tu pago fue aprobado."),
    Pago.Estado.PENDIENTE: gettext_lazy("Tu pago quedó pendiente de confirmación."),
    Pago.Estado.RECHAZADO: gettext_lazy("Tu pago fue rechazado y no se te cobró nada."),
    Pago.Estado.ANULADO: gettext_lazy("Tu pago fue anulado."),
    Pago.Estado.REEMBOLSADO: gettext_lazy("Tu pago fue reembolsado."),
}


def _formatear_pesos(valor):
    """Formato colombiano: separador de miles con punto."""
    return formats.number_format(valor, force_grouping=True)


class NotificadorConsola(Notificador):
    """Imprime la notificación. Para desarrollo: no gasta cuota de correo."""

    def notificar_publicacion(self, articulo) -> None:
        logger.info(
            "[MOCK] Correo a %s: tu %s quedó publicado por $%s COP.",
            articulo.vendedor.correo,
            articulo,
            f"{articulo.precio:,}".replace(",", "."),
        )


class NotificadorEmail(Notificador):
    """Envía un correo real usando el backend configurado en Django."""

    def notificar_publicacion(self, articulo) -> None:
        precio = f"{articulo.precio:,}".replace(",", ".")
        send_mail(
            subject=_("Tu publicación %(articulo)s ya está en CarFit") % {"articulo": articulo},
            message=_(
                "Hola %(nombre)s,\n\n"
                "Tu publicación %(articulo)s está visible por $%(precio)s COP.\n"
            ) % {"nombre": articulo.vendedor.nombre, "articulo": articulo, "precio": precio},
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[articulo.vendedor.correo],
            fail_silently=False,
        )
        logger.info("[REAL] Correo enviado a %s.", articulo.vendedor.correo)


class NotificadorPagoConsola(NotificadorPagos):
    """Imprime el comprobante. Para desarrollo y para las pruebas."""

    def notificar_resultado(self, pago) -> None:
        logger.info(
            "[MOCK] Comprobante a %s: pago %s por $%s %s con %s -> %s. %s",
            pago.cliente.correo,
            pago.referencia,
            _formatear_pesos(pago.total),
            pago.moneda,
            pago.get_metodo_pago_display(),
            pago.estado,
            MENSAJES_POR_ESTADO.get(pago.estado, ""),
        )


class NotificadorPagoEmail(NotificadorPagos):
    """Envía el comprobante por correo con el backend configurado en Django."""

    def notificar_resultado(self, pago) -> None:
        send_mail(
            subject=_("CarFit: pago %(referencia)s %(estado)s") % {
                "referencia": pago.referencia, "estado": pago.get_estado_display(),
            },
            message=_(
                "Hola %(nombre)s,\n\n%(estado)s\n\n"
                "Referencia: %(referencia)s\nMétodo: %(metodo)s\n"
                "Artículo: $%(precio)s %(moneda)s\nComisión: $%(comision)s %(moneda)s\n"
                "Total: $%(total)s %(moneda)s\n%(mensaje)s\n"
            ) % {
                "nombre": pago.cliente.nombre, "estado": MENSAJES_POR_ESTADO.get(pago.estado, ""),
                "referencia": pago.referencia, "metodo": pago.get_metodo_pago_display(),
                "precio": _formatear_pesos(pago.precio), "comision": _formatear_pesos(pago.comision),
                "total": _formatear_pesos(pago.total), "moneda": pago.moneda,
                "mensaje": pago.mensaje_localizado,
            },
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[pago.cliente.correo],
            fail_silently=False,
        )
        logger.info("[REAL] Comprobante enviado a %s.", pago.cliente.correo)
