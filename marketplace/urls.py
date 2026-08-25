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
    path(
        "carrito/agregar/<str:tipo_articulo>/<int:articulo_id>/",
        views.AgregarArticuloCarrito.as_view(),
        name="agregar_articulo_carrito",
    ),
    path(
        "carrito/quitar/<str:tipo_articulo>/<int:articulo_id>/",
        views.QuitarArticuloCarrito.as_view(),
        name="quitar_articulo_carrito",
    ),
    path(
        "carrito/vaciar/",
        views.VaciarCarritoView.as_view(),
        name="vaciar_carrito",
    ),
    path(
        "carrito/total/",
        views.CalcularTotalCarritoView.as_view(),
        name="calcular_total_carrito",
    ),
    path(
        "carrito/confirmar/",
        views.ConfirmarCompraCarritoView.as_view(),
        name="confirmar_compra_carrito",
    ),
]
