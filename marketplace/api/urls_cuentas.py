"""Rutas de login y CRUD administrativo.

Antes vivía en `marketplace/api_urls.py`; se mueve junto a `views_cuentas.py`
para que las dos mitades de la API (cuentas y pagos) cuelguen del mismo
paquete. Mismas rutas y mismo namespace de siempre (`marketplace_api`), solo
cambia dónde vive el archivo.
"""

from django.urls import path

from . import views_cuentas

app_name = "marketplace_api"

urlpatterns = [
    path("login/", views_cuentas.LoginAPIView.as_view(), name="login"),
    path(
        "vendedores/",
        views_cuentas.VendedorListCreateAPIView.as_view(),
        name="vendedores_lista",
    ),
    path(
        "vendedores/<int:pk>/",
        views_cuentas.VendedorDetailAPIView.as_view(),
        name="vendedor_detalle",
    ),
    path(
        "clientes/",
        views_cuentas.ClienteListCreateAPIView.as_view(),
        name="clientes_lista",
    ),
    path(
        "clientes/<int:pk>/",
        views_cuentas.ClienteDetailAPIView.as_view(),
        name="cliente_detalle",
    ),
    path("carros/", views_cuentas.CarroListCreateAPIView.as_view(), name="carros_lista"),
    path(
        "carros/<int:pk>/",
        views_cuentas.CarroDetailAPIView.as_view(),
        name="carro_detalle",
    ),
]
