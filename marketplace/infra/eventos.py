import logging
from functools import partial

from django.conf import settings
from django.db import transaction
from django.utils.translation import get_language
from kombu.exceptions import OperationalError

from ..models import Carro, EventoNotificacion
from .factories import NotificadorFactory, NotificadorPagosFactory

logger = logging.getLogger(__name__)


def publicar_evento(evento_id):
    from ..tasks import enviar_notificacion

    try:
        enviar_notificacion.apply_async(args=[evento_id], retry=False)
    except (OperationalError, OSError):
        logger.warning("Redis no disponible. Evento %s pendiente de reenvío.", evento_id)


def _registrar(clase, objeto_id, datos=None):
    evento = EventoNotificacion.objects.create(
        clase=clase, objeto_id=objeto_id, idioma=get_language() or settings.LANGUAGE_CODE,
        datos=datos or {},
    )
    transaction.on_commit(partial(publicar_evento, evento.pk), robust=True)


class NotificadorPublicacionAsincrono:
    def notificar_publicacion(self, articulo):
        _registrar("carro" if isinstance(articulo, Carro) else "repuesto", articulo.pk)


class NotificadorPagoAsincrono:
    def notificar_resultado(self, pago):
        _registrar("pago", pago.pk, {"estado": pago.estado, "mensaje": str(pago.mensaje)})


def notificador_publicacion():
    if settings.CELERY_BROKER_URL:
        return NotificadorPublicacionAsincrono()
    return NotificadorFactory.crear()


def notificador_pago():
    if settings.CELERY_BROKER_URL:
        return NotificadorPagoAsincrono()
    return NotificadorPagosFactory.crear()
