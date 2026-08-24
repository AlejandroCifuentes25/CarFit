"""Pruebas de la infraestructura de pagos: pasarelas y su Factory.

Ninguna de estas pruebas sale a internet. La pasarela real se ejercita por
su traductor de estados y por su manejo de fallas, que es donde de verdad
puede equivocarse.
"""

import os
from unittest import mock

from django.test import SimpleTestCase

from ..domain.exceptions import (
    MetodoPagoNoSoportadoError,
    PasarelaNoDisponibleError,
)
from ..domain.ports import SolicitudPago
from ..infra.factories import NotificadorPagosFactory, PasarelaPagoFactory
from ..infra.notificadores import NotificadorPagoConsola, NotificadorPagoEmail
from ..infra.pasarelas import (
    PasarelaAgregador,
    PasarelaCorresponsalEfectivo,
    PasarelaSimulada,
)
from ..models import Pago


def solicitud(metodo=Pago.Metodo.TARJETA_CREDITO, datos=None, referencia="CF-001"):
    return SolicitudPago(
        referencia=referencia,
        monto=1_000_000,
        moneda="COP",
        metodo=metodo,
        datos_metodo=datos if datos is not None else {"token_tarjeta": "tok_123"},
    )


class PasarelaSimuladaTest(SimpleTestCase):
    def setUp(self):
        self.pasarela = PasarelaSimulada()

    def test_aprueba_una_tarjeta_normal(self):
        resultado = self.pasarela.procesar(solicitud())

        self.assertTrue(resultado.fue_aprobado)
        self.assertTrue(resultado.codigo_autorizacion)

    def test_rechaza_cuando_los_datos_piden_rechazo(self):
        resultado = self.pasarela.procesar(
            solicitud(datos={"token_tarjeta": "tok_RECHAZAR"})
        )

        self.assertTrue(resultado.fue_rechazado)
        self.assertFalse(resultado.fue_aprobado)

    def test_deja_pendiente_los_metodos_que_no_confirman_en_el_momento(self):
        resultado = self.pasarela.procesar(
            solicitud(metodo=Pago.Metodo.PSE, datos={"banco": "1022"})
        )

        self.assertTrue(resultado.quedo_pendiente)

    def test_es_determinista(self):
        """La misma referencia produce siempre el mismo código."""
        primero = self.pasarela.procesar(solicitud())
        segundo = self.pasarela.procesar(solicitud())

        self.assertEqual(primero.codigo_autorizacion, segundo.codigo_autorizacion)

    def test_la_consulta_confirma_la_transaccion(self):
        resultado = self.pasarela.consultar("CF-001")

        self.assertTrue(resultado.fue_aprobado)


class PasarelaAgregadorTest(SimpleTestCase):
    def setUp(self):
        self.pasarela = PasarelaAgregador(
            url_base="https://sandbox.agregador.co/v1", llave="llave"
        )

    def test_traduce_estado_aprobado(self):
        resultado = self.pasarela._interpretar(
            {"data": {"id": "tx_1", "status": "APPROVED", "authorization_code": "A1"}}
        )

        self.assertTrue(resultado.fue_aprobado)
        self.assertEqual(resultado.referencia_pasarela, "tx_1")
        self.assertEqual(resultado.codigo_autorizacion, "A1")

    def test_traduce_estado_pendiente(self):
        resultado = self.pasarela._interpretar({"data": {"status": "PENDING"}})

        self.assertTrue(resultado.quedo_pendiente)

    def test_traduce_estado_rechazado(self):
        resultado = self.pasarela._interpretar(
            {"data": {"status": "DECLINED", "status_message": "Fondos insuficientes"}}
        )

        self.assertTrue(resultado.fue_rechazado)
        self.assertEqual(resultado.mensaje, "Fondos insuficientes")

    def test_un_estado_desconocido_no_se_da_por_bueno(self):
        with self.assertRaises(PasarelaNoDisponibleError):
            self.pasarela._interpretar({"data": {"status": "LO_QUE_SEA"}})

    def test_sin_url_configurada_falla_antes_de_intentar_la_red(self):
        pasarela = PasarelaAgregador(url_base="", llave="")

        with self.assertRaises(PasarelaNoDisponibleError) as capturado:
            pasarela.procesar(solicitud())

        self.assertIn("PASARELA_URL", str(capturado.exception))


