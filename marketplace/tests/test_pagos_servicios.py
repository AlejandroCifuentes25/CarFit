"""Pruebas del Service Layer de pagos.

Las pasarelas y el notificador se inyectan por constructor: ninguna prueba
sale a internet ni manda correos. Poder sustituirlos sin tocar el servicio
es justamente lo que se quiere demostrar de la Inversión de Dependencias.
"""

from django.test import TestCase

from ..domain.exceptions import (
    ArticuloNoDisponibleError,
    PagoDuplicadoError,
    PagoInvalidoError,
    PasarelaNoDisponibleError,
    RecursoNoEncontradoError,
    TransicionPagoInvalidaError,
)
from ..domain.ports import NotificadorPagos, PasarelaPago, ResultadoPago
from ..models import Pago, TransaccionPago
from ..services import (
    CatalogoMetodosPagoService,
    ConfirmarPagoService,
    ConsultarPagoService,
    ProcesarPagoService,
)
from .test_pagos_dominio import (
    TOKEN_DE_PRUEBA,
    crear_carro,
    crear_cliente,
    crear_repuesto,
    crear_vendedor,
)


class PasarelaEspia(PasarelaPago):
    """Devuelve lo que se le configure y recuerda con qué la llamaron."""

    nombre = "ESPIA"

    def __init__(self, resultado=None, resultado_consulta=None, falla=None):
        self._resultado = resultado or ResultadoPago.aprobado(
            referencia_pasarela="tx_1", codigo_autorizacion="AUT-1"
        )
        self._resultado_consulta = resultado_consulta or ResultadoPago.aprobado(
            referencia_pasarela="tx_1", codigo_autorizacion="AUT-2"
        )
        self._falla = falla
        self.solicitudes = []
        self.consultas = []

    def procesar(self, solicitud):
        self.solicitudes.append(solicitud)
        if self._falla:
            raise self._falla
        return self._resultado

    def consultar(self, referencia):
        self.consultas.append(referencia)
        if self._falla:
            raise self._falla
        return self._resultado_consulta


class FactoryDePasarelaFalsa:
    """Sustituye a `PasarelaPagoFactory` devolviendo siempre el mismo doble."""

    def __init__(self, pasarela):
        self.pasarela = pasarela
        self.metodos_pedidos = []

    def crear(self, metodo, modo=None):
        self.metodos_pedidos.append(metodo)
        return self.pasarela


class NotificadorPagosEspia(NotificadorPagos):
    def __init__(self):
        self.notificados = []

    def notificar_resultado(self, pago):
        self.notificados.append((pago.referencia, pago.estado))


class BaseDePagosTest(TestCase):
    """Montaje común: un cliente, un vendedor y un carro publicado."""

    def setUp(self):
        self.cliente = crear_cliente()
        self.vendedor = crear_vendedor()
        self.carro = crear_carro(self.vendedor, precio=10_000_000)
        self.pasarela = PasarelaEspia()
        self.notificador = NotificadorPagosEspia()
        self.factory = FactoryDePasarelaFalsa(self.pasarela)

    def _servicio(self, pasarela=None):
        factory = FactoryDePasarelaFalsa(pasarela) if pasarela else self.factory
        return ProcesarPagoService(
            pasarela_factory=factory, notificador=self.notificador
        )

    def _datos(self, **cambios):
        datos = {
            "metodo_pago": Pago.Metodo.TARJETA_CREDITO,
            "carro": self.carro.pk,
            "cuotas": 1,
            **TOKEN_DE_PRUEBA,
        }
        datos.update(cambios)
        return datos


