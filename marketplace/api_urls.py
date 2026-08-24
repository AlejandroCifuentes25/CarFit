"""Rutas de la API (DRF).

Separadas de `urls.py` (HTML) y montadas bajo el prefijo `/api/` en
`carfit/urls.py`. Este aislamiento es, además, el primer paso para poner un
API Gateway delante: todo lo que necesita quedar expuesto como servicio
cuelga de un único prefijo.
"""

from django.urls import path

from . import api_views

app_name = "marketplace_api"

urlpatterns = [
    path("login/", api_views.LoginAPIView.as_view(), name="login"),
    path(
        "vendedores/",
        api_views.VendedorListCreateAPIView.as_view(),
        name="vendedores_lista",
    ),
    path(
        "vendedores/<int:pk>/",
        api_views.VendedorDetailAPIView.as_view(),
        name="vendedor_detalle",
    ),
    path(
        "clientes/",
        api_views.ClienteListCreateAPIView.as_view(),
        name="clientes_lista",
    ),
    path(
        "clientes/<int:pk>/",
        api_views.ClienteDetailAPIView.as_view(),
        name="cliente_detalle",
    ),
    path("carros/", api_views.CarroListCreateAPIView.as_view(), name="carros_lista"),
    path(
        "carros/<int:pk>/",
        api_views.CarroDetailAPIView.as_view(),
        name="carro_detalle",
    ),
]
