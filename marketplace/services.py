"""Capa de Aplicación (Service Layer).

Aquí viven los *algoritmos* de los casos de uso "Crear Artículo" y
"Pagar un Artículo": el orden de los pasos, la transaccionalidad y la
coordinación entre los Builders (dominio) y las dependencias externas
(infraestructura).

Reglas que se respetan aquí:

* **SRP**: el servicio orquesta; no valida atributos (eso es del Builder) ni
  sabe cómo se envía un correo (eso es de `infra/`).
* **DIP**: depende de los puertos `ValidadorDocumental` y `Notificador`, no
  de sus implementaciones. Las Factories resuelven el default; los tests
  inyectan dobles por constructor.
* El servicio **no conoce HTTP**: no recibe `request` ni devuelve
  `HttpResponse`. Se puede llamar desde un comando de consola o una tarea
  asíncrona sin cambiar nada.
"""

from dataclasses import dataclass

from django.contrib.auth import authenticate, login
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.db.models import F

from .domain.builders import CarroBuilder, PagoBuilder
from .domain.exceptions import (
    ArticuloNoDisponibleError,
    CredencialesInvalidasError,
    DocumentacionInvalidaError,
    ErrorDeDominio,
    NombreDeUsuarioEnUsoError,
    PagoDuplicadoError,
    PagoInvalidoError,
    RecursoNoEncontradoError,
    TransicionPagoInvalidaError,
)
from .domain.facturas import Factura, generar_factura
from .domain.metodos_pago import metodos_disponibles, obtener_especificacion
from .domain.ports import ResultadoTransaccion, SolicitudPago
from .infra.factories import (
    NotificadorFactory,
    NotificadorPagosFactory,
    PasarelaPagoFactory,
    ValidadorDocumentalFactory,
)
from .models import Carro, CarritoCompra, Cliente, DocumentoCarro, Inventario, Pago, Repuesto, TransaccionPago, Vendedor


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

        try:
            carro.save()
        except IntegrityError:
            raise ErrorDeDominio("Ya existe un vehículo registrado con esta placa.")

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


# ----------------------------------------------------------------------
# Pagos
# ----------------------------------------------------------------------

#: Traducción del vocabulario del dominio al que persiste la base de datos.
#: Vive en el Service Layer porque es exactamente su oficio: coordinar
#: dominio y persistencia sin que ninguno de los dos conozca al otro.
ESTADO_SEGUN_RESULTADO = {
    ResultadoTransaccion.APROBADA: Pago.Estado.APROBADO,
    ResultadoTransaccion.PENDIENTE: Pago.Estado.PENDIENTE,
    ResultadoTransaccion.RECHAZADA: Pago.Estado.RECHAZADO,
}

#: Un artículo con un pago en estos estados está comprometido: o ya se
#: vendió, o hay un pago en curso que puede aprobarse en cualquier momento.
ESTADOS_QUE_COMPROMETEN_ARTICULO = (Pago.Estado.APROBADO, Pago.Estado.PENDIENTE)


class BitacoraPagos:
    """Deja constancia de cada interacción con una pasarela.

    Es una clase aparte y no un método más del servicio porque auditar no
    es cobrar: si mañana la bitácora se manda a un sistema externo de
    trazabilidad, cambia esta clase y ningún servicio se entera (SRP).
    """

    def registrar(self, pago, operacion, pasarela, resultado) -> TransaccionPago:
        return TransaccionPago.objects.create(
            pago=pago,
            operacion=operacion,
            pasarela=pasarela,
            estado_resultante=ESTADO_SEGUN_RESULTADO[resultado.resultado],
            codigo_autorizacion=resultado.codigo_autorizacion[:60],
            mensaje=resultado.mensaje[:200],
        )


class CatalogoMetodosPagoService:
    """Responde qué métodos de pago puede usar el comprador.

    Existe para que la capa de presentación no arme la lista a mano: el
    catálogo y sus límites son del dominio, y la API solo los expone.
    """

    def listar(self, monto=None):
        """Métodos soportados; si se pasa `monto`, solo los que aplican."""
        return metodos_disponibles(monto)

    def obtener(self, codigo):
        """Especificación de un método concreto.

        Raises:
            MetodoPagoNoSoportadoError: el código no existe.
        """
        return obtener_especificacion(codigo)


