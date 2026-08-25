"""Pruebas de la API REST de pagos.

Verifican el contrato HTTP: qué código devuelve cada situación. La API corre
en modo MOCK, así que la pasarela es la simulada: determinista y sin red.

Que estas pruebas solo miren códigos y cuerpos de respuesta, y no reglas de
negocio, es la señal de que las vistas están delgadas: lo que se prueba del
negocio ya está probado en `test_pagos_dominio` y `test_pagos_servicios`.
"""

import os
from unittest import mock

from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from ..models import Pago
from .test_pagos_dominio import crear_carro, crear_cliente, crear_vendedor

ENTORNO_SIMULADO = {"PASARELA_PAGO": "MOCK", "NOTIFICADOR_PAGOS": "MOCK"}

DATOS_PSE = {
    "banco": "1022",
    "tipo_persona": "NATURAL",
    "documento_pagador": "1017123456",
}


class BaseAPIPagosTest(APITestCase):
    def setUp(self):
        # Se fija el entorno simulado para toda la prueba: así el resultado
        # no depende de las variables que tenga exportadas quien la corra.
        entorno = mock.patch.dict(os.environ, ENTORNO_SIMULADO)
        entorno.start()
        self.addCleanup(entorno.stop)

        self.cliente = crear_cliente()
        self.vendedor = crear_vendedor()
        self.carro = crear_carro(self.vendedor, precio=10_000_000)
        self.url_pagos = reverse("api:pagos")
        self.client.force_login(self.cliente.usuario)

    def _cuerpo(self, **cambios):
        datos = {
            "metodo_pago": Pago.Metodo.TARJETA_CREDITO,
            "carro": self.carro.pk,
            "token_tarjeta": "tok_prueba_123",
        }
        datos.update(cambios)
        return datos

    def _pagar(self, **cambios):
        return self.client.post(self.url_pagos, self._cuerpo(**cambios), format="json")


