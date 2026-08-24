"""Pruebas de la generación de factura: dominio, servicio y API.

Corresponde a `Pago.Generar_Factura()` del diagrama de clases del proyecto.
"""

import os
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from ..domain.exceptions import PagoNoFacturableError, RecursoNoEncontradoError
from ..domain.facturas import generar_factura
from ..models import Pago
from ..services import ConsultarPagoService, FacturaService, ProcesarPagoService
from .test_pagos_dominio import TOKEN_DE_PRUEBA, crear_carro, crear_cliente, crear_vendedor
from .test_pagos_servicios import FactoryDePasarelaFalsa, NotificadorPagosEspia, PasarelaEspia


class GenerarFacturaDominioTest(TestCase):
    def setUp(self):
        self.cliente = crear_cliente()
        self.vendedor = crear_vendedor()
        self.carro = crear_carro(self.vendedor, precio=10_000_000)

    def _procesar(self, pasarela=None):
        factory = FactoryDePasarelaFalsa(pasarela or PasarelaEspia())
        datos = {
            "metodo_pago": Pago.Metodo.TARJETA_CREDITO,
            "carro": self.carro.pk,
            **TOKEN_DE_PRUEBA,
        }
        return ProcesarPagoService(
            pasarela_factory=factory, notificador=NotificadorPagosEspia()
        ).procesar(self.cliente, datos)

    def test_genera_la_factura_de_un_pago_aprobado(self):
        pago = self._procesar()

        factura = generar_factura(pago)

        self.assertEqual(factura.referencia_pago, pago.referencia)
        self.assertEqual(factura.numero, f"FAC-{pago.referencia}")
        self.assertEqual(factura.subtotal, pago.precio)
        self.assertEqual(factura.comision, pago.comision)
        self.assertEqual(factura.total, pago.total)
        self.assertEqual(factura.cliente_nombre, self.cliente.nombre)
        self.assertEqual(factura.vendedor_nombre, self.vendedor.nombre)
        self.assertIn("Mazda", factura.articulo_descripcion)

    def test_no_factura_un_pago_pendiente(self):
        from ..domain.ports import ResultadoPago

        pago = self._procesar(PasarelaEspia(resultado=ResultadoPago.pendiente("tx")))

        with self.assertRaises(PagoNoFacturableError) as capturado:
            generar_factura(pago)

        self.assertIn("APROBADO", str(capturado.exception))

    def test_no_factura_un_pago_rechazado(self):
        from ..domain.ports import ResultadoPago

        pago = self._procesar(
            PasarelaEspia(resultado=ResultadoPago.rechazado("Fondos insuficientes."))
        )

        with self.assertRaises(PagoNoFacturableError):
            generar_factura(pago)


class FacturaServiceTest(TestCase):
    def setUp(self):
        self.cliente = crear_cliente()
        self.vendedor = crear_vendedor()
        self.carro = crear_carro(self.vendedor, precio=10_000_000)
        factory = FactoryDePasarelaFalsa(PasarelaEspia())
        self.pago = ProcesarPagoService(
            pasarela_factory=factory, notificador=NotificadorPagosEspia()
        ).procesar(
            self.cliente,
            {
                "metodo_pago": Pago.Metodo.TARJETA_CREDITO,
                "carro": self.carro.pk,
                **TOKEN_DE_PRUEBA,
            },
        )
        self.servicio = FacturaService()

    def test_genera_la_factura_de_un_pago_propio(self):
        factura = self.servicio.generar(self.pago.referencia, self.cliente)

        self.assertEqual(factura.referencia_pago, self.pago.referencia)

    def test_no_deja_facturar_el_pago_de_otro_cliente(self):
        intruso = crear_cliente(usuario="intruso", nombre="Otro")

        with self.assertRaises(RecursoNoEncontradoError):
            self.servicio.generar(self.pago.referencia, intruso)

    def test_referencia_inexistente(self):
        with self.assertRaises(RecursoNoEncontradoError):
            self.servicio.generar("CF-NO-EXISTE", self.cliente)


ENTORNO_SIMULADO = {"PASARELA_PAGO": "MOCK", "NOTIFICADOR_PAGOS": "MOCK"}


class FacturaPagoAPITest(APITestCase):
    def setUp(self):
        entorno = mock.patch.dict(os.environ, ENTORNO_SIMULADO)
        entorno.start()
        self.addCleanup(entorno.stop)

        self.cliente = crear_cliente()
        self.vendedor = crear_vendedor()
        self.carro = crear_carro(self.vendedor, precio=10_000_000)
        self.client.force_login(self.cliente.usuario)

        respuesta = self.client.post(
            reverse("api:pagos"),
            {
                "metodo_pago": Pago.Metodo.TARJETA_CREDITO,
                "carro": self.carro.pk,
                **TOKEN_DE_PRUEBA,
            },
            format="json",
        )
        self.referencia = respuesta.data["referencia"]

    def _url(self, referencia=None):
        return reverse("api:factura-pago", args=[referencia or self.referencia])

    def test_200_con_la_factura_de_un_pago_aprobado(self):
        respuesta = self.client.get(self._url())

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(respuesta.data["referencia_pago"], self.referencia)
        self.assertEqual(respuesta.data["total"], 10_290_900)

    def test_404_cuando_el_pago_no_existe(self):
        respuesta = self.client.get(self._url("CF-NO-EXISTE"))

        self.assertEqual(respuesta.status_code, status.HTTP_404_NOT_FOUND)

    def test_409_cuando_el_pago_no_esta_aprobado(self):
        pendiente = self.client.post(
            reverse("api:pagos"),
            {
                "metodo_pago": Pago.Metodo.PSE,
                "carro": crear_carro(self.vendedor, precio=6_000_000, placa="XYZ98A").pk,
                "banco": "1022",
                "tipo_persona": "NATURAL",
                "documento_pagador": "1017123456",
            },
            format="json",
        )

        respuesta = self.client.get(self._url(pendiente.data["referencia"]))

        self.assertEqual(respuesta.status_code, status.HTTP_409_CONFLICT)
