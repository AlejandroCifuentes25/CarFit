"""Contexto compartido para la experiencia de carrito."""

from django.conf import settings
from django.urls import reverse

from .services import CarritoComprasService


def carrito_compra(request):
    navegacion = {
        "catalogo_web_url": "/compras/v2/catalogo/" if settings.CARFIT_FLASK_COMPRAS else reverse("marketplace:catalogo_compras"),
        "carrito_web_url": "/compras/v2/carrito/" if settings.CARFIT_FLASK_COMPRAS else reverse("marketplace:carrito"),
    }
    if not request.user.is_authenticated or not hasattr(request.user, "cliente"):
        return {
            **navegacion,
            "carrito_total": 0,
            "carrito_cantidad": 0,
            "carrito_carros_ids": [],
            "carrito_repuestos_ids": [],
        }

    resumen = CarritoComprasService().obtener_resumen(request.user)
    carrito = resumen["carrito"]

    return {
        **navegacion,
        "carrito_total": carrito.precio_total,
        "carrito_cantidad": carrito.cantidad_producto,
        "carrito_carros_ids": list(carrito.carros.values_list("pk", flat=True)),
        "carrito_repuestos_ids": list(carrito.repuestos.values_list("pk", flat=True)),
    }