class CatalogoComprasService:
    """Determina qué artículos pueden mostrarse como comprables.

    La disponibilidad es una regla de negocio: un artículo con un pago
    pendiente o aprobado no se puede ofrecer de nuevo. La presentación solo
    consume el resultado de este servicio y lo entrega a la plantilla.
    """

    def __init__(self, carro_model=Carro, repuesto_model=Repuesto):
        self._carro_model = carro_model
        self._repuesto_model = repuesto_model

    def listar_disponibles(self, usuario):
        carros = self._carro_model.objects.exclude(
            pagos__estado__in=ESTADOS_QUE_COMPROMETEN_ARTICULO
        )
        repuestos = self._repuesto_model.objects.exclude(
            pagos__estado__in=ESTADOS_QUE_COMPROMETEN_ARTICULO
        )
        vendedor_propio = getattr(usuario, "vendedor", None)
        if vendedor_propio is not None:
            carros = carros.exclude(vendedor=vendedor_propio)
            repuestos = repuestos.exclude(vendedor=vendedor_propio)
        return carros.distinct(), repuestos.distinct()


class ProcesarPagoService:
    """Cobra un artículo del marketplace a nombre de un cliente.

    Este es el algoritmo del caso de uso, y nada más que el algoritmo:

    1. Ubicar el artículo y confirmar que todavía se puede comprar.
    2. Construir el pago con el Builder, que aplica las invariantes.
    3. Verificar la idempotencia por referencia.
    4. Pedirle a la pasarela (la que decida la Factory según el método)
       que cobre.
    5. Guardar el desenlace, dejar bitácora y avisarle al cliente.

    Ninguno de esos pasos calcula comisiones (eso es del dominio) ni sabe
    cómo se habla con un agregador (eso es de `infra/`), ni conoce HTTP: el
    servicio recibe un `Cliente` y un diccionario, no un `request`.
    """

    def __init__(self, pasarela_factory=None, notificador=None, bitacora=None):
        # Inyección de dependencias: sin argumentos, las Factories deciden
        # según el entorno; en las pruebas se inyectan dobles.
        self._pasarela_factory = pasarela_factory or PasarelaPagoFactory
        self._notificador = notificador or NotificadorPagosFactory.crear()
        self._bitacora = bitacora or BitacoraPagos()

    def procesar(self, cliente, datos) -> Pago:
        """Ejecuta el cobro y devuelve el `Pago` ya persistido.

        El pago se devuelve tanto si quedó APROBADO como si quedó PENDIENTE
        o RECHAZADO: un rechazo del emisor es un desenlace legítimo del caso
        de uso, no un error del programa. Quien llama decide cómo
        representarlo.

        Args:
            cliente: `Cliente` que paga.
            datos: diccionario ya validado en formato por la capa de
                presentación.

        Raises:
            RecursoNoEncontradoError: el artículo no existe.
            ArticuloNoDisponibleError: el artículo ya está comprometido.
            PagoInvalidoError: los datos no cumplen las invariantes.
            PagoDuplicadoError: la referencia ya se usó.
            PasarelaNoDisponibleError: el proveedor de pagos falló.
        """
        articulo = self._resolver_articulo(datos)
        self._verificar_disponibilidad(articulo)

        builder = self._armar_builder(cliente, articulo, datos)
        pago = builder.build()
        self._verificar_referencia_libre(pago.referencia)

        # La llamada a la pasarela ocurre **fuera** de la transacción: es una
        # petición de red que puede tardar segundos y mantener abierta una
        # transacción de base de datos mientras tanto bloquea filas sin
        # necesidad.
        pasarela = self._pasarela_factory.crear(pago.metodo_pago)
        resultado = pasarela.procesar(
            self._armar_solicitud(pago, articulo, builder.datos_metodo())
        )

        self._registrar_desenlace(
            pago, pasarela, resultado, TransaccionPago.Operacion.PROCESAR
        )
        self._notificador.notificar_resultado(pago)

        return pago

    # ------------------------------------------------------------------
    # Pasos internos
    # ------------------------------------------------------------------

    def _resolver_articulo(self, datos):
        """Ubica el carro o el repuesto que se está comprando."""
        carro_id = datos.get("carro")
        repuesto_id = datos.get("repuesto")

        if carro_id and repuesto_id:
            raise PagoInvalidoError(
                ["Un pago cubre un solo artículo: o un carro o un repuesto."]
            )
        if not carro_id and not repuesto_id:
            raise PagoInvalidoError(
                ["Hay que indicar el carro o el repuesto que se está pagando."]
            )

        if carro_id:
            articulo = Carro.objects.filter(pk=carro_id).first()
            if articulo is None:
                raise RecursoNoEncontradoError("el carro", carro_id)
            return articulo

        articulo = Repuesto.objects.filter(pk=repuesto_id).first()
        if articulo is None:
            raise RecursoNoEncontradoError("el repuesto", repuesto_id)
        return articulo

    def _verificar_disponibilidad(self, articulo):
        """Impide cobrar dos veces el mismo artículo."""
        filtro = (
            {"carro": articulo}
            if isinstance(articulo, Carro)
            else {"repuesto": articulo}
        )
        comprometido = Pago.objects.filter(
            estado__in=ESTADOS_QUE_COMPROMETEN_ARTICULO, **filtro
        ).exists()

        if comprometido:
            raise ArticuloNoDisponibleError(
                articulo,
                f"El artículo '{articulo}' ya tiene un pago aprobado o en curso.",
            )

    def _verificar_referencia_libre(self, referencia):
        if Pago.objects.filter(referencia=referencia).exists():
            raise PagoDuplicadoError(referencia)

    def _armar_builder(self, cliente, articulo, datos):
        builder = (
            PagoBuilder()
            .para_cliente(cliente)
            .con_metodo(datos.get("metodo_pago"), self._datos_del_metodo(datos))
            .con_cuotas(datos.get("cuotas") or 1)
        )
        if datos.get("referencia"):
            builder.con_referencia(datos["referencia"])

        if isinstance(articulo, Carro):
            return builder.por_carro(articulo)
        return builder.por_repuesto(articulo)

    def _datos_del_metodo(self, datos):
        """Extrae los datos sensibles que viajan a la pasarela.

        Se listan explícitamente en lugar de reenviar todo el diccionario:
        así ningún campo inesperado del cliente termina en la petición al
        proveedor.
        """
        campos = (
            "token_tarjeta",
            "banco",
            "tipo_persona",
            "documento_pagador",
            "telefono",
        )
        return {campo: datos[campo] for campo in campos if datos.get(campo)}

    def _armar_solicitud(self, pago, articulo, datos_metodo) -> SolicitudPago:
        return SolicitudPago(
            referencia=pago.referencia,
            monto=pago.total,
            moneda=pago.moneda,
            metodo=pago.metodo_pago,
            cuotas=pago.cuotas,
            descripcion=f"CarFit - {articulo}",
            correo_pagador=pago.cliente.correo,
            datos_metodo=datos_metodo,
        )

    @transaction.atomic
    def _registrar_desenlace(self, pago, pasarela, resultado, operacion):
        """Guarda el pago con el estado que devolvió la pasarela."""
        pago.estado = ESTADO_SEGUN_RESULTADO[resultado.resultado]
        pago.pasarela = pasarela.nombre
        pago.referencia_pasarela = resultado.referencia_pasarela[:80]
        pago.codigo_autorizacion = resultado.codigo_autorizacion[:60]
        pago.mensaje = resultado.mensaje[:200]

        try:
            pago.save()
        except IntegrityError:
            # Dos peticiones simultáneas con la misma referencia: la
            # restricción de unicidad de la base de datos es la última
            # línea de defensa contra el doble cobro.
            raise PagoDuplicadoError(pago.referencia) from None

        self._bitacora.registrar(pago, operacion, pasarela.nombre, resultado)


