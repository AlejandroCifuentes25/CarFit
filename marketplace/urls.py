from django.urls import path

from . import views

app_name = "marketplace"

urlpatterns = [
    path("articulos/nuevo/", views.CrearArticuloView.as_view(), name="crear_articulo"),
    path(
        "articulos/publicado/",
        views.ArticuloPublicadoView.as_view(),
        name="articulo_publicado",
    ),
    path("comprar/", views.CatalogoComprasView.as_view(), name="catalogo_compras"),
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
]
