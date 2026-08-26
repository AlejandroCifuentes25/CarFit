"""Carrito de compras (DRF).

Antes vivía en `marketplace/views.py` junto con las vistas HTML, aunque ya
usaba `APIView` y serializers como la API de pagos. Se mueve aquí para que
toda la API quede en un solo paquete, y se centraliza en `BaseCarritoView`
la traducción de `ErrorDeDominio` a HTTP que las vistas antes repetían cada
una por su lado (ahora reutiliza `respuesta_de_error`, igual que pagos).
"""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..domain.exceptions import ErrorDeDominio
from ..services import CarritoComprasService
from .errores import respuesta_de_error
from .serializers import ArticuloCarritoSerializer, MovimientoCarritoSerializer


class BaseCarritoView(APIView):
    """Comparten permisos, el service y la traducción de errores de dominio."""

    permission_classes = [IsAuthenticated]
    service_factory = CarritoComprasService

    def get_service(self):
        return self.service_factory()

    def ejecutar_y_responder(self, operacion, serializar=lambda resultado: resultado):
        try:
            resultado = operacion()
        except ErrorDeDominio as error:
            return respuesta_de_error(error)
        return Response(serializar(resultado))


class BaseArticuloCarritoView(BaseCarritoView):
    def post(self, request, *args, **kwargs):
        serializer = MovimientoCarritoSerializer(data=kwargs)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        return self.ejecutar_y_responder(
            lambda: self.ejecutar(self.get_service(), request.user, datos),
            serializar=lambda resultado: ArticuloCarritoSerializer(resultado).data,
        )


class AgregarArticuloCarrito(BaseArticuloCarritoView):
    def ejecutar(self, servicio, usuario, datos):
        return servicio.agregar_articulo(usuario, datos["tipo_articulo"], datos["articulo_id"])


class QuitarArticuloCarrito(BaseArticuloCarritoView):
    def ejecutar(self, servicio, usuario, datos):
        return servicio.quitar_articulo(usuario, datos["tipo_articulo"], datos["articulo_id"])


class BaseCarritoOperacionView(BaseCarritoView):
    def post(self, request, *args, **kwargs):
        return self.ejecutar_y_responder(lambda: self.ejecutar(self.get_service(), request.user))


class VaciarCarritoView(BaseCarritoOperacionView):
    def ejecutar(self, servicio, usuario):
        carrito = servicio.vaciar_carrito(usuario)
        return {
            "carrito_id": carrito.pk,
            "cantidad_producto": carrito.cantidad_producto,
            "precio_total": carrito.precio_total,
        }


class CalcularTotalCarritoView(BaseCarritoOperacionView):
    def ejecutar(self, servicio, usuario):
        return {"precio_total": servicio.calcular_total(usuario)}


class ConfirmarCompraCarritoView(BaseCarritoOperacionView):
    def ejecutar(self, servicio, usuario):
        return servicio.confirmar_compra(usuario)
