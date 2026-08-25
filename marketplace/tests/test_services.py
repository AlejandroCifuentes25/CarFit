"""Pruebas del Service Layer.

Se inyectan dobles por constructor: ninguna prueba envía correos ni consulta
el RUNT. Esa posibilidad es exactamente el beneficio de la Inversión de
Dependencias que exige el taller.
"""

from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from ..domain.exceptions import ArticuloInvalidoError, DocumentacionInvalidaError, ErrorDeDominio
from ..domain.ports import Notificador, ResultadoValidacion, ValidadorDocumental
from ..infra.validadores import ValidadorDocumentalRunt
from ..models import Carro, CarritoCompra, DocumentoCarro, Inventario, Repuesto, Vendedor
from ..services import ArticuloCarrito, CarritoComprasService, PublicacionArticuloService


class ValidadorEspia(ValidadorDocumental):
    """Aprueba o rechaza según se configure, y recuerda cómo lo llamaron."""

    def __init__(self, resultado=None):
        self._resultado = resultado or ResultadoValidacion.ok()
        self.llamadas = []

    def validar(self, placa, documentos):
        self.llamadas.append((placa, list(documentos)))
        return self._resultado


class NotificadorEspia(Notificador):
    def __init__(self):
        self.notificados = []

    def notificar_publicacion(self, articulo):
        self.notificados.append(articulo)


DATOS_VALIDOS = {
    "placa": "ABC123",
    "marca": "Mazda",
    "modelo": "CX-30",
    "color": "Rojo",
    "estado": "USADO",
    "kilometraje": 15_000,
    "precio": 85_000_000,
    "descripcion": "Único dueño, full equipo.",
    "soat_expedicion": date(2026, 1, 10),
    "soat_vencimiento": date(2027, 1, 10),
    "soat_archivo": None,
    "tecnomecanica_expedicion": date(2026, 2, 1),
    "tecnomecanica_vencimiento": date(2027, 2, 1),
    "tecnomecanica_archivo": None,
}


class PublicacionArticuloServiceTest(TestCase):
    def setUp(self):
        usuario = User.objects.create_user("alejandro", password="clave-de-prueba")
        self.vendedor = Vendedor.objects.create(
            usuario=usuario,
            nombre="Alejandro Cifuentes",
            correo="alejandro@carfit.co",
            direccion="Cra 43A #1-50",
            numero_tel="3001234567",
        )
        self.validador = ValidadorEspia()
        self.notificador = NotificadorEspia()
        self.service = PublicacionArticuloService(
            validador=self.validador, notificador=self.notificador
        )

    def test_publica_el_carro_y_lo_persiste(self):
        carro = self.service.crear_articulo(self.vendedor, DATOS_VALIDOS)

        self.assertIsNotNone(carro.pk)
        self.assertEqual(Carro.objects.count(), 1)
        self.assertEqual(carro.vendedor, self.vendedor)

    def test_persiste_los_dos_documentos_obligatorios(self):
        carro = self.service.crear_articulo(self.vendedor, DATOS_VALIDOS)

        tipos = set(carro.documentos.values_list("tipo_documento", flat=True))
        self.assertEqual(tipos, {"SOAT", "TECNOMECANICA"})

    def test_incrementa_el_inventario_del_vendedor(self):
        self.service.crear_articulo(self.vendedor, DATOS_VALIDOS)
        self.service.crear_articulo(self.vendedor, {**DATOS_VALIDOS, "placa": "XYZ98A"})

        inventario = Inventario.objects.get(vendedor=self.vendedor)
        self.assertEqual(inventario.cantidad_carro, 2)

    def test_notifica_al_vendedor(self):
        carro = self.service.crear_articulo(self.vendedor, DATOS_VALIDOS)

        self.assertEqual(self.notificador.notificados, [carro])

    def test_valida_la_documentacion_antes_de_guardar(self):
        self.service.crear_articulo(self.vendedor, DATOS_VALIDOS)

        placa, documentos = self.validador.llamadas[0]
        self.assertEqual(placa, "ABC123")
        self.assertEqual(len(documentos), 2)

    def test_documentacion_rechazada_aborta_la_publicacion(self):
        service = PublicacionArticuloService(
            validador=ValidadorEspia(ResultadoValidacion.rechazado("SOAT vencido.")),
            notificador=self.notificador,
        )

        with self.assertRaises(DocumentacionInvalidaError):
            service.crear_articulo(self.vendedor, DATOS_VALIDOS)

        self.assertEqual(Carro.objects.count(), 0)
        self.assertEqual(self.notificador.notificados, [])

    def test_carro_invalido_no_llega_a_la_validacion_documental(self):
        with self.assertRaises(ArticuloInvalidoError):
            self.service.crear_articulo(self.vendedor, {**DATOS_VALIDOS, "precio": 0})

        self.assertEqual(self.validador.llamadas, [])
        self.assertEqual(Carro.objects.count(), 0)

    def test_no_deja_datos_a_medias_si_falla_la_documentacion(self):
        service = PublicacionArticuloService(
            validador=ValidadorEspia(ResultadoValidacion.rechazado("Vencido.")),
            notificador=self.notificador,
        )

        with self.assertRaises(DocumentacionInvalidaError):
            service.crear_articulo(self.vendedor, DATOS_VALIDOS)

        self.assertEqual(DocumentoCarro.objects.count(), 0)
        self.assertEqual(Inventario.objects.count(), 0)