class ProcesarPagoServiceTest(BaseDePagosTest):
    def test_registra_el_pago_aprobado(self):
        pago = self._servicio().procesar(self.cliente, self._datos())

        self.assertIsNotNone(pago.pk)
        self.assertEqual(pago.estado, Pago.Estado.APROBADO)
        self.assertEqual(pago.codigo_autorizacion, "AUT-1")
        self.assertEqual(Pago.objects.count(), 1)

    def test_cobra_el_total_con_comision_incluida(self):
        pago = self._servicio().procesar(self.cliente, self._datos())

        self.assertEqual(pago.precio, 10_000_000)
        self.assertEqual(pago.comision, 290_900)
        self.assertEqual(self.pasarela.solicitudes[0].monto, pago.total)

    def test_le_pide_a_la_factory_la_pasarela_del_metodo_elegido(self):
        self._servicio().procesar(
            self.cliente, self._datos(metodo_pago=Pago.Metodo.TARJETA_CREDITO)
        )

        self.assertEqual(self.factory.metodos_pedidos, [Pago.Metodo.TARJETA_CREDITO])

    def test_los_datos_sensibles_van_a_la_pasarela_pero_no_a_la_base_de_datos(self):
        pago = self._servicio().procesar(self.cliente, self._datos())

        self.assertEqual(
            self.pasarela.solicitudes[0].datos_metodo, {"token_tarjeta": "tok_prueba_123"}
        )
        guardado = Pago.objects.get(pk=pago.pk)
        self.assertNotIn("tok_prueba_123", str(guardado.__dict__))

    def test_deja_bitacora_de_la_transaccion(self):
        pago = self._servicio().procesar(self.cliente, self._datos())

        transaccion = TransaccionPago.objects.get(pago=pago)
        self.assertEqual(transaccion.operacion, TransaccionPago.Operacion.PROCESAR)
        self.assertEqual(transaccion.estado_resultante, Pago.Estado.APROBADO)
        self.assertEqual(transaccion.pasarela, "ESPIA")

    def test_notifica_al_cliente(self):
        pago = self._servicio().procesar(self.cliente, self._datos())

        self.assertEqual(
            self.notificador.notificados, [(pago.referencia, Pago.Estado.APROBADO)]
        )

    def test_un_rechazo_del_emisor_se_registra_y_no_revienta(self):
        pasarela = PasarelaEspia(
            resultado=ResultadoPago.rechazado("Fondos insuficientes.")
        )

        pago = self._servicio(pasarela).procesar(self.cliente, self._datos())

        self.assertEqual(pago.estado, Pago.Estado.RECHAZADO)
        self.assertEqual(pago.mensaje, "Fondos insuficientes.")
        self.assertEqual(Pago.objects.count(), 1)

    def test_un_metodo_diferido_queda_pendiente(self):
        pasarela = PasarelaEspia(resultado=ResultadoPago.pendiente("tx_2"))
        datos = self._datos(
            metodo_pago=Pago.Metodo.PSE,
            banco="1022",
            tipo_persona="NATURAL",
            documento_pagador="1017",
            token_tarjeta="",
        )

        pago = self._servicio(pasarela).procesar(self.cliente, datos)

        self.assertEqual(pago.estado, Pago.Estado.PENDIENTE)

    def test_permite_pagar_un_repuesto(self):
        repuesto = crear_repuesto(self.vendedor, precio=350_000)

        pago = self._servicio().procesar(
            self.cliente, self._datos(carro=None, repuesto=repuesto.pk)
        )

        self.assertEqual(pago.repuesto, repuesto)

    # ------------------------------------------------------------------
    # Caminos de error
    # ------------------------------------------------------------------

    def test_falla_si_el_articulo_no_existe(self):
        with self.assertRaises(RecursoNoEncontradoError):
            self._servicio().procesar(self.cliente, self._datos(carro=9_999))

        self.assertEqual(Pago.objects.count(), 0)

    def test_falla_si_no_se_indica_articulo(self):
        with self.assertRaises(PagoInvalidoError):
            self._servicio().procesar(self.cliente, self._datos(carro=None))

    def test_no_se_puede_comprar_dos_veces_el_mismo_carro(self):
        self._servicio().procesar(self.cliente, self._datos())
        otro_cliente = crear_cliente(usuario="andrea", nombre="Andrea Ruiz")

        with self.assertRaises(ArticuloNoDisponibleError):
            self._servicio().procesar(otro_cliente, self._datos())

        self.assertEqual(Pago.objects.count(), 1)

    def test_un_pago_pendiente_tambien_bloquea_el_articulo(self):
        pasarela = PasarelaEspia(resultado=ResultadoPago.pendiente("tx_2"))
        self._servicio(pasarela).procesar(self.cliente, self._datos())

        with self.assertRaises(ArticuloNoDisponibleError):
            self._servicio().procesar(self.cliente, self._datos())

    def test_la_misma_referencia_no_cobra_dos_veces(self):
        datos = self._datos(referencia="CF-IDEMPOTENTE")
        self._servicio().procesar(self.cliente, datos)

        otro_carro = crear_carro(self.vendedor, precio=9_000_000, placa="XYZ98A")

        with self.assertRaises(PagoDuplicadoError):
            self._servicio().procesar(self.cliente, {**datos, "carro": otro_carro.pk})

        self.assertEqual(Pago.objects.count(), 1)

    def test_datos_invalidos_no_llegan_a_la_pasarela(self):
        with self.assertRaises(PagoInvalidoError):
            self._servicio().procesar(self.cliente, self._datos(token_tarjeta=""))

        self.assertEqual(self.pasarela.solicitudes, [])
        self.assertEqual(Pago.objects.count(), 0)

    def test_si_la_pasarela_falla_no_queda_un_pago_a_medias(self):
        pasarela = PasarelaEspia(
            falla=PasarelaNoDisponibleError("ESPIA", "tiempo de espera agotado.")
        )

        with self.assertRaises(PasarelaNoDisponibleError):
            self._servicio(pasarela).procesar(self.cliente, self._datos())

        self.assertEqual(Pago.objects.count(), 0)
        self.assertEqual(self.notificador.notificados, [])