class PasarelaCorresponsalEfectivoTest(SimpleTestCase):
    def test_genera_un_codigo_de_recaudo_y_queda_pendiente(self):
        resultado = PasarelaCorresponsalEfectivo().procesar(
            solicitud(metodo=Pago.Metodo.EFECTIVO, datos={"documento_pagador": "1017"})
        )

        self.assertTrue(resultado.quedo_pendiente)
        self.assertEqual(len(resultado.referencia_pasarela), 10)

    def test_no_se_aprueba_sola_al_consultar(self):
        """Hasta que el corresponsal no reporte, el pago sigue pendiente."""
        resultado = PasarelaCorresponsalEfectivo().consultar("0123456789")

        self.assertTrue(resultado.quedo_pendiente)


class PasarelaPagoFactoryTest(SimpleTestCase):
    @mock.patch.dict(os.environ, {"PASARELA_PAGO": "MOCK"})
    def test_en_modo_mock_toda_la_operacion_es_simulada(self):
        for metodo in Pago.Metodo.values:
            with self.subTest(metodo=metodo):
                self.assertIsInstance(
                    PasarelaPagoFactory.crear(metodo), PasarelaSimulada
                )

    @mock.patch.dict(os.environ, {"PASARELA_PAGO": "REAL"})
    def test_en_modo_real_las_tarjetas_van_al_agregador(self):
        pasarela = PasarelaPagoFactory.crear(Pago.Metodo.TARJETA_CREDITO)

        self.assertIsInstance(pasarela, PasarelaAgregador)

    @mock.patch.dict(os.environ, {"PASARELA_PAGO": "REAL"})
    def test_en_modo_real_el_efectivo_va_al_corresponsal(self):
        pasarela = PasarelaPagoFactory.crear(Pago.Metodo.EFECTIVO)

        self.assertIsInstance(pasarela, PasarelaCorresponsalEfectivo)

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_sin_variable_de_entorno_usa_la_simulada(self):
        self.assertIsInstance(
            PasarelaPagoFactory.crear(Pago.Metodo.PSE), PasarelaSimulada
        )

    def test_el_modo_explicito_gana_sobre_el_entorno(self):
        with mock.patch.dict(os.environ, {"PASARELA_PAGO": "REAL"}):
            pasarela = PasarelaPagoFactory.crear(Pago.Metodo.PSE, modo="MOCK")

        self.assertIsInstance(pasarela, PasarelaSimulada)

    @mock.patch.dict(os.environ, {"PASARELA_PAGO": "PRODUCCION"})
    def test_modo_desconocido_falla_con_mensaje_claro(self):
        with self.assertRaises(ValueError) as capturado:
            PasarelaPagoFactory.crear(Pago.Metodo.PSE)

        self.assertIn("no es válido", str(capturado.exception))

    def test_metodo_desconocido_no_llega_a_crear_pasarela(self):
        with self.assertRaises(MetodoPagoNoSoportadoError):
            PasarelaPagoFactory.crear("TRUEQUE")


class NotificadorPagosFactoryTest(SimpleTestCase):
    @mock.patch.dict(os.environ, {"NOTIFICADOR_PAGOS": "MOCK"})
    def test_entorno_mock_notifica_por_consola(self):
        self.assertIsInstance(NotificadorPagosFactory.crear(), NotificadorPagoConsola)

    @mock.patch.dict(os.environ, {"NOTIFICADOR_PAGOS": "REAL"})
    def test_entorno_real_notifica_por_correo(self):
        self.assertIsInstance(NotificadorPagosFactory.crear(), NotificadorPagoEmail)
