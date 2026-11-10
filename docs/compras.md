# Catálogo y carrito (Flask)

El servicio `shopping_microservice.py` corre en el puerto 5004, se construye con
`Dockerfile.shopping` y se publica en el stack Compose como `shopping`. Nginx
dirige `/compras/v2/` al servicio. Las rutas Django `/comprar/`, `/carrito/` y
sus endpoints `/carrito/...` continúan disponibles como implementación heredada.

| Flask (nuevo) | Django (legado) |
|---|---|
| `/compras/v2/catalogo/` | `/comprar/` |
| `/compras/v2/carrito/` | `/carrito/` |
| `/compras/v2/api/carrito/total/` | `/carrito/total/` |
| `/compras/v2/api/carrito/agregar/<tipo>/<id>/` | `/carrito/agregar/<tipo>/<id>/` |
| `/compras/v2/api/carrito/quitar/<tipo>/<id>/` | `/carrito/quitar/<tipo>/<id>/` |
| `/compras/v2/api/carrito/vaciar/` | `/carrito/vaciar/` |
| `/compras/v2/health` | — |

- Usa la sesión de Django, valida CSRF en cambios del carrito y checkout, y
  reutiliza `CatalogoComprasService`, `CarritoComprasService`,
  `PagarCarritoService` y `PagoForm`.
- El checkout conserva las reglas y pasarelas existentes. Tras procesar pagos,
  redirige al detalle Django del primer pago; historial, detalle y factura no
  forman parte de esta migración.
- Cada cliente ahora tiene su propio carrito. La migración agrega la relación
  como nullable; cualquier carrito anterior queda sin cliente asignado y sus
  artículos no se trasladan automáticamente a una cuenta.
- Las rutas anteriores de Django siguen disponibles. El menú principal dirige
  catálogo y carrito al nuevo servicio Flask.
- Para ejecutar la ruta por el gateway, inicia `docker compose up --build` y
  visita `http://127.0.0.1:8000/compras/v2/catalogo/`.

Pruebas enfocadas:
`python manage.py test marketplace.tests.test_shopping_microservice marketplace.tests.test_carrito`.
