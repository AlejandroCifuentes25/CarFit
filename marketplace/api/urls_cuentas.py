"""Rutas de login y CRUD administrativo.

Antes vivía en `marketplace/api_urls.py`; se mueve junto a `views.py` para
que las dos mitades de la API (cuentas y pagos) cuelguen del mismo paquete.
Mismas rutas y mismo namespace de siempre (`marketplace_api`), solo cambia
dónde vive el archivo.
"""

from django.urls import path

from . import views

app_name = "marketplace_api"

urlpatterns = [
    path("login/", views.LoginAPIView.as_view(), name="login"),
    path(
        "vendedores/",
        views.VendedorListCreateAPIView.as_view(),
        name="vendedores_lista",
    ),
    path(
        "vendedores/<int:pk>/",
        views.VendedorDetailAPIView.as_view(),
        name="vendedor_detalle",
    ),
    path(
        "clientes/",
        views.ClienteListCreateAPIView.as_view(),
        name="clientes_lista",
    ),
    path(
        "clientes/<int:pk>/",
        views.ClienteDetailAPIView.as_view(),
        name="cliente_detalle",
    ),
    path("carros/", views.CarroListCreateAPIView.as_view(), name="carros_lista"),
    path(
        "carros/<int:pk>/",
        views.CarroDetailAPIView.as_view(),
        name="carro_detalle",
    ),
    path(
        "publicar-repuesto/",
        views.PublicarRepuestoAPIView.as_view(),
        name="api_publicar_repuesto",
    ),
]