class CrearPagoAPITest(BaseAPIPagosTest):
    def test_201_cuando_el_pago_queda_aprobado(self):
        respuesta = self._pagar()

        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        self.assertEqual(respuesta.data["estado"], Pago.Estado.APROBADO)
        self.assertEqual(respuesta.data["total"], 10_290_900)
        self.assertTrue(respuesta.data["referencia"])

    def test_201_cuando_el_metodo_queda_pendiente_de_confirmacion(self):
        respuesta = self._pagar(
            metodo_pago=Pago.Metodo.PSE, token_tarjeta="", **DATOS_PSE
        )

        self.assertEqual(respuesta.status_code, status.HTTP_201_CREATED)
        self.assertEqual(respuesta.data["estado"], Pago.Estado.PENDIENTE)

    def test_409_cuando_el_emisor_rechaza_la_transaccion(self):
        respuesta = self._pagar(token_tarjeta="tok_RECHAZAR")

        self.assertEqual(respuesta.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(respuesta.data["estado"], Pago.Estado.RECHAZADO)

    def test_400_cuando_el_metodo_no_existe(self):
        respuesta = self._pagar(metodo_pago="TRUEQUE")

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detalles", respuesta.data)

    def test_400_cuando_faltan_los_datos_del_metodo(self):
        respuesta = self._pagar(token_tarjeta="")

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("token_tarjeta", str(respuesta.data))

    def test_400_cuando_el_formato_de_la_entrada_es_invalido(self):
        respuesta = self._pagar(cuotas=0)

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_400_cuando_las_cuotas_superan_el_tope_del_metodo(self):
        respuesta = self._pagar(cuotas=48)

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("entre 1 y 36", str(respuesta.data))

    def test_404_cuando_el_carro_no_existe(self):
        respuesta = self._pagar(carro=9_999)

        self.assertEqual(respuesta.status_code, status.HTTP_404_NOT_FOUND)

    def test_409_cuando_el_articulo_ya_se_vendio(self):
        self._pagar()

        respuesta = self._pagar()

        self.assertEqual(respuesta.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(Pago.objects.count(), 1)

    def test_409_cuando_se_repite_la_referencia(self):
        otro_carro = crear_carro(self.vendedor, precio=9_000_000, placa="XYZ98A")
        self._pagar(referencia="CF-IDEMPOTENTE")

        respuesta = self._pagar(referencia="CF-IDEMPOTENTE", carro=otro_carro.pk)

        self.assertEqual(respuesta.status_code, status.HTTP_409_CONFLICT)

    def test_404_cuando_el_usuario_no_tiene_perfil_de_cliente(self):
        self.client.force_login(
            User.objects.create_user("sin_perfil", password="clave-de-prueba")
        )

        respuesta = self._pagar()

        self.assertEqual(respuesta.status_code, status.HTTP_404_NOT_FOUND)

    def test_la_api_esta_cerrada_a_los_anonimos(self):
        self.client.logout()

        respuesta = self._pagar()

        self.assertIn(
            respuesta.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_la_respuesta_nunca_devuelve_los_datos_de_la_tarjeta(self):
        respuesta = self._pagar()

        self.assertNotIn("tok_prueba_123", str(respuesta.data))


class ConsultarPagoAPITest(BaseAPIPagosTest):
    def setUp(self):
        super().setUp()
        self.referencia = self._pagar().data["referencia"]

    def _url_detalle(self, referencia=None):
        return reverse(
            "api:detalle-pago", args=[referencia or self.referencia]
        )

    def test_200_al_consultar_un_pago_propio(self):
        respuesta = self.client.get(self._url_detalle())

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(respuesta.data["referencia"], self.referencia)

    def test_404_cuando_la_referencia_no_existe(self):
        respuesta = self.client.get(self._url_detalle("CF-NO-EXISTE"))

        self.assertEqual(respuesta.status_code, status.HTTP_404_NOT_FOUND)

    def test_404_cuando_el_pago_es_de_otro_cliente(self):
        intruso = crear_cliente(usuario="intruso", nombre="Otro")
        self.client.force_login(intruso.usuario)

        respuesta = self.client.get(self._url_detalle())

        self.assertEqual(respuesta.status_code, status.HTTP_404_NOT_FOUND)

    def test_el_historial_solo_trae_los_pagos_del_cliente(self):
        respuesta = self.client.get(self.url_pagos)

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(len(respuesta.data["pagos"]), 1)


class ConfirmarPagoAPITest(BaseAPIPagosTest):
    def setUp(self):
        super().setUp()
        self.referencia = self._pagar(
            metodo_pago=Pago.Metodo.PSE, token_tarjeta="", **DATOS_PSE
        ).data["referencia"]
        self.url = reverse("api:confirmar-pago", args=[self.referencia])

    def test_200_al_confirmar_un_pago_pendiente(self):
        respuesta = self.client.post(self.url, {}, format="json")

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(respuesta.data["estado"], Pago.Estado.APROBADO)

    def test_409_al_confirmar_dos_veces(self):
        self.client.post(self.url, {}, format="json")

        respuesta = self.client.post(self.url, {}, format="json")

        self.assertEqual(respuesta.status_code, status.HTTP_409_CONFLICT)

    def test_404_cuando_la_referencia_no_existe(self):
        url = reverse("api:confirmar-pago", args=["CF-NO-EXISTE"])

        respuesta = self.client.post(url, {}, format="json")

        self.assertEqual(respuesta.status_code, status.HTTP_404_NOT_FOUND)


class MetodosPagoAPITest(BaseAPIPagosTest):
    def setUp(self):
        super().setUp()
        self.url = reverse("api:metodos-pago")

    def test_200_con_el_catalogo_completo(self):
        respuesta = self.client.get(self.url)

        self.assertEqual(respuesta.status_code, status.HTTP_200_OK)
        self.assertEqual(len(respuesta.data["metodos"]), len(Pago.Metodo.values))

    def test_filtra_por_monto(self):
        respuesta = self.client.get(self.url, {"monto": 85_000_000})

        codigos = {metodo["codigo"] for metodo in respuesta.data["metodos"]}
        self.assertNotIn(Pago.Metodo.EFECTIVO, codigos)

    def test_400_cuando_el_monto_no_es_un_numero(self):
        respuesta = self.client.get(self.url, {"monto": "mucho"})

        self.assertEqual(respuesta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_expone_los_datos_que_la_interfaz_necesita_para_el_formulario(self):
        respuesta = self.client.get(self.url)

        tarjeta = next(
            metodo
            for metodo in respuesta.data["metodos"]
            if metodo["codigo"] == Pago.Metodo.TARJETA_CREDITO
        )
        self.assertEqual(tarjeta["campos_requeridos"], ["token_tarjeta"])
        self.assertTrue(tarjeta["permite_cuotas"])
        self.assertEqual(tarjeta["cuotas_maximas"], 36)
