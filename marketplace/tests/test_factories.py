"""Pruebas de las Factories.

Evidencian el criterio de la rúbrica: el comportamiento cambia con variables
de entorno, sin tocar el código que consume la dependencia.
"""

import os
from unittest import mock

from django.test import SimpleTestCase

from ..infra.factories import NotificadorFactory, ValidadorDocumentalFactory
from ..infra.notificadores import NotificadorConsola, NotificadorEmail
from ..infra.validadores import ValidadorDocumentalMock, ValidadorDocumentalRunt


class ValidadorDocumentalFactoryTest(SimpleTestCase):
    @mock.patch.dict(os.environ, {"VALIDADOR_DOCUMENTAL": "MOCK"})
    def test_entorno_mock_devuelve_validador_mock(self):
        self.assertIsInstance(ValidadorDocumentalFactory.crear(), ValidadorDocumentalMock)

    @mock.patch.dict(os.environ, {"VALIDADOR_DOCUMENTAL": "REAL"})
    def test_entorno_real_devuelve_validador_runt(self):
        self.assertIsInstance(ValidadorDocumentalFactory.crear(), ValidadorDocumentalRunt)

    @mock.patch.dict(os.environ, {"VALIDADOR_DOCUMENTAL": "real"})
    def test_el_valor_de_entorno_no_distingue_mayusculas(self):
        self.assertIsInstance(ValidadorDocumentalFactory.crear(), ValidadorDocumentalRunt)

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_sin_variable_usa_mock_por_defecto(self):
        self.assertIsInstance(ValidadorDocumentalFactory.crear(), ValidadorDocumentalMock)

    @mock.patch.dict(os.environ, {"VALIDADOR_DOCUMENTAL": "SARASA"})
    def test_valor_desconocido_falla_con_mensaje_claro(self):
        with self.assertRaises(ValueError) as capturado:
            ValidadorDocumentalFactory.crear()

        self.assertIn("no es válido", str(capturado.exception))


class NotificadorFactoryTest(SimpleTestCase):
    @mock.patch.dict(os.environ, {"NOTIFICADOR": "MOCK"})
    def test_entorno_mock_devuelve_notificador_consola(self):
        self.assertIsInstance(NotificadorFactory.crear(), NotificadorConsola)

    @mock.patch.dict(os.environ, {"NOTIFICADOR": "REAL"})
    def test_entorno_real_devuelve_notificador_email(self):
        self.assertIsInstance(NotificadorFactory.crear(), NotificadorEmail)

    def test_el_tipo_explicito_gana_sobre_el_entorno(self):
        with mock.patch.dict(os.environ, {"NOTIFICADOR": "REAL"}):
            self.assertIsInstance(NotificadorFactory.crear("MOCK"), NotificadorConsola)
