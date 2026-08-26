from django.urls import path

from . import views
from .api import views as api_views

app_name = "marketplace"

urlpatterns = [
    path("", views.IndexView.as_view(), name="index"),
    path("registro/", views.RegistroView.as_view(), name="registro"),
    path("articulos/nuevo/", views.CrearArticuloView.as_view(), name="crear_articulo"),
    path(
        "articulos/nuevo/repuesto/",
        views.CrearRepuestoView.as_view(),
        name="crear_repuesto",
    ),
    path(
        "articulos/publicado/",
        views.ArticuloPublicadoView.as_view(),
        name="articulo_publicado",
    ),
    path("mis-publicaciones/", views.MisPublicacionesView.as_view(), name="mis_publicaciones"),
    path("articulos/editar/<str:tipo>/<int:pk>/", views.EditarArticuloView.as_view(), name="editar_articulo"),
    path("articulos/eliminar/<str:tipo>/<int:pk>/", views.EliminarArticuloView.as_view(), name="eliminar_articulo"),
    path("comprar/", views.CatalogoComprasView.as_view(), name="catalogo_compras"),
    path("carrito/", views.CarritoComprasView.as_view(), name="carrito"),
    path(
        "comprar/<str:tipo>/<int:pk>/pagar/",
        views.PagarArticuloView.as_view(),
        name="pagar_articulo",
    ),
    path("pagos/", views.HistorialPagosView.as_view(), name="historial_pagos"),
    path(
        "pagos/<str:referencia>/",
        views.DetallePagoView.as_view(),
        name="detalle_pago",
    ),
    path(
        "pagos/<str:referencia>/confirmar/",
        views.ConfirmarPagoView.as_view(),
        name="confirmar_pago",
    ),
    path(
        "pagos/<str:referencia>/factura/",
        views.FacturaPagoView.as_view(),
        name="factura_pago",
    ),
    path("carrito/agregar/<str:tipo_articulo>/<int:articulo_id>/", api_views.AgregarArticuloCarrito.as_view(), name="agregar_articulo_carrito"),
    path("carrito/quitar/<str:tipo_articulo>/<int:articulo_id>/", api_views.QuitarArticuloCarrito.as_view(), name="quitar_articulo_carrito"),
    path("carrito/vaciar/", api_views.VaciarCarritoView.as_view(), name="vaciar_carrito"),
    path("carrito/total/", api_views.CalcularTotalCarritoView.as_view(), name="calcular_total_carrito"),
    path("carrito/confirmar/", api_views.ConfirmarCompraCarritoView.as_view(), name="confirmar_compra_carrito"),
]