class ConsultarPagoService:
    """Recupera pagos ya registrados.

    Separado de `ProcesarPagoService` porque consultar y cobrar son
    responsabilidades distintas: una lee, la otra mueve dinero.
    """

    def obtener(self, referencia, cliente=None) -> Pago:
        """Devuelve el pago de `referencia`.

        Cuando se pasa `cliente`, la búsqueda se restringe a sus pagos: un
        cliente no puede consultar el pago de otro, y la respuesta es la
        misma que si no existiera para no filtrar información.

        Raises:
            RecursoNoEncontradoError: no hay un pago así para ese cliente.
        """
        filtro = {"referencia": referencia}
        if cliente is not None:
            filtro["cliente"] = cliente

        pago = Pago.objects.filter(**filtro).first()
        if pago is None:
            raise RecursoNoEncontradoError("el pago", referencia)
        return pago

    def listar(self, cliente):
        """Historial de pagos del cliente, del más reciente al más antiguo."""
        return Pago.objects.filter(cliente=cliente)


class FacturaService:
    """Genera la factura de un pago propio.

    Corresponde a `Pago.Generar_Factura()` del diagrama de clases. Vive
    aparte de `ConsultarPagoService` porque generar un documento no es lo
    mismo que leer un registro: aquí además se aplica la regla de negocio
    de que solo un pago aprobado es facturable.
    """

    def __init__(self, consulta=None):
        self._consulta = consulta or ConsultarPagoService()

    def generar(self, referencia, cliente=None) -> Factura:
        """Devuelve la factura de `referencia`.

        Raises:
            RecursoNoEncontradoError: no existe ese pago para el cliente.
            PagoNoFacturableError: el pago no está en estado APROBADO.
        """
        pago = self._consulta.obtener(referencia, cliente)
        return generar_factura(pago)


