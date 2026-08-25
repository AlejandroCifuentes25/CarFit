"""Capa de Aplicación (Service Layer).

Aquí vive el *algoritmo* del caso de uso "Crear Artículo": el orden de los
pasos, la transaccionalidad y la coordinación entre el Builder (dominio) y
las dependencias externas (infraestructura).

Reglas que se respetan aquí:

* **SRP** — el servicio orquesta; no valida atributos (eso es del Builder) ni
  sabe cómo se envía un correo (eso es de `infra/`).
* **DIP** — depende de los puertos `ValidadorDocumental` y `Notificador`, no
  de sus implementaciones. Las Factories resuelven el default; los tests
  inyectan dobles por constructor.
* El servicio **no conoce HTTP**: no recibe `request` ni devuelve
  `HttpResponse`. Se puede llamar desde un comando de consola o una tarea
  asíncrona sin cambiar nada.
"""

from django.db import transaction
from django.db.models import F
from dataclasses import dataclass

from .domain.exceptions import ArticuloInvalidoError, ErrorDeDominio
from .domain.builders import CarroBuilder
from .domain.exceptions import DocumentacionInvalidaError
from .infra.factories import NotificadorFactory, ValidadorDocumentalFactory
from .models import Carro, CarritoCompra, DocumentoCarro, Inventario, Repuesto


@dataclass(frozen=True)
class ArticuloCarrito:
    accion: str
    tipo_articulo: str
    articulo_id: int
    titulo: str
    precio: int
    vendedor_id: int
    vendedor_nombre: str
    detalle: dict


class PublicacionArticuloService:
    """Publica un vehículo en el marketplace a nombre de un vendedor."""

    def __init__(self, validador=None, notificador=None):
        # Inyección de dependencias: si no se inyecta nada, las Factories
        # deciden la implementación según las variables de entorno.
        self._validador = validador or ValidadorDocumentalFactory.crear()
        self._notificador = notificador or NotificadorFactory.crear()

    @transaction.atomic
    def crear_articulo(self, vendedor, datos):
        """Publica un carro y devuelve la instancia ya persistida.

        Args:
            vendedor: `Vendedor` dueño del artículo.
            datos: diccionario con los campos del formulario.

        Raises:
            ArticuloInvalidoError: el vehículo no cumple las invariantes.
            DocumentacionInvalidaError: los documentos no están vigentes.
        """
        documentos = self._armar_documentos(datos)

        carro = (
            CarroBuilder()
            .para_vendedor(vendedor)
            .con_identificacion(datos["placa"], datos["marca"], datos["modelo"])
            .con_caracteristicas(datos["color"], datos["kilometraje"], datos["estado"])
            .con_precio(datos["precio"])
            .con_descripcion(datos.get("descripcion", ""))
            .con_documentos(documentos)
            .build()
        )

        self._verificar_documentacion(carro.placa, documentos)

        carro.save()
        self._persistir_documentos(carro, documentos)
        self._actualizar_inventario(vendedor)
        self._notificador.notificar_publicacion(carro)

        return carro

    # ------------------------------------------------------------------
    # Pasos internos
    # ------------------------------------------------------------------

    def _armar_documentos(self, datos):
        """Traduce los campos planos del formulario a objetos del modelo."""
        especificaciones = (
            (DocumentoCarro.Tipo.SOAT, "soat"),
            (DocumentoCarro.Tipo.TECNOMECANICA, "tecnomecanica"),
        )
        return [
            DocumentoCarro(
                tipo_documento=tipo,
                fecha_expedicion=datos[f"{prefijo}_expedicion"],
                fecha_vencimiento=datos[f"{prefijo}_vencimiento"],
                archivo=datos.get(f"{prefijo}_archivo"),
            )
            for tipo, prefijo in especificaciones
        ]

    def _verificar_documentacion(self, placa, documentos):
        resultado = self._validador.validar(placa, documentos)
        if not resultado.es_valido:
            raise DocumentacionInvalidaError(resultado.motivos)

    def _persistir_documentos(self, carro, documentos):
        for documento in documentos:
            documento.carro = carro
        DocumentoCarro.objects.bulk_create(documentos)

    def _actualizar_inventario(self, vendedor):
        Inventario.objects.get_or_create(vendedor=vendedor)
        Inventario.objects.filter(vendedor=vendedor).update(
            cantidad_carro=F("cantidad_carro") + 1
        )

