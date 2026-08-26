"""Capa de Presentación de la API (Django REST Framework).

Se usa `APIView` (o `generics.*APIView` para el CRUD administrativo) y no
`ViewSet`, para tener control explícito de cada método HTTP y de cada
código de estado, que es lo que se está evaluando.

Ninguna de estas vistas contiene reglas de negocio. Su trabajo completo es:

1. Validar el *formato* de la entrada con un serializer.
2. Llamar al servicio correspondiente.
3. Traducir el desenlace a un código HTTP.

Si alguna de estas clases empieza a calcular comisiones o a decidir si un
artículo está disponible, la lógica está en el lugar equivocado.

Se agrupan aquí las tres familias de endpoints (cuentas, carrito y pagos)
en vez de un archivo por familia: es la misma convención que ya usan
`services.py`, `domain/builders.py` e `infra/factories.py` en el resto del
proyecto.
"""

from rest_framework import generics, permissions, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..domain.exceptions import CredencialesInvalidasError, ErrorDeDominio, RecursoNoEncontradoError
from ..models import Carro, Cliente, Pago, Vendedor
from ..services import (
    AutenticacionService,
    CarritoComprasService,
    CatalogoMetodosPagoService,
    ConfirmarPagoService,
    ConsultarPagoService,
    FacturaService,
    ProcesarPagoService,
)
from .errores import respuesta_de_error
from .serializers import (
    ArticuloCarritoSerializer,
    CarroSerializer,
    ClienteSerializer,
    CrearPagoSerializer,
    EspecificacionMetodoPagoSerializer,
    FacturaSerializer,
    LoginSerializer,
    MovimientoCarritoSerializer,
    PagoSerializer,
    VendedorSerializer,
)

# ---------------------------------------------------------------------
# Cuentas: login y CRUD administrativo (solo usuarios staff)
# ---------------------------------------------------------------------


class LoginAPIView(APIView):
    """Inicia sesión de un usuario (Vendedor, Cliente o Administrador).

    La sesión queda asociada por cookie, igual que el login HTML ya
    existente en `/cuentas/login/`: ambos comparten `AutenticacionService`.
    """

    permission_classes = [permissions.AllowAny]
    # Inyectable desde las pruebas: LoginAPIView.as_view(service_factory=...)
    service_factory = AutenticacionService

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            usuario = self.service_factory().iniciar_sesion(
                request, **serializer.validated_data
            )
        except CredencialesInvalidasError as error:
            return respuesta_de_error(error)

        return Response(
            {"id": usuario.id, "username": usuario.username, "is_staff": usuario.is_staff},
            status=status.HTTP_200_OK,
        )


class VendedorListCreateAPIView(generics.ListCreateAPIView):
    queryset = Vendedor.objects.all()
    serializer_class = VendedorSerializer
    permission_classes = [permissions.IsAdminUser]


class VendedorDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Vendedor.objects.all()
    serializer_class = VendedorSerializer
    permission_classes = [permissions.IsAdminUser]


class ClienteListCreateAPIView(generics.ListCreateAPIView):
    queryset = Cliente.objects.all()
    serializer_class = ClienteSerializer
    permission_classes = [permissions.IsAdminUser]


class ClienteDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Cliente.objects.all()
    serializer_class = ClienteSerializer
    permission_classes = [permissions.IsAdminUser]


class CarroListCreateAPIView(generics.ListCreateAPIView):
    queryset = Carro.objects.all()
    serializer_class = CarroSerializer
    permission_classes = [permissions.IsAdminUser]


class CarroDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Carro.objects.all()
    serializer_class = CarroSerializer
    permission_classes = [permissions.IsAdminUser]


# ---------------------------------------------------------------------
# Carrito de compras
# ---------------------------------------------------------------------


class BaseCarritoView(APIView):
    """Comparten permisos, el service y la traducción de errores de dominio."""

    permission_classes = [IsAuthenticated]
    service_factory = CarritoComprasService

    def get_service(self):
        return self.service_factory()

    def ejecutar_y_responder(self, operacion, serializar=lambda resultado: resultado):
        try:
            resultado = operacion()
        except ErrorDeDominio as error:
            return respuesta_de_error(error)
        return Response(serializar(resultado))


class BaseArticuloCarritoView(BaseCarritoView):
    def post(self, request, *args, **kwargs):
        serializer = MovimientoCarritoSerializer(data=kwargs)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        return self.ejecutar_y_responder(
            lambda: self.ejecutar(self.get_service(), request.user, datos),
            serializar=lambda resultado: ArticuloCarritoSerializer(resultado).data,
        )


class AgregarArticuloCarrito(BaseArticuloCarritoView):
    def ejecutar(self, servicio, usuario, datos):
        return servicio.agregar_articulo(usuario, datos["tipo_articulo"], datos["articulo_id"])


class QuitarArticuloCarrito(BaseArticuloCarritoView):
    def ejecutar(self, servicio, usuario, datos):
        return servicio.quitar_articulo(usuario, datos["tipo_articulo"], datos["articulo_id"])


class BaseCarritoOperacionView(BaseCarritoView):
    def post(self, request, *args, **kwargs):
        return self.ejecutar_y_responder(lambda: self.ejecutar(self.get_service(), request.user))


class VaciarCarritoView(BaseCarritoOperacionView):
    def ejecutar(self, servicio, usuario):
        carrito = servicio.vaciar_carrito(usuario)
        return {
            "carrito_id": carrito.pk,
            "cantidad_producto": carrito.cantidad_producto,
            "precio_total": carrito.precio_total,
        }


class CalcularTotalCarritoView(BaseCarritoOperacionView):
    def ejecutar(self, servicio, usuario):
        return {"precio_total": servicio.calcular_total(usuario)}