class ConfirmarPagoService:
    """Resuelve un pago que quedó pendiente.

    PSE y efectivo no confirman en el momento: el cliente sale a su banco o
    a un corresponsal y el desenlace llega después. Este servicio le
    pregunta a la pasarela en qué quedó la transacción y actualiza el pago.
    """

    def __init__(self, pasarela_factory=None, notificador=None, bitacora=None):
        self._pasarela_factory = pasarela_factory or PasarelaPagoFactory
        self._notificador = notificador or NotificadorPagosFactory.crear()
        self._bitacora = bitacora or BitacoraPagos()
        self._consulta = ConsultarPagoService()

    def confirmar(self, referencia, cliente=None) -> Pago:
        """Actualiza el pago con lo que reporte la pasarela.

        Raises:
            RecursoNoEncontradoError: el pago no existe.
            TransicionPagoInvalidaError: el pago ya estaba resuelto.
            PasarelaNoDisponibleError: el proveedor de pagos falló.
        """
        pago = self._consulta.obtener(referencia, cliente)

        if pago.estado != Pago.Estado.PENDIENTE:
            raise TransicionPagoInvalidaError(
                pago.referencia, pago.estado, Pago.Estado.APROBADO
            )

        pasarela = self._pasarela_factory.crear(pago.metodo_pago)
        resultado = pasarela.consultar(pago.referencia_pasarela or pago.referencia)

        estado_anterior = pago.estado
        self._actualizar(pago, pasarela, resultado)

        # Solo se molesta al cliente cuando de verdad cambió algo: un pago
        # que sigue pendiente no amerita otro correo.
        if pago.estado != estado_anterior:
            self._notificador.notificar_resultado(pago)

        return pago

    @transaction.atomic
    def _actualizar(self, pago, pasarela, resultado):
        pago.estado = ESTADO_SEGUN_RESULTADO[resultado.resultado]
        pago.codigo_autorizacion = (
            resultado.codigo_autorizacion[:60] or pago.codigo_autorizacion
        )
        pago.mensaje = resultado.mensaje[:200]
        pago.save(
            update_fields=["estado", "codigo_autorizacion", "mensaje", "actualizado_en"]
        )
        self._bitacora.registrar(
            pago, TransaccionPago.Operacion.CONFIRMAR, pasarela.nombre, resultado
        )


class AutenticacionService:
    def iniciar_sesion(self, request, username, password):
        usuario = authenticate(request, username=username, password=password)
        if usuario is None:
            raise CredencialesInvalidasError()
        login(request, usuario)
        return usuario


