"""Capa de Presentación — API (Django REST Framework).

Convive con `views.py` (HTML): esta es la interfaz para el CRUD
administrativo y el inicio de sesión. Igual que la vista HTML de
`CrearArticuloView`, ninguna de estas clases contiene lógica de negocio:
el login delega en `AutenticacionService`; el CRUD delega la validación de
formato al Serializer y usa `generics` de DRF para la persistencia (no hay
invariante de negocio adicional que orquestar en estos flujos).
"""

from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .domain.exceptions import CredencialesInvalidasError
from .models import Carro, Cliente, Vendedor
from .serializers import (
    CarroSerializer,
    ClienteSerializer,
    LoginSerializer,
    VendedorSerializer,
)
from .services import AutenticacionService


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
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)

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

from .serializers import RepuestoSerializer

class PublicarRepuestoAPIView(APIView):
    """Expone el flujo de negocio de publicar un repuesto usando APIView."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if not hasattr(request.user, "vendedor"):
            return Response({"detail": "Se requiere perfil de Vendedor."}, status=status.HTTP_403_FORBIDDEN)
            
        serializer = RepuestoSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        from .services import PublicacionArticuloService
        from .domain.exceptions import ErrorDeDominio
        
        servicio = PublicacionArticuloService()
        try:
            repuesto = servicio.crear_repuesto(request.user.vendedor, serializer.validated_data)
        except ErrorDeDominio as error:
            return Response({"detail": str(error)}, status=status.HTTP_409_CONFLICT)
            
        serializer_salida = RepuestoSerializer(repuesto)
        return Response(serializer_salida.data, status=status.HTTP_201_CREATED)