class CarritoComprasService:
    """Normaliza Carro y Repuesto para que un carrito los consuma después."""

    def __init__(self, carro_model=Carro, repuesto_model=Repuesto):
        self._carro_model = carro_model
        self._repuesto_model = repuesto_model

    def agregar_articulo(self, usuario, tipo_articulo, articulo_id):
        carrito = self._obtener_o_crear_carrito()
        articulo = self._obtener_articulo(tipo_articulo, articulo_id)
        self._asignar_al_carrito(carrito, articulo)
        self._recalcular_carrito(carrito)
        return self._armar_articulo_carrito("agregado", tipo_articulo, articulo)

    def quitar_articulo(self, usuario, tipo_articulo, articulo_id):
        carrito = self._obtener_o_crear_carrito()
        articulo = self._obtener_articulo(tipo_articulo, articulo_id)
        self._quitar_del_carrito(carrito, articulo)
        self._recalcular_carrito(carrito)
        return self._armar_articulo_carrito("quitado", tipo_articulo, articulo)

    def vaciar_carrito(self, usuario):
        carrito = self._obtener_o_crear_carrito()
        self._desasignar_todos_los_items(carrito)
        carrito.cantidad_producto = 0
        carrito.precio_total = 0
        carrito.save(update_fields=["cantidad_producto", "precio_total"])
        return carrito

    def calcular_total(self, usuario):
        carrito = self._obtener_o_crear_carrito()
        self._recalcular_carrito(carrito)
        return carrito.precio_total

    def confirmar_compra(self, usuario):
        carrito = self._obtener_o_crear_carrito()
        self._recalcular_carrito(carrito)
        if carrito.cantidad_producto == 0:
            raise ErrorDeDominio("El carrito está vacío.")
        return {
            "carrito_id": carrito.pk,
            "cantidad_producto": carrito.cantidad_producto,
            "precio_total": carrito.precio_total,
            "estado": "PENDIENTE_PAGO",
        }

    def _obtener_o_crear_carrito(self):
        carrito = CarritoCompra.objects.first()
        if carrito is None:
            carrito = CarritoCompra.objects.create()
        return carrito

    def _asignar_al_carrito(self, carrito, articulo):
        articulo.carrito_compra = carrito
        articulo.save(update_fields=["carrito_compra"])

    def _quitar_del_carrito(self, carrito, articulo):
        if articulo.carrito_compra_id != carrito.id:
            raise ErrorDeDominio("El artículo no está en el carrito.")
        articulo.carrito_compra = None
        articulo.save(update_fields=["carrito_compra"])

    def _desasignar_todos_los_items(self, carrito):
        carrito.carros.update(carrito_compra=None)
        carrito.repuestos.update(carrito_compra=None)

    def _recalcular_carrito(self, carrito):
        cantidad_carros = carrito.carros.count()
        cantidad_repuestos = carrito.repuestos.count()
        carrito.cantidad_producto = cantidad_carros + cantidad_repuestos
        carrito.precio_total = sum(carro.precio for carro in carrito.carros.all()) + sum(
            repuesto.precio for repuesto in carrito.repuestos.all()
        )
        carrito.save(update_fields=["cantidad_producto", "precio_total"])

    def _obtener_articulo(self, tipo_articulo, articulo_id):
        if tipo_articulo == "carro":
            try:
                return self._carro_model.objects.select_related("vendedor").get(
                    pk=articulo_id
                )
            except self._carro_model.DoesNotExist as error:
                raise ErrorDeDominio("No existe el carro solicitado.") from error

        if tipo_articulo == "repuesto":
            try:
                return self._repuesto_model.objects.select_related("vendedor").get(
                    pk=articulo_id
                )
            except self._repuesto_model.DoesNotExist as error:
                raise ErrorDeDominio("No existe el repuesto solicitado.") from error

        raise ErrorDeDominio("Tipo de artículo no soportado.")

    def _armar_articulo_carrito(self, accion, tipo_articulo, articulo):
        if isinstance(articulo, Carro):
            return ArticuloCarrito(
                accion=accion,
                tipo_articulo=tipo_articulo,
                articulo_id=articulo.pk,
                titulo=f"{articulo.marca} {articulo.modelo}",
                precio=articulo.precio,
                vendedor_id=articulo.vendedor_id,
                vendedor_nombre=articulo.vendedor.nombre,
                detalle={
                    "placa": articulo.placa,
                    "estado": articulo.estado,
                    "color": articulo.color,
                    "kilometraje": articulo.kilometraje,
                    "descripcion": articulo.descripcion,
                },
            )

        return ArticuloCarrito(
            accion=accion,
            tipo_articulo=tipo_articulo,
            articulo_id=articulo.pk,
            titulo=f"{articulo.tipo} - {articulo.modelo_carro}",
            precio=articulo.precio,
            vendedor_id=articulo.vendedor_id,
            vendedor_nombre=articulo.vendedor.nombre,
            detalle={
                "tipo": articulo.tipo,
                "modelo_carro": articulo.modelo_carro,
                "numero_serie": articulo.numero_serie,
                "estado": articulo.estado,
            },
        )