class RegistroUsuarioService:
    def registrar(self, request, rol, datos):
        if User.objects.filter(username=datos["username"]).exists():
            raise NombreDeUsuarioEnUsoError(datos["username"])
        with transaction.atomic():
            usuario = User.objects.create_user(
                username=datos["username"], password=datos["password"]
            )
            # Siempre se crea perfil de Cliente para que puedan comprar
            Cliente.objects.create(
                usuario=usuario, nombre=datos["nombre"], correo=datos["correo"],
                direccion=datos["direccion"], numero_tel=datos["numero_tel"],
            )
            if rol == "VENDEDOR":
                Vendedor.objects.create(
                    usuario=usuario, nombre=datos["nombre"], correo=datos["correo"],
                    direccion=datos["direccion"], numero_tel=datos["numero_tel"],
                )
        login(request, usuario)
        return usuario


class CarritoComprasService:
    def __init__(self, carro_model=Carro, repuesto_model=Repuesto):
        self._carro_model, self._repuesto_model = carro_model, repuesto_model

    def agregar_articulo(self, usuario, tipo_articulo, articulo_id):
        carrito, articulo = self._obtener_o_crear_carrito(), self._obtener_articulo(tipo_articulo, articulo_id)
        articulo.carrito_compra = carrito
        articulo.save(update_fields=["carrito_compra"])
        self._recalcular(carrito)
        return self._respuesta("agregado", tipo_articulo, articulo)

    def quitar_articulo(self, usuario, tipo_articulo, articulo_id):
        carrito, articulo = self._obtener_o_crear_carrito(), self._obtener_articulo(tipo_articulo, articulo_id)
        if articulo.carrito_compra_id != carrito.id:
            raise ErrorDeDominio("El artículo no está en el carrito.")
        articulo.carrito_compra = None
        articulo.save(update_fields=["carrito_compra"])
        self._recalcular(carrito)
        return self._respuesta("quitado", tipo_articulo, articulo)

    def vaciar_carrito(self, usuario):
        carrito = self._obtener_o_crear_carrito()
        carrito.carros.update(carrito_compra=None)
        carrito.repuestos.update(carrito_compra=None)
        carrito.cantidad_producto, carrito.precio_total = 0, 0
        carrito.save(update_fields=["cantidad_producto", "precio_total"])
        return carrito

    def calcular_total(self, usuario):
        carrito = self._obtener_o_crear_carrito()
        self._recalcular(carrito)
        return carrito.precio_total

    def confirmar_compra(self, usuario):
        carrito = self._obtener_o_crear_carrito()
        self._recalcular(carrito)
        if not carrito.cantidad_producto:
            raise ErrorDeDominio("El carrito está vacío.")
        return {"carrito_id": carrito.pk, "cantidad_producto": carrito.cantidad_producto, "precio_total": carrito.precio_total, "estado": "PENDIENTE_PAGO"}

    def _obtener_o_crear_carrito(self):
        return CarritoCompra.objects.first() or CarritoCompra.objects.create()

    def _obtener_articulo(self, tipo, articulo_id):
        modelo = {"carro": self._carro_model, "repuesto": self._repuesto_model}.get(tipo)
        if modelo is None:
            raise ErrorDeDominio("Tipo de artículo no soportado.")
        try:
            return modelo.objects.select_related("vendedor").get(pk=articulo_id)
        except modelo.DoesNotExist as error:
            raise ErrorDeDominio(f"No existe el {tipo} solicitado.") from error

    def _recalcular(self, carrito):
        carrito.cantidad_producto = carrito.carros.count() + carrito.repuestos.count()
        carrito.precio_total = sum(x.precio for x in carrito.carros.all()) + sum(x.precio for x in carrito.repuestos.all())
        carrito.save(update_fields=["cantidad_producto", "precio_total"])

    def _respuesta(self, accion, tipo, articulo):
        if isinstance(articulo, Carro):
            titulo, detalle = f"{articulo.marca} {articulo.modelo}", {"placa": articulo.placa}
        else:
            titulo, detalle = f"{articulo.tipo} - {articulo.modelo_carro}", {"numero_serie": articulo.numero_serie}
        return ArticuloCarrito(accion, tipo, articulo.pk, titulo, articulo.precio, articulo.vendedor_id, articulo.vendedor.nombre, detalle)
