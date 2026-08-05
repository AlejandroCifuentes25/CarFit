"""Implementaciones concretas del puerto `Notificador`."""

import logging

from django.conf import settings
from django.core.mail import send_mail

from ..domain.ports import Notificador

logger = logging.getLogger(__name__)


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
            subject=f"Tu {articulo.marca} {articulo.modelo} ya está en CarFit",
            message=(
                f"Hola {articulo.vendedor.nombre},\n\n"
                f"Publicamos tu {articulo} por $ {precio} COP.\n"
                f"Ya es visible para los compradores en CarFit.\n"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[articulo.vendedor.correo],
            fail_silently=False,
        )
        logger.info("[REAL] Correo enviado a %s.", articulo.vendedor.correo)
