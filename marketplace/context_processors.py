"""Contexto compartido para la experiencia de carrito."""

from .services import CarritoComprasService


def carrito_compra(request):
    if not request.user.is_authenticated:
        return {
            "carrito_total": 0,
            "carrito_cantidad": 0,
            "carrito_carros_ids": [],
            "carrito_repuestos_ids": [],
        }

    resumen = CarritoComprasService().obtener_resumen(request.user)
    carrito = resumen["carrito"]

    return {
        "carrito_total": carrito.precio_total,
        "carrito_cantidad": carrito.cantidad_producto,
        "carrito_carros_ids": list(carrito.carros.values_list("pk", flat=True)),
        "carrito_repuestos_ids": list(carrito.repuestos.values_list("pk", flat=True)),
    }