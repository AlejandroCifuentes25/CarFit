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

from django.contrib.auth import authenticate, login
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import F

from .domain.builders import CarroBuilder
from .domain.exceptions import (
    CredencialesInvalidasError,
    DocumentacionInvalidaError,
    NombreDeUsuarioEnUsoError,
)
from .infra.factories import NotificadorFactory, ValidadorDocumentalFactory
from .models import Cliente, DocumentoCarro, Inventario, Vendedor


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


class AutenticacionService:
    """Orquesta el caso de uso "Iniciar sesión".

    Igual que `PublicacionArticuloService`, no conoce DRF ni `Response`:
    recibe el `request` (lo necesita `authenticate`/`login` de Django para
    asociar la sesión) y las credenciales ya validadas en *formato* por el
    Serializer, y devuelve el usuario autenticado o levanta un error de
    dominio. La vista es quien lo traduce a un código HTTP.
    """

    def iniciar_sesion(self, request, username, password):
        usuario = authenticate(request, username=username, password=password)
        if usuario is None:
            raise CredencialesInvalidasError()
        login(request, usuario)
        return usuario


class RegistroUsuarioService:
    """Orquesta el registro de una cuenta nueva (Cliente o Vendedor).

    Crea el `User` de Django y el registro de rol en una única transacción
    y, si todo sale bien, inicia sesión de una vez. Como el resto del
    Service Layer, no conoce `forms` ni `HttpResponse`: recibe datos ya
    validados en *formato* y levanta un error de dominio si el nombre de
    usuario ya existe.
    """

    ROLES = {"CLIENTE": Cliente, "VENDEDOR": Vendedor}

    def registrar(self, request, rol, datos):
        username = datos["username"]
        if User.objects.filter(username=username).exists():
            raise NombreDeUsuarioEnUsoError(username)

        modelo_rol = self.ROLES[rol]

        with transaction.atomic():
            usuario = User.objects.create_user(
                username=username, password=datos["password"]
            )
            modelo_rol.objects.create(
                usuario=usuario,
                nombre=datos["nombre"],
                correo=datos["correo"],
                direccion=datos["direccion"],
                numero_tel=datos["numero_tel"],
            )

        login(request, usuario)
        return usuario
