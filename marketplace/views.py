"""Capa de Interfaz (Django Views).

La vista solo traduce entre HTTP y el dominio: toma los datos del `request`,
llama al servicio y convierte los errores de negocio en errores de
formulario. No contiene ni una regla de negocio.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import FormView, TemplateView

from .domain.exceptions import ErrorDeDominio
from .forms import CrearArticuloForm, PagoForm, RegistroForm
from .models import Carro, Repuesto
from .services import (
    CatalogoComprasService,
    ConfirmarPagoService,
    ConsultarPagoService,
    FacturaService,
    ProcesarPagoService,
    PublicacionArticuloService,
    RegistroUsuarioService,
)


class IndexView(TemplateView):
    template_name = "marketplace/index.html"


class RegistroView(FormView):
    template_name = "marketplace/registro.html"
    form_class = RegistroForm
    service_factory = RegistroUsuarioService

    def form_valid(self, form):
        try:
            self.service_factory().registrar(self.request, form.cleaned_data["rol"], form.cleaned_data)
        except ErrorDeDominio as error:
            form.add_error(None, str(error))
            return self.form_invalid(form)
        if form.cleaned_data["rol"] == "CLIENTE":
            self.success_url = reverse_lazy("marketplace:catalogo_compras")
        else:
            self.success_url = reverse_lazy("marketplace:crear_articulo")
        return super().form_valid(form)


class VendedorRequeridoMixin:
    """Impide que cuentas de cliente accedan al flujo de publicación."""

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not hasattr(request.user, "vendedor"):
            return render(request, "marketplace/sin_perfil_vendedor.html", status=403)
        return super().dispatch(request, *args, **kwargs)


class CrearArticuloView(LoginRequiredMixin, VendedorRequeridoMixin, FormView):
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


# ----------------------------------------------------------------------
# Compra y pagos
# ----------------------------------------------------------------------


class ClienteRequeridoMixin:
    """Exige que el usuario autenticado tenga perfil de `Cliente`.

    Publicar es de vendedores; comprar es de clientes. Un usuario sin perfil
    de cliente recibe una página explicativa en vez de un 404 críptico.
    """

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not hasattr(request.user, "cliente"):
            return render(request, "marketplace/sin_perfil_cliente.html", status=403)
        return super().dispatch(request, *args, **kwargs)


class CatalogoComprasView(LoginRequiredMixin, TemplateView):
    """Muestra el catálogo calculado por la capa de aplicación."""

    template_name = "marketplace/catalogo.html"
    service_factory = CatalogoComprasService

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["carros"], contexto["repuestos"] = self.service_factory().listar_disponibles(
            self.request.user
        )
        return contexto


class PagarArticuloView(LoginRequiredMixin, ClienteRequeridoMixin, View):
    """Formulario de pago de un carro o un repuesto.

    Traduce entre HTTP y `ProcesarPagoService`: arma el diccionario que el
    servicio espera, delega el cobro y convierte los errores de dominio en
    errores de formulario. La comisión que se ve en pantalla mientras se
    elige el método es una vista previa en JavaScript; la que de verdad
    cobra la calcula el dominio en el servidor.
    """

    template_name = "marketplace/pagar_articulo.html"
    servicio = ProcesarPagoService
    modelos = {"carro": Carro, "repuesto": Repuesto}

    def get(self, request, tipo, pk):
        articulo = self._articulo(tipo, pk)
        formulario = PagoForm(monto=articulo.precio)
        return render(request, self.template_name, self._contexto(articulo, tipo, formulario))

    def post(self, request, tipo, pk):
        articulo = self._articulo(tipo, pk)
        formulario = PagoForm(request.POST, monto=articulo.precio)

        if formulario.is_valid():
            datos = dict(formulario.cleaned_data)
            datos[tipo] = articulo.pk
            try:
                pago = self.servicio().procesar(request.user.cliente, datos)
            except ErrorDeDominio as error:
                formulario.add_error(None, str(error))
            else:
                return redirect("marketplace:detalle_pago", referencia=pago.referencia)

        return render(request, self.template_name, self._contexto(articulo, tipo, formulario))

    def _articulo(self, tipo, pk):
        modelo = self.modelos.get(tipo)
        if modelo is None:
            raise Http404("Tipo de artículo desconocido.")
        return get_object_or_404(modelo, pk=pk)

    def _contexto(self, articulo, tipo, formulario):
        metodos = formulario.metodos
        seleccionado = formulario["metodo_pago"].value() if formulario.metodos else None
        return {
            "articulo": articulo,
            "tipo": tipo,
            "metodos": metodos,
            "form": formulario,
            "metodo_inicial": seleccionado or (metodos[0].codigo if metodos else None),
        }


class DetallePagoView(LoginRequiredMixin, ClienteRequeridoMixin, View):
    """Estado de un pago propio."""

    template_name = "marketplace/pago_detalle.html"
    servicio = ConsultarPagoService

    def get(self, request, referencia):
        try:
            pago = self.servicio().obtener(referencia, request.user.cliente)
        except ErrorDeDominio as error:
            raise Http404(str(error)) from error
        return render(request, self.template_name, {"pago": pago})


class FacturaPagoView(LoginRequiredMixin, ClienteRequeridoMixin, View):
    """Factura imprimible de un pago aprobado."""

    template_name = "marketplace/pago_factura.html"
    servicio = FacturaService

    def get(self, request, referencia):
        try:
            factura = self.servicio().generar(referencia, request.user.cliente)
        except ErrorDeDominio as error:
            raise Http404(str(error)) from error
        return render(request, self.template_name, {"factura": factura})


class ConfirmarPagoView(LoginRequiredMixin, ClienteRequeridoMixin, View):
    """Resuelve un pago pendiente (PSE, efectivo) contra la pasarela."""

    servicio = ConfirmarPagoService

    def post(self, request, referencia):
        try:
            self.servicio().confirmar(referencia, request.user.cliente)
        except ErrorDeDominio as error:
            messages.error(request, str(error))
        else:
            messages.success(request, "Actualizamos el estado de tu pago.")
        return redirect("marketplace:detalle_pago", referencia=referencia)


class HistorialPagosView(LoginRequiredMixin, ClienteRequeridoMixin, TemplateView):
    """Historial de pagos del cliente autenticado."""

    template_name = "marketplace/historial_pagos.html"
    servicio = ConsultarPagoService

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["pagos"] = self.servicio().listar(self.request.user.cliente)
        return contexto
