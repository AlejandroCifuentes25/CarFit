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
]
