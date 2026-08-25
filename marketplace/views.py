"""Capa de Interfaz (Django Views).

La vista solo traduce entre HTTP y el dominio: toma los datos del `request`,
llama al servicio y convierte los errores de negocio en errores de
formulario. No contiene ni una regla de negocio.
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import FormView, TemplateView

from .domain.exceptions import ErrorDeDominio
from .forms import CrearArticuloForm, RegistroForm
from .services import PublicacionArticuloService, RegistroUsuarioService


class IndexView(TemplateView):
    """Página principal: punto de entrada con enlaces a iniciar sesión o
    registrarse (o, si ya hay sesión iniciada, a publicar un artículo)."""

    template_name = "marketplace/index.html"


class RegistroView(FormView):
    """Registro de una cuenta nueva, como Cliente o como Vendedor."""

    template_name = "marketplace/registro.html"
    form_class = RegistroForm
    success_url = reverse_lazy("marketplace:crear_articulo")
    # Inyectable desde las pruebas: RegistroView.as_view(service_factory=...)
    service_factory = RegistroUsuarioService

    def form_valid(self, form):
        datos = form.cleaned_data
        try:
            self.service_factory().registrar(self.request, datos["rol"], datos)
        except ErrorDeDominio as error:
            form.add_error(None, str(error))
            return self.form_invalid(form)
        return super().form_valid(form)


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
