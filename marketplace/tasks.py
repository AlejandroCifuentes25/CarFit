from datetime import timedelta
from smtplib import SMTPException

from celery import shared_task
from django.db import OperationalError, transaction
from django.utils import timezone, translation

from .infra.factories import NotificadorFactory, NotificadorPagosFactory
from .models import Carro, EventoNotificacion, Pago, Repuesto


@shared_task(
    autoretry_for=(OSError, SMTPException, OperationalError),
    retry_backoff=True,
    max_retries=4,
    acks_late=True,
)
def enviar_notificacion(evento_id):
    with transaction.atomic():
        evento = EventoNotificacion.objects.select_for_update().get(pk=evento_id)
        if evento.enviado_en is not None:
            return
        with translation.override(evento.idioma):
            if evento.clase == "pago":
                pago = Pago.objects.select_related("cliente").get(pk=evento.objeto_id)
                # Conserva el estado que originó el aviso aunque ya haya cambiado.
                pago.estado = evento.datos["estado"]
                pago.mensaje = evento.datos["mensaje"]
                NotificadorPagosFactory.crear().notificar_resultado(pago)
            else:
                modelo = {"carro": Carro, "repuesto": Repuesto}[evento.clase]
                articulo = modelo.objects.select_related("vendedor").filter(pk=evento.objeto_id).first()
                if articulo is not None:
                    NotificadorFactory.crear().notificar_publicacion(articulo)
        evento.enviado_en = timezone.now()
        evento.save(update_fields=["enviado_en"])


@shared_task
def recuperar_notificaciones():
    """Recupera eventos persistidos cuando Redis no aceptó el primer envío."""
    pendientes = EventoNotificacion.objects.filter(
        enviado_en__isnull=True, creado_en__lt=timezone.now() - timedelta(seconds=30),
    ).order_by("id").values_list("id", flat=True)[:100]
    for evento_id in pendientes:
        enviar_notificacion.apply_async(args=[evento_id], retry=False)