class ValidadorDocumentalRuntTest(TestCase):
    def _documento(self, vencimiento):
        return DocumentoCarro(
            tipo_documento=DocumentoCarro.Tipo.SOAT,
            fecha_expedicion=date(2025, 1, 1),
            fecha_vencimiento=vencimiento,
        )

    def test_aprueba_documentos_vigentes(self):
        validador = ValidadorDocumentalRunt(hoy=lambda: date(2026, 6, 1))

        resultado = validador.validar("ABC123", [self._documento(date(2027, 1, 1))])

        self.assertTrue(resultado.es_valido)

    def test_rechaza_documentos_vencidos(self):
        validador = ValidadorDocumentalRunt(hoy=lambda: date(2026, 6, 1))

        resultado = validador.validar("ABC123", [self._documento(date(2026, 1, 1))])

        self.assertFalse(resultado.es_valido)
        self.assertIn("vencido", resultado.motivos[0])


class CarritoComprasServiceTest(TestCase):
    def setUp(self):
        usuario = User.objects.create_user("maria", password="clave-de-prueba")
        self.vendedor = Vendedor.objects.create(
            usuario=usuario,
            nombre="María López",
            correo="maria@carfit.co",
            direccion="Cra 12 #34-56",
            numero_tel="3015557788",
        )
        self.service = CarritoComprasService()

    def test_agrega_un_carro_y_normaliza_sus_datos(self):
        carro = Carro.objects.create(
            vendedor=self.vendedor,
            placa="XYZ123",
            marca="Toyota",
            modelo="Corolla",
            estado=Carro.Estado.USADO,
            color="Blanco",
            kilometraje=45000,
            descripcion="",
            precio=70000000,
        )

        resultado = self.service.agregar_articulo(object(), "carro", carro.pk)

        self.assertIsInstance(resultado, ArticuloCarrito)
        self.assertEqual(resultado.accion, "agregado")
        self.assertEqual(resultado.titulo, "Toyota Corolla")
        self.assertEqual(resultado.detalle["placa"], "XYZ123")
        self.assertEqual(CarritoCompra.objects.count(), 1)
        self.assertEqual(Carro.objects.get(pk=carro.pk).carrito_compra_id, CarritoCompra.objects.first().id)
        self.assertEqual(CarritoCompra.objects.first().cantidad_producto, 1)

    def test_quita_un_repuesto_y_normaliza_sus_datos(self):
        repuesto = Repuesto.objects.create(
            vendedor=self.vendedor,
            tipo="Filtro de aceite",
            modelo_carro="Corolla",
            precio=120000,
            numero_serie="REP-001",
            estado=Repuesto.Estado.NUEVO,
        )

        self.service.agregar_articulo(object(), "repuesto", repuesto.pk)
        resultado = self.service.quitar_articulo(object(), "repuesto", repuesto.pk)

        self.assertIsInstance(resultado, ArticuloCarrito)
        self.assertEqual(resultado.accion, "quitado")
        self.assertEqual(resultado.titulo, "Filtro de aceite - Corolla")
        self.assertEqual(resultado.detalle["numero_serie"], "REP-001")
        self.assertIsNone(Repuesto.objects.get(pk=repuesto.pk).carrito_compra_id)
        self.assertEqual(CarritoCompra.objects.first().cantidad_producto, 0)

    def test_rechaza_tipo_de_articulo_no_soportado(self):
        with self.assertRaises(ErrorDeDominio):
            self.service.agregar_articulo(object(), "moto", 1)
