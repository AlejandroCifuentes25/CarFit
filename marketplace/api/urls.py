"""Rutas de la API REST de pagos.

Todas cuelgan de `/api/` con nombres de recurso en plural, sin verbos en la
URL: la acción la indica el método HTTP. Esa disciplina es la que permite
que un API Gateway enrute por prefijo (`/api/pagos/*` hacia el servicio de
pagos) sin conocer la implementación.
"""

from django.urls import path

from . import views

app_name = "api"

urlpatterns = [
    # Va antes que el detalle: si no, "metodos" se leería como una referencia.
    path(
        "pagos/metodos/",
        views.MetodosPagoAPIView.as_view(),
        name="metodos-pago",
    ),
    path("pagos/", views.PagosAPIView.as_view(), name="pagos"),
    path(
        "pagos/<str:referencia>/",
        views.DetallePagoAPIView.as_view(),
        name="detalle-pago",
    ),
    path(
        "pagos/<str:referencia>/confirmar/",
        views.ConfirmacionPagoAPIView.as_view(),
        name="confirmar-pago",
    ),
    path(
        "pagos/<str:referencia>/factura/",
        views.FacturaPagoAPIView.as_view(),
        name="factura-pago",
    ),
]
