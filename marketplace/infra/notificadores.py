"""Implementaciones concretas de los puertos `Notificador` y `NotificadorPagos`."""

import logging

from django.conf import settings
from django.core.mail import send_mail

from ..domain.ports import Notificador, NotificadorPagos
from ..models import Pago

logger = logging.getLogger(__name__)

#: Qué se le dice al cliente según cómo terminó su pago. Tenerlo en un mapa
#: y no en un `if/elif` deja que un estado nuevo sea una línea más.
MENSAJES_POR_ESTADO = {
    Pago.Estado.APROBADO: "Tu pago fue aprobado. El vendedor ya fue notificado.",
    Pago.Estado.PENDIENTE: "Tu pago quedó pendiente de confirmación.",
    Pago.Estado.RECHAZADO: "Tu pago fue rechazado y no se te cobró nada.",
    Pago.Estado.ANULADO: "Tu pago fue anulado.",
    Pago.Estado.REEMBOLSADO: "Tu pago fue reembolsado.",
}


def _formatear_pesos(valor):
    """Formato colombiano: separador de miles con punto."""
    return f"{valor:,}".replace(",", ".")


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
            subject=f"CarFit: pago {pago.referencia} {pago.get_estado_display()}",
            message=(
                f"Hola {pago.cliente.nombre},\n\n"
                f"{MENSAJES_POR_ESTADO.get(pago.estado, '')}\n\n"
                f"Referencia: {pago.referencia}\n"
                f"Método: {pago.get_metodo_pago_display()}\n"
                f"Artículo: ${_formatear_pesos(pago.precio)} {pago.moneda}\n"
                f"Comisión: ${_formatear_pesos(pago.comision)} {pago.moneda}\n"
                f"Total: ${_formatear_pesos(pago.total)} {pago.moneda}\n"
                f"{pago.mensaje}\n"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[pago.cliente.correo],
            fail_silently=False,
        )
        logger.info("[REAL] Comprobante enviado a %s.", pago.cliente.correo)
