"""Login y CRUD administrativo (DRF).

Antes vivía en `marketplace/api_views.py`, como una segunda API paralela a
la de pagos. Se mueve aquí para que exista un solo paquete `api/` con toda
la presentación DRF del proyecto, en vez de dos estructuras que hacen lo
mismo en lugares distintos.
"""

from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from ..domain.exceptions import CredencialesInvalidasError
from ..models import Carro, Cliente, Vendedor
from ..services import AutenticacionService
from .errores import respuesta_de_error
from .serializers_cuentas import (
    CarroSerializer,
    ClienteSerializer,
    LoginSerializer,
    VendedorSerializer,
)


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


# ---------------------------------------------------------------------
# CRUD administrativo — solo usuarios staff (rol Administrador)
# ---------------------------------------------------------------------


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