class ConsultarPagoServiceTest(BaseDePagosTest):
    def setUp(self):
        super().setUp()
        self.pago = self._servicio().procesar(self.cliente, self._datos())
        self.servicio = ConsultarPagoService()

    def test_devuelve_el_pago_por_referencia(self):
        encontrado = self.servicio.obtener(self.pago.referencia)

        self.assertEqual(encontrado.pk, self.pago.pk)

    def test_no_deja_ver_el_pago_de_otro_cliente(self):
        intruso = crear_cliente(usuario="intruso", nombre="Otro")

        with self.assertRaises(RecursoNoEncontradoError):
            self.servicio.obtener(self.pago.referencia, intruso)

    def test_lista_solo_los_pagos_del_cliente(self):
        intruso = crear_cliente(usuario="intruso", nombre="Otro")

        self.assertEqual(self.servicio.listar(self.cliente).count(), 1)
        self.assertEqual(self.servicio.listar(intruso).count(), 0)

    def test_referencia_inexistente(self):
        with self.assertRaises(RecursoNoEncontradoError):
            self.servicio.obtener("CF-NO-EXISTE")


class ConfirmarPagoServiceTest(BaseDePagosTest):
    def setUp(self):
        super().setUp()
        self.pasarela = PasarelaEspia(resultado=ResultadoPago.pendiente("tx_2"))
        self.factory = FactoryDePasarelaFalsa(self.pasarela)
        self.pago = self._servicio().procesar(self.cliente, self._datos())
        self.servicio = ConfirmarPagoService(
            pasarela_factory=self.factory, notificador=self.notificador
        )

    def test_confirma_un_pago_pendiente(self):
        pago = self.servicio.confirmar(self.pago.referencia, self.cliente)

        self.assertEqual(pago.estado, Pago.Estado.APROBADO)
        self.assertEqual(pago.codigo_autorizacion, "AUT-2")

    def test_le_pregunta_a_la_pasarela_por_su_propia_referencia(self):
        self.servicio.confirmar(self.pago.referencia, self.cliente)

        self.assertEqual(self.pasarela.consultas, ["tx_2"])

    def test_deja_bitacora_de_la_confirmacion(self):
        self.servicio.confirmar(self.pago.referencia, self.cliente)

        operaciones = list(
            TransaccionPago.objects.filter(pago=self.pago).values_list(
                "operacion", flat=True
            )
        )
        self.assertEqual(
            operaciones,
            [
                TransaccionPago.Operacion.PROCESAR,
                TransaccionPago.Operacion.CONFIRMAR,
            ],
        )

    def test_avisa_al_cliente_solo_cuando_el_estado_cambia(self):
        self.notificador.notificados.clear()

        self.servicio.confirmar(self.pago.referencia, self.cliente)

        self.assertEqual(len(self.notificador.notificados), 1)

    def test_no_avisa_si_el_banco_sigue_sin_responder(self):
        pasarela = PasarelaEspia(
            resultado_consulta=ResultadoPago.pendiente("tx_2", "Aún sin respuesta.")
        )
        servicio = ConfirmarPagoService(
            pasarela_factory=FactoryDePasarelaFalsa(pasarela),
            notificador=self.notificador,
        )
        self.notificador.notificados.clear()

        pago = servicio.confirmar(self.pago.referencia, self.cliente)

        self.assertEqual(pago.estado, Pago.Estado.PENDIENTE)
        self.assertEqual(self.notificador.notificados, [])

    def test_no_se_confirma_dos_veces(self):
        self.servicio.confirmar(self.pago.referencia, self.cliente)

        with self.assertRaises(TransicionPagoInvalidaError):
            self.servicio.confirmar(self.pago.referencia, self.cliente)

    def test_no_se_confirma_el_pago_de_otro_cliente(self):
        intruso = crear_cliente(usuario="intruso", nombre="Otro")

        with self.assertRaises(RecursoNoEncontradoError):
            self.servicio.confirmar(self.pago.referencia, intruso)


class CatalogoMetodosPagoServiceTest(TestCase):
    def test_lista_el_catalogo_completo(self):
        metodos = CatalogoMetodosPagoService().listar()

        self.assertEqual(len(metodos), len(Pago.Metodo.values))

    def test_filtra_por_monto(self):
        codigos = {m.codigo for m in CatalogoMetodosPagoService().listar(85_000_000)}

        self.assertNotIn(Pago.Metodo.EFECTIVO, codigos)