class ConfirmarCompraCarritoView(BaseCarritoOperacionView):
    def ejecutar(self, servicio, usuario):
        return servicio.confirmar_compra(usuario)


# ---------------------------------------------------------------------
# Pagos
# ---------------------------------------------------------------------

#: Cómo se representa en HTTP cada desenlace del cobro. Un pago rechazado sí
#: se registró (existe, tiene referencia y queda en el historial), pero el
#: recurso "pago aprobado" no llegó a crearse: por eso 409 y no 201.
CODIGO_SEGUN_ESTADO = {
    Pago.Estado.APROBADO: status.HTTP_201_CREATED,
    Pago.Estado.PENDIENTE: status.HTTP_201_CREATED,
    Pago.Estado.RECHAZADO: status.HTTP_409_CONFLICT,
}


class VistaDePagos(APIView):
    """Base con lo que comparten todas las vistas de pago."""

    permission_classes = [IsAuthenticated]

    def cliente_autenticado(self):
        """`Cliente` asociado al usuario de la petición.

        Raises:
            RecursoNoEncontradoError: el usuario existe pero no tiene perfil
                de cliente, así que no puede comprar.
        """
        cliente = getattr(self.request.user, "cliente", None)
        if cliente is None:
            raise RecursoNoEncontradoError(
                "un perfil de cliente para el usuario autenticado"
            )
        return cliente


class MetodosPagoAPIView(VistaDePagos):
    """`GET /api/pagos/metodos/`: catálogo de métodos de pago.

    Acepta `?monto=` para que la interfaz solo ofrezca los métodos que
    sirven para ese valor: no tiene sentido mostrar "efectivo en
    corresponsal" para un carro de ochenta millones.
    """

    servicio = CatalogoMetodosPagoService

    def get(self, request):
        monto = request.query_params.get("monto")
        if monto is not None:
            if not monto.isdigit():
                return Response(
                    {"error": "El parámetro 'monto' debe ser un entero en pesos."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            monto = int(monto)

        metodos = self.servicio().listar(monto)
        datos = EspecificacionMetodoPagoSerializer(metodos, many=True).data
        return Response({"metodos": datos}, status=status.HTTP_200_OK)


class PagosAPIView(VistaDePagos):
    """`POST /api/pagos/` registra un pago; `GET` devuelve el historial.

    Códigos de la creación:

    * **201** el pago quedó aprobado o pendiente de confirmación.
    * **400** los datos no cumplen las reglas del método de pago.
    * **404** el carro o el repuesto no existe.
    * **409** el artículo ya estaba vendido, la referencia ya se usó, o el
      emisor rechazó la transacción.
    * **503** la pasarela no respondió.
    """

    servicio = ProcesarPagoService
    servicio_consulta = ConsultarPagoService

    def get(self, request):
        try:
            cliente = self.cliente_autenticado()
        except ErrorDeDominio as error:
            return respuesta_de_error(error)

        pagos = self.servicio_consulta().listar(cliente)
        return Response(
            {"pagos": PagoSerializer(pagos, many=True).data},
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        entrada = CrearPagoSerializer(data=request.data)
        if not entrada.is_valid():
            return Response(
                {"error": "Datos con formato inválido.", "detalles": entrada.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            cliente = self.cliente_autenticado()
            pago = self.servicio().procesar(cliente, entrada.validated_data)
        except ErrorDeDominio as error:
            return respuesta_de_error(error)

        return Response(
            PagoSerializer(pago).data,
            status=CODIGO_SEGUN_ESTADO.get(pago.estado, status.HTTP_201_CREATED),
        )


class DetallePagoAPIView(VistaDePagos):
    """`GET /api/pagos/<referencia>/`: estado de un pago propio.

    Devuelve 404 tanto si la referencia no existe como si es de otro
    cliente: responder distinto permitiría averiguar qué referencias son
    válidas probando una por una.
    """

    servicio = ConsultarPagoService

    def get(self, request, referencia):
        try:
            pago = self.servicio().obtener(referencia, self.cliente_autenticado())
        except ErrorDeDominio as error:
            return respuesta_de_error(error)

        return Response(PagoSerializer(pago).data, status=status.HTTP_200_OK)


class FacturaPagoAPIView(VistaDePagos):
    """`GET /api/pagos/<referencia>/factura/`: factura de un pago propio.

    * **200** el pago está aprobado y se devuelve la factura.
    * **404** no existe un pago así para el cliente.
    * **409** el pago existe pero no está aprobado, así que no es facturable.
    """

    servicio = FacturaService

    def get(self, request, referencia):
        try:
            factura = self.servicio().generar(referencia, self.cliente_autenticado())
        except ErrorDeDominio as error:
            return respuesta_de_error(error)

        return Response(FacturaSerializer(factura).data, status=status.HTTP_200_OK)


class ConfirmacionPagoAPIView(VistaDePagos):
    """`POST /api/pagos/<referencia>/confirmar/`: resuelve un pago pendiente.

    PSE y efectivo no confirman en el momento. Esta operación le pregunta a
    la pasarela en qué terminó la transacción.

    * **200** el pago se actualizó (puede quedar aprobado, rechazado o
      seguir pendiente si el banco todavía no responde).
    * **404** no existe un pago con esa referencia para el cliente.
    * **409** el pago ya estaba resuelto: confirmar dos veces no es válido.
    * **503** la pasarela no respondió.
    """

    servicio = ConfirmarPagoService

    def post(self, request, referencia):
        try:
            pago = self.servicio().confirmar(referencia, self.cliente_autenticado())
        except ErrorDeDominio as error:
            return respuesta_de_error(error)

        return Response(PagoSerializer(pago).data, status=status.HTTP_200_OK)
