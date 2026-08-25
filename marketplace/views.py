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

class BaseArticuloCarritoView(APIView):
    permission_classes = [IsAuthenticated]
    service_factory = CarritoComprasService
    request_serializer_class = MovimientoCarritoSerializer
    response_serializer_class = ArticuloCarritoSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.request_serializer_class(data=kwargs)
        serializer.is_valid(raise_exception=True)

        try:
            resultado = self.ejecutar(
                self.service_factory(), request.user, serializer.validated_data
            )
        except ErrorDeDominio as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            self.response_serializer_class(resultado).data,
            status=status.HTTP_200_OK,
        )

    def ejecutar(self, servicio, usuario, datos):
        raise NotImplementedError


class AgregarArticuloCarrito(BaseArticuloCarritoView):
    """Orquesta la logica para Agrega un artículo al carrito del usuario autenticado."""

    def ejecutar(self, servicio, usuario, datos):
        return servicio.agregar_articulo(
            usuario, datos["tipo_articulo"], datos["articulo_id"]
        )

class QuitarArticuloCarrito(BaseArticuloCarritoView):
    """ Orquesta la logica para quitar un artículo del carrito del usuario autenticado."""

    def ejecutar(self, servicio, usuario, datos):
        return servicio.quitar_articulo(
            usuario, datos["tipo_articulo"], datos["articulo_id"]
        )
