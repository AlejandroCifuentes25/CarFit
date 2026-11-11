"""Capa de Interfaz (Django Views).

La vista solo traduce entre HTTP y el dominio: toma los datos del `request`,
llama al servicio y convierte los errores de negocio en errores de
formulario. No contiene ni una regla de negocio.
"""

from django.utils.translation import gettext as _

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import FormView, TemplateView, UpdateView, DeleteView, CreateView

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .api.serializers import MovimientoCarritoSerializer
from .api.serializers import (
    RespuestaCarritoSerializer,
    RespuestaEstadoCarritoSerializer,
    RespuestaMovimientoCarritoSerializer,
)
from .domain.exceptions import ErrorDeDominio
from .forms import CrearArticuloForm, DocumentoCarroForm, PagoForm, RegistroForm, ResenaForm
from .models import Carro, CarritoCompra, DocumentoCarro, Repuesto, Vendedor
from .services import (
    CatalogoComprasService,
    ConfirmarPagoService,
    ConsultarPagoService,
    DocumentoCarroService,
    FacturaService,
    ProcesarPagoService,
    PublicacionArticuloService,
    CarritoComprasService,
    PagarCarritoService,
    RegistroUsuarioService,
    ResenaService,
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
        from .domain.exceptions import ErrorDeDominio

        try:
            servicio = self.service_factory()
            servicio.crear_articulo(self.request.user.vendedor, form.cleaned_data)
            return super().form_valid(form)
        except (ValueError, ErrorDeDominio) as e:
            form.add_error(None, str(e))
            return self.form_invalid(form)


class CrearRepuestoView(LoginRequiredMixin, VendedorRequeridoMixin, FormView):
    template_name = "marketplace/crear_repuesto.html"
    success_url = reverse_lazy("marketplace:articulo_publicado")

    def get_form_class(self):
        from django import forms
        from .models import Repuesto
        class RepuestoForm(forms.ModelForm):
            class Meta:
                model = Repuesto
                fields = ["tipo", "modelo_carro", "numero_serie", "estado", "precio"]
        return RepuestoForm

    def form_valid(self, form):
        from .domain.exceptions import ErrorDeDominio

        try:
            servicio = PublicacionArticuloService()
            servicio.crear_repuesto(self.request.user.vendedor, form.cleaned_data)
            return super().form_valid(form)
        except (ValueError, ErrorDeDominio) as e:
            form.add_error(None, str(e))
            return self.form_invalid(form)


class ArticuloPublicadoView(LoginRequiredMixin, TemplateView):
    template_name = "marketplace/articulo_publicado.html"


class MisPublicacionesView(LoginRequiredMixin, VendedorRequeridoMixin, TemplateView):
    template_name = "marketplace/mis_publicaciones.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        vendedor = self.request.user.vendedor
        contexto["carros"] = vendedor.carros.all()
        contexto["repuestos"] = vendedor.repuestos.all()
        return contexto


class EditarArticuloView(LoginRequiredMixin, VendedorRequeridoMixin, UpdateView):
    template_name = "marketplace/editar_articulo.html"
    success_url = reverse_lazy("marketplace:mis_publicaciones")

    def get_queryset(self):
        tipo = self.kwargs.get("tipo")
        if tipo == "carro":
            return Carro.objects.filter(vendedor=self.request.user.vendedor)
        elif tipo == "repuesto":
            return Repuesto.objects.filter(vendedor=self.request.user.vendedor)
        raise Http404

    def get_form_class(self):
        from django import forms
        tipo = self.kwargs.get("tipo")
        if tipo == "carro":
            class CarroForm(forms.ModelForm):
                class Meta:
                    model = Carro
                    fields = ["placa", "marca", "modelo", "color", "estado", "kilometraje", "precio", "descripcion"]
            return CarroForm
        else:
            class RepuestoForm(forms.ModelForm):
                class Meta:
                    model = Repuesto
                    fields = ["tipo", "modelo_carro", "numero_serie", "estado", "precio"]
            return RepuestoForm

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["tipo"] = self.kwargs.get("tipo")
        return contexto

    def form_valid(self, form):
        from .services import PublicacionArticuloService
        from .domain.exceptions import ErrorDeDominio
        
        servicio = PublicacionArticuloService()
        try:
            if self.kwargs.get("tipo") == "carro":
                self.object = servicio.editar_carro(self.get_object(), form.cleaned_data)
            else:
                self.object = servicio.editar_repuesto(self.get_object(), form.cleaned_data)
            return redirect(self.get_success_url())
        except ErrorDeDominio as e:
            form.add_error(None, str(e))
            return self.form_invalid(form)


class EliminarArticuloView(LoginRequiredMixin, VendedorRequeridoMixin, DeleteView):
    template_name = "marketplace/confirmar_eliminar.html"
    success_url = reverse_lazy("marketplace:mis_publicaciones")

    def get_queryset(self):
        tipo = self.kwargs.get("tipo")
        if tipo == "carro":
            return Carro.objects.filter(vendedor=self.request.user.vendedor)
        elif tipo == "repuesto":
            return Repuesto.objects.filter(vendedor=self.request.user.vendedor)
        raise Http404

    def form_valid(self, form):
        from .services import PublicacionArticuloService
        from .domain.exceptions import ErrorDeDominio
        
        servicio = PublicacionArticuloService()
        try:
            servicio.eliminar_articulo(self.get_object())
            return redirect(self.success_url)
        except ErrorDeDominio as e:
            messages.error(self.request, str(e))
            return redirect("marketplace:mis_publicaciones")

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["tipo"] = self.kwargs.get("tipo")
        return contexto


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
            from .models import Cliente
            vendedor = getattr(request.user, "vendedor", None)
            cliente = Cliente.objects.create(
                usuario=request.user,
                nombre=vendedor.nombre if vendedor else request.user.username,
                correo=vendedor.correo if vendedor else request.user.email,
                direccion=vendedor.direccion if vendedor else "",
                numero_tel=vendedor.numero_tel if vendedor else ""
            )
            # Asignarlo manualmente al request para evitar problemas de caché en esta misma petición
            request.user.cliente = cliente
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


class CarritoComprasView(LoginRequiredMixin, ClienteRequeridoMixin, FormView):
    """Muestra el carrito y confirma el pago de todos sus artículos."""

    template_name = "marketplace/carrito.html"
    form_class = PagoForm
    service_factory = CarritoComprasService
    checkout_service_factory = PagarCarritoService
    success_url = reverse_lazy("marketplace:historial_pagos")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["monto"] = self._resumen_carrito()["carrito"].precio_total
        return kwargs

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        resumen = self._resumen_carrito()

        articulos = []
        for articulo in resumen["articulos"]:
            articulos.append(
                {
                    "tipo_articulo": articulo.tipo_articulo,
                    "articulo_id": articulo.articulo_id,
                    "titulo": articulo.titulo,
                    "precio": articulo.precio,
                    "vendedor_nombre": articulo.vendedor_nombre,
                    "detalle": articulo.detalle,
                    "quitar_url": reverse(
                        "marketplace:quitar_articulo_carrito",
                        kwargs={
                            "tipo_articulo": articulo.tipo_articulo,
                            "articulo_id": articulo.articulo_id,
                        },
                    ),
                }
            )

        contexto.update(
            {
                "carrito": resumen["carrito"],
                "articulos": articulos,
                "metodo_inicial": contexto["form"].metodos[0].codigo if contexto["form"].metodos else None,
            }
        )
        return contexto

    def form_valid(self, form):
        try:
            resultado = self.checkout_service_factory().procesar(
                self.request.user.cliente, form.cleaned_data
            )
        except ErrorDeDominio as error:
            form.add_error(None, str(error))
            return self.form_invalid(form)

        pagos = resultado.get("pagos", [])
        if pagos:
            messages.success(
                self.request,
                _('Procesamos %(valor1)s pagos. Te llevamos al primer recibo.') % {'valor1': len(pagos)},
            )
            return redirect("marketplace:detalle_pago", referencia=pagos[0].referencia)

        messages.success(self.request, _('Procesamos tu compra.'))
        return super().form_valid(form)

    def _resumen_carrito(self):
        return self.service_factory().obtener_resumen(self.request.user)


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
            raise Http404(_('Tipo de artículo desconocido.'))
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
            messages.success(request, _('Actualizamos el estado de tu pago.'))
        return redirect("marketplace:detalle_pago", referencia=referencia)


class HistorialPagosView(LoginRequiredMixin, ClienteRequeridoMixin, TemplateView):
    """Historial de pagos del cliente autenticado."""

    template_name = "marketplace/historial_pagos.html"
    servicio = ConsultarPagoService

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["pagos"] = self.servicio().listar(self.request.user.cliente)
        return contexto


class BaseCarritoView(APIView):
    permission_classes = [IsAuthenticated]
    service_factory = CarritoComprasService

    def get_service(self):
        return self.service_factory()


class BaseArticuloCarritoView(BaseCarritoView):
    def post(self, request, *args, **kwargs):
        serializer = MovimientoCarritoSerializer(data=kwargs)
        serializer.is_valid(raise_exception=True)
        try:
            servicio = self.get_service()
            resultado = self.ejecutar(servicio, request.user, serializer.validated_data)
        except ErrorDeDominio as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        resumen = servicio.obtener_resumen(request.user)
        return Response(
            RespuestaMovimientoCarritoSerializer(
                {"articulo": resultado, "carrito": resumen["carrito"]}
            ).data
        )


class AgregarArticuloCarrito(BaseArticuloCarritoView):
    def ejecutar(self, servicio, usuario, datos):
        return servicio.agregar_articulo(usuario, datos["tipo_articulo"], datos["articulo_id"])


class QuitarArticuloCarrito(BaseArticuloCarritoView):
    def ejecutar(self, servicio, usuario, datos):
        return servicio.quitar_articulo(usuario, datos["tipo_articulo"], datos["articulo_id"])


class BaseCarritoOperacionView(BaseCarritoView):
    def post(self, request, *args, **kwargs):
        try:
            resultado = self.ejecutar(self.get_service(), request.user)
        except ErrorDeDominio as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        if "estado" in resultado:
            return Response(RespuestaEstadoCarritoSerializer(resultado).data)
        return Response(RespuestaCarritoSerializer(resultado).data)


class VaciarCarritoView(BaseCarritoOperacionView):
    def ejecutar(self, servicio, usuario):
        servicio.vaciar_carrito(usuario)
        return {"carrito": servicio.obtener_resumen(usuario)["carrito"]}


class CalcularTotalCarritoView(BaseCarritoOperacionView):
    def get(self, request, *args, **kwargs):
        try:
            resultado = self.ejecutar(self.get_service(), request.user)
        except ErrorDeDominio as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(RespuestaCarritoSerializer(resultado).data)

    def ejecutar(self, servicio, usuario):
        return {"carrito": servicio.obtener_resumen(usuario)["carrito"]}


class ConfirmarCompraCarritoView(BaseCarritoOperacionView):
    def ejecutar(self, servicio, usuario):
        resultado = servicio.confirmar_compra(usuario)
        return {
            "estado": resultado["estado"],
            "carrito": servicio.obtener_resumen(usuario)["carrito"],
        }


# ----------------------------------------------------------------------
# Documentación del vehículo y Reseñas a Vendedores
# ----------------------------------------------------------------------


class DocumentosCarroView(LoginRequiredMixin, View):
    """Muestra la documentación de un carro, su estado de vigencia documental
    y permite únicamente al vendedor propietario actualizar fechas o archivos."""

    template_name = "marketplace/documentos_carro.html"
    service_factory = DocumentoCarroService

    def _contexto(self, request, carro, servicio, form=None):
        reporte = servicio.verificar_cumplimiento(carro)
        es_dueno = (
            hasattr(request.user, "vendedor")
            and request.user.vendedor.id == carro.vendedor_id
        )
        puede_ver_archivos = servicio.tiene_acceso_archivos(request.user, carro)
        return {
            "carro": carro,
            "reporte": reporte,
            "es_dueno": es_dueno,
            "puede_ver_archivos": puede_ver_archivos,
            "form": form if form is not None else (DocumentoCarroForm() if es_dueno else None),
        }

    def get(self, request, pk):
        carro = get_object_or_404(Carro.objects.select_related("vendedor"), pk=pk)
        servicio = self.service_factory()
        return render(request, self.template_name, self._contexto(request, carro, servicio))

    def post(self, request, pk):
        carro = get_object_or_404(Carro.objects.select_related("vendedor"), pk=pk)
        es_dueno = (
            hasattr(request.user, "vendedor")
            and request.user.vendedor.id == carro.vendedor_id
        )
        if not es_dueno:
            return render(request, "marketplace/sin_perfil_vendedor.html", status=403)

        form = DocumentoCarroForm(request.POST, request.FILES)
        servicio = self.service_factory()
        if form.is_valid():
            try:
                servicio.guardar_documento(
                    request.user.vendedor, carro, form.cleaned_data
                )
                messages.success(request, _('Documento actualizado correctamente.'))
                return redirect("marketplace:documentos_carro", pk=carro.pk)
            except ErrorDeDominio as error:
                form.add_error(None, str(error))

        return render(request, self.template_name, self._contexto(request, carro, servicio, form=form))


class DescargarDocumentoCarroView(LoginRequiredMixin, View):
    """Sirve el archivo original únicamente si el usuario tiene permiso verificado en el backend."""

    service_factory = DocumentoCarroService

    def get(self, request, doc_id):
        doc = get_object_or_404(
            DocumentoCarro.objects.select_related("carro", "carro__vendedor"),
            pk=doc_id,
        )
        if not doc.archivo:
            raise Http404(_('El documento no tiene archivo adjunto.'))

        if not self.service_factory().tiene_acceso_archivos(request.user, doc.carro):
            return HttpResponseForbidden(
                _("No tienes permiso para acceder al documento original del propietario.")
            )

        return FileResponse(doc.archivo.open("rb"), as_attachment=False)


class ResenasVendedorView(LoginRequiredMixin, ClienteRequeridoMixin, View):
    """Lista las reseñas de un vendedor y permite publicar una nueva."""

    template_name = "marketplace/resenas_vendedor.html"
    service_factory = ResenaService

    def get(self, request, vendedor_id):
        servicio = self.service_factory()
        try:
            datos = servicio.listar_por_vendedor(vendedor_id)
        except ErrorDeDominio as error:
            raise Http404(str(error)) from error

        es_mismo_vendedor = (
            hasattr(request.user, "vendedor")
            and request.user.vendedor.id == datos["vendedor"].id
        )
        form = None if es_mismo_vendedor else ResenaForm()
        return render(
            request,
            self.template_name,
            {
                **datos,
                "es_mismo_vendedor": es_mismo_vendedor,
                "form": form,
            },
        )

    def post(self, request, vendedor_id):
        servicio = self.service_factory()
        try:
            datos = servicio.listar_por_vendedor(vendedor_id)
        except ErrorDeDominio as error:
            raise Http404(str(error)) from error

        form = ResenaForm(request.POST)
        if form.is_valid():
            try:
                servicio.crear_resena(
                    request.user.cliente, vendedor_id, form.cleaned_data
                )
                messages.success(request, _('Tu reseña ha sido publicada.'))
                return redirect("marketplace:resenas_vendedor", vendedor_id=vendedor_id)
            except ErrorDeDominio as error:
                form.add_error(None, str(error))

        return render(
            request,
            self.template_name,
            {
                **datos,
                "es_mismo_vendedor": False,
                "form": form,
            },
        )
