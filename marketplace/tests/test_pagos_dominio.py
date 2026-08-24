"""Pruebas del dominio de pagos: catálogo de métodos y `PagoBuilder`.

Todo lo que se verifica aquí es negocio puro (comisiones, límites, datos
obligatorios, cuotas), sin HTTP, sin pasarelas y sin serializers. Que estas
pruebas puedan escribirse así es la evidencia de que las reglas quedaron en
el dominio y no repartidas por la aplicación.
"""

from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from ..domain.builders import PagoBuilder
from ..domain.exceptions import MetodoPagoNoSoportadoError, PagoInvalidoError
from ..domain.metodos_pago import (
    CATALOGO_METODOS,
    metodos_disponibles,
    obtener_especificacion,
)
from ..models import Carro, Cliente, Pago, Repuesto, Vendedor

# ----------------------------------------------------------------------
# Ayudas compartidas por las demás pruebas de pagos
# ----------------------------------------------------------------------


def crear_cliente(usuario="julian", nombre="Julián Jiménez"):
    return Cliente.objects.create(
        usuario=User.objects.create_user(usuario, password="clave-de-prueba"),
        nombre=nombre,
        correo=f"{usuario}@carfit.co",
        direccion="Cra 43A #1-50",
        numero_tel="3001234567",
    )


def crear_vendedor(usuario="simon", nombre="Simón Mazo"):
    return Vendedor.objects.create(
        usuario=User.objects.create_user(usuario, password="clave-de-prueba"),
        nombre=nombre,
        correo=f"{usuario}@carfit.co",
        direccion="Calle 10 #43-20",
        numero_tel="3009876543",
    )


def crear_carro(vendedor, precio=85_000_000, placa="ABC123"):
    return Carro.objects.create(
        vendedor=vendedor,
        placa=placa,
        marca="Mazda",
        modelo="CX-30",
        estado=Carro.Estado.USADO,
        color="Rojo",
        kilometraje=15_000,
        precio=precio,
    )


def crear_repuesto(vendedor, precio=350_000, numero_serie="SER-001"):
    return Repuesto.objects.create(
        vendedor=vendedor,
        tipo="Alternador",
        modelo_carro="Mazda CX-30",
        precio=precio,
        numero_serie=numero_serie,
        estado=Repuesto.Estado.NUEVO,
    )


TOKEN_DE_PRUEBA = {"token_tarjeta": "tok_prueba_123"}


# ----------------------------------------------------------------------
# Catálogo de métodos de pago
# ----------------------------------------------------------------------


class CatalogoMetodosPagoTest(TestCase):
    def test_todo_metodo_del_modelo_tiene_especificacion(self):
        """El catálogo y las opciones del modelo no pueden desincronizarse."""
        self.assertEqual(set(CATALOGO_METODOS), set(Pago.Metodo.values))

    def test_comision_de_tarjeta_suma_porcentaje_y_valor_fijo(self):
        tarjeta = obtener_especificacion(Pago.Metodo.TARJETA_CREDITO)

        # 2,9% de $1.000.000 = $29.000, más $900 fijos.
        self.assertEqual(tarjeta.calcular_comision(1_000_000), 29_900)
        self.assertEqual(tarjeta.calcular_total(1_000_000), 1_029_900)

    def test_comision_de_pse_es_un_valor_fijo(self):
        pse = obtener_especificacion(Pago.Metodo.PSE)

        self.assertEqual(pse.comision_porcentual, Decimal("0.0000"))
        self.assertEqual(pse.calcular_comision(50_000_000), 2_500)

    def test_la_comision_siempre_es_un_entero_de_pesos(self):
        billetera = obtener_especificacion(Pago.Metodo.BILLETERA_DIGITAL)

        comision = billetera.calcular_comision(333_333)

        self.assertIsInstance(comision, int)
        self.assertEqual(comision, 5_833)  # 1,75% de 333.333 = 5.833,3275

    def test_el_codigo_no_distingue_mayusculas(self):
        self.assertEqual(obtener_especificacion("pse").codigo, Pago.Metodo.PSE)

    def test_metodo_desconocido_falla_con_mensaje_util(self):
        with self.assertRaises(MetodoPagoNoSoportadoError) as capturado:
            obtener_especificacion("CRIPTOMONEDA")

        self.assertIn("no está soportado", str(capturado.exception))
        self.assertIn(Pago.Metodo.PSE, capturado.exception.soportados)

    def test_filtra_los_metodos_que_no_sirven_para_el_monto(self):
        """Nadie paga un carro de $85.000.000 en efectivo en una tienda."""
        codigos = {metodo.codigo for metodo in metodos_disponibles(85_000_000)}

        self.assertIn(Pago.Metodo.TARJETA_CREDITO, codigos)
        self.assertIn(Pago.Metodo.PSE, codigos)
        self.assertNotIn(Pago.Metodo.EFECTIVO, codigos)
        self.assertNotIn(Pago.Metodo.BILLETERA_DIGITAL, codigos)

    def test_sin_monto_devuelve_el_catalogo_completo(self):
        self.assertEqual(len(metodos_disponibles()), len(CATALOGO_METODOS))


