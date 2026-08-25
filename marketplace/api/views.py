"""Capa de Presentación de pagos (Django REST Framework).

Se usa `APIView` y no `ViewSet` para tener control explícito de cada método
HTTP y de cada código de estado, que es lo que se está evaluando.

Ninguna de estas vistas contiene reglas de negocio. Su trabajo completo es:

1. Validar el *formato* de la entrada con un serializer.
2. Llamar al servicio correspondiente.
3. Traducir el desenlace a un código HTTP.

Si alguna de estas clases empieza a calcular comisiones o a decidir si un
artículo está disponible, la lógica está en el lugar equivocado.
"""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..domain.exceptions import ErrorDeDominio, RecursoNoEncontradoError
from ..models import Pago
from ..services import (
    CatalogoMetodosPagoService,
    ConfirmarPagoService,
    ConsultarPagoService,
    FacturaService,
    ProcesarPagoService,
)
from .errores import respuesta_de_error
from .serializers import (
    CrearPagoSerializer,
    EspecificacionMetodoPagoSerializer,
    FacturaSerializer,
    PagoSerializer,
)

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
