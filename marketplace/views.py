"""Capa de Interfaz (Django Views).

La vista solo traduce entre HTTP y el dominio: toma los datos del `request`,
llama al servicio y convierte los errores de negocio en errores de
formulario. No contiene ni una regla de negocio.
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import FormView, TemplateView

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .domain.exceptions import ErrorDeDominio
from .forms import CrearArticuloForm
from .api.serializers import ArticuloCarritoSerializer, MovimientoCarritoSerializer
from .services import CarritoComprasService, PublicacionArticuloService

class CrearArticuloView(LoginRequiredMixin, FormView):
    """Publica un artículo del vendedor autenticado."""

    template_name = "marketplace/crear_articulo.html"
    form_class = CrearArticuloForm
    success_url = reverse_lazy("marketplace:articulo_publicado")
    # Inyectable desde las pruebas: CrearArticuloView.as_view(service_factory=...)
    service_factory = PublicacionArticuloService

    def form_valid(self, form):
        try:
            self.service_factory().crear_articulo(
                self.request.user.vendedor, form.cleaned_data
            )
        except ErrorDeDominio as error:
            form.add_error(None, str(error))
            return self.form_invalid(form)
        return super().form_valid(form)


class ArticuloPublicadoView(LoginRequiredMixin, TemplateView):
    template_name = "marketplace/articulo_publicado.html"


class BaseCarritoView(APIView):
    """Vista base del carrito: centraliza autenticación e inyección del servicio."""

    permission_classes = [IsAuthenticated]
    service_factory = CarritoComprasService

    def get_service(self):
        return self.service_factory()


class BaseArticuloCarritoView(BaseCarritoView):
    """Plantilla para acciones que reciben un artículo y delegan al servicio."""

    request_serializer_class = MovimientoCarritoSerializer
    response_serializer_class = ArticuloCarritoSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.request_serializer_class(data=kwargs)
        serializer.is_valid(raise_exception=True)

        try:
            resultado = self.ejecutar(
                self.get_service(), request.user, serializer.validated_data
            )
        except ErrorDeDominio as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            self.response_serializer_class(resultado).data,
            status=status.HTTP_200_OK,
        )

    def ejecutar(self, servicio, usuario, datos):
        raise NotImplementedError


class BaseCarritoOperacionView(BaseCarritoView):
    """Plantilla para operaciones del carrito que no necesitan datos extra."""

    def post(self, request, *args, **kwargs):
        try:
            resultado = self.ejecutar(self.get_service(), request.user)
        except ErrorDeDominio as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(resultado, status=status.HTTP_200_OK)

    def ejecutar(self, servicio, usuario):
        raise NotImplementedError


class AgregarArticuloCarrito(BaseArticuloCarritoView):
    """Agrega un carro o repuesto al carrito actual."""

    def ejecutar(self, servicio, usuario, datos):
        return servicio.agregar_articulo(
            usuario, datos["tipo_articulo"], datos["articulo_id"]
        )

class QuitarArticuloCarrito(BaseArticuloCarritoView):
    """Quita un carro o repuesto del carrito actual."""

    def ejecutar(self, servicio, usuario, datos):
        return servicio.quitar_articulo(
            usuario, datos["tipo_articulo"], datos["articulo_id"]
        )


class VaciarCarritoView(BaseCarritoOperacionView):
    """Vacía por completo el carrito actual."""

    def ejecutar(self, servicio, usuario):
        carrito = servicio.vaciar_carrito(usuario)
        return {
            "carrito_id": carrito.pk,
            "cantidad_producto": carrito.cantidad_producto,
            "precio_total": carrito.precio_total,
        }


class CalcularTotalCarritoView(BaseCarritoOperacionView):
    """Devuelve el precio total acumulado del carrito."""

    def ejecutar(self, servicio, usuario):
        total = servicio.calcular_total(usuario)
        return {"precio_total": total}


class ConfirmarCompraCarritoView(BaseCarritoOperacionView):
    """Confirma el carrito y lo deja listo para la capa de pagos."""

    def ejecutar(self, servicio, usuario):
        return servicio.confirmar_compra(usuario)