# ----------------------------------------------------------------------
# PagoBuilder
# ----------------------------------------------------------------------


class PagoBuilderTest(TestCase):
    def setUp(self):
        self.cliente = crear_cliente()
        self.vendedor = crear_vendedor()
        self.carro = crear_carro(self.vendedor, precio=85_000_000)

    def _builder(self, **cambios):
        builder = (
            PagoBuilder()
            .para_cliente(cambios.get("cliente", self.cliente))
            .por_carro(cambios.get("carro", self.carro))
            .con_metodo(
                cambios.get("metodo", Pago.Metodo.TARJETA_CREDITO),
                cambios.get("datos", TOKEN_DE_PRUEBA),
            )
        )
        if "cuotas" in cambios:
            builder.con_cuotas(cambios["cuotas"])
        if "referencia" in cambios:
            builder.con_referencia(cambios["referencia"])
        return builder

    def test_construye_un_pago_con_importes_calculados(self):
        pago = self._builder().build()

        self.assertEqual(pago.precio, 85_000_000)
        self.assertEqual(pago.comision, 2_465_900)  # 2,9% + $900
        self.assertEqual(pago.total, 87_465_900)
        self.assertEqual(pago.moneda, "COP")

    def test_el_pago_nace_pendiente_y_sin_persistir(self):
        pago = self._builder().build()

        self.assertEqual(pago.estado, Pago.Estado.PENDIENTE)
        self.assertIsNone(pago.pk)
        self.assertEqual(Pago.objects.count(), 0)

    def test_genera_referencia_cuando_no_se_indica(self):
        pago = self._builder().build()
        otro = self._builder().build()

        self.assertTrue(pago.referencia.startswith("CF-"))
        self.assertNotEqual(pago.referencia, otro.referencia)

    def test_respeta_la_referencia_recibida(self):
        pago = self._builder(referencia="CF-IDEMPOTENTE-1").build()

        self.assertEqual(pago.referencia, "CF-IDEMPOTENTE-1")

    def test_el_monto_lo_fija_el_precio_publicado(self):
        """El comprador no puede proponer cuánto paga."""
        carro = crear_carro(self.vendedor, precio=1_200_000, placa="XYZ98A")

        pago = self._builder(carro=carro).build()

        self.assertEqual(pago.precio, 1_200_000)

    def test_los_datos_sensibles_no_viajan_dentro_del_pago(self):
        builder = self._builder()

        pago = builder.build()

        self.assertEqual(builder.datos_metodo(), TOKEN_DE_PRUEBA)
        self.assertFalse(hasattr(pago, "token_tarjeta"))

    def test_permite_pagar_un_repuesto(self):
        repuesto = crear_repuesto(self.vendedor, precio=350_000)

        pago = (
            PagoBuilder()
            .para_cliente(self.cliente)
            .por_repuesto(repuesto)
            .con_metodo(Pago.Metodo.TARJETA_DEBITO, TOKEN_DE_PRUEBA)
            .build()
        )

        self.assertEqual(pago.repuesto, repuesto)
        self.assertIsNone(pago.carro)

    # ------------------------------------------------------------------
    # Invariantes
    # ------------------------------------------------------------------

    def test_rechaza_pago_sin_articulo(self):
        with self.assertRaises(PagoInvalidoError) as capturado:
            PagoBuilder().para_cliente(self.cliente).con_metodo(
                Pago.Metodo.PSE, {"banco": "1022", "tipo_persona": "NATURAL",
                                  "documento_pagador": "1017"}
            ).build()

        self.assertIn("carro o a un repuesto", str(capturado.exception))

    def test_rechaza_pago_de_dos_articulos_a_la_vez(self):
        repuesto = crear_repuesto(self.vendedor)

        with self.assertRaises(PagoInvalidoError) as capturado:
            self._builder().por_repuesto(repuesto).build()

        self.assertIn("un solo artículo", str(capturado.exception))

    def test_rechaza_pago_sin_cliente(self):
        with self.assertRaises(PagoInvalidoError) as capturado:
            PagoBuilder().por_carro(self.carro).con_metodo(
                Pago.Metodo.TARJETA_CREDITO, TOKEN_DE_PRUEBA
            ).build()

        self.assertIn("cliente", str(capturado.exception))

    def test_rechaza_metodo_no_soportado(self):
        with self.assertRaises(PagoInvalidoError) as capturado:
            self._builder(metodo="TRUEQUE").build()

        self.assertIn("TRUEQUE", str(capturado.exception))

    def test_rechaza_tarjeta_sin_token(self):
        with self.assertRaises(PagoInvalidoError) as capturado:
            self._builder(datos={}).build()

        self.assertIn("token_tarjeta", str(capturado.exception))

    def test_rechaza_pse_sin_los_datos_del_banco(self):
        with self.assertRaises(PagoInvalidoError) as capturado:
            self._builder(metodo=Pago.Metodo.PSE, datos={"banco": "1022"}).build()

        mensaje = str(capturado.exception)
        self.assertIn("tipo_persona", mensaje)
        self.assertIn("documento_pagador", mensaje)

    def test_rechaza_cuotas_en_un_metodo_que_no_las_permite(self):
        datos = {
            "banco": "1022",
            "tipo_persona": "NATURAL",
            "documento_pagador": "1017",
        }

        with self.assertRaises(PagoInvalidoError) as capturado:
            self._builder(metodo=Pago.Metodo.PSE, datos=datos, cuotas=12).build()

        self.assertIn("no permite diferir", str(capturado.exception))

    def test_rechaza_mas_cuotas_de_las_admitidas(self):
        with self.assertRaises(PagoInvalidoError) as capturado:
            self._builder(cuotas=48).build()

        self.assertIn("entre 1 y 36", str(capturado.exception))

    def test_acepta_cuotas_dentro_del_tope(self):
        pago = self._builder(cuotas=12).build()

        self.assertEqual(pago.cuotas, 12)

    def test_rechaza_monto_fuera_del_rango_del_metodo(self):
        """Un corresponsal no recibe $85.000.000 en efectivo."""
        with self.assertRaises(PagoInvalidoError) as capturado:
            self._builder(
                metodo=Pago.Metodo.EFECTIVO, datos={"documento_pagador": "1017"}
            ).build()

        self.assertIn("solo opera entre", str(capturado.exception))

    def test_nadie_compra_su_propio_articulo(self):
        cliente_vendedor = Cliente.objects.create(
            usuario=self.vendedor.usuario,
            nombre=self.vendedor.nombre,
            correo=self.vendedor.correo,
            direccion=self.vendedor.direccion,
            numero_tel=self.vendedor.numero_tel,
        )

        with self.assertRaises(PagoInvalidoError) as capturado:
            self._builder(cliente=cliente_vendedor).build()

        self.assertIn("su propio artículo", str(capturado.exception))

    def test_reporta_todos_los_errores_de_una_vez(self):
        with self.assertRaises(PagoInvalidoError) as capturado:
            self._builder(datos={}, cuotas=99).build()

        self.assertEqual(len(capturado.exception.errores), 2)
