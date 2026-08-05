"""Pruebas del CarroBuilder.

Ninguna toca la base de datos: el Builder es dominio puro y `build()` no
persiste. Eso es justamente lo que hace estas reglas baratas de probar.
"""

from datetime import date

from django.test import SimpleTestCase

from ..domain.builders import CarroBuilder
from ..domain.exceptions import ArticuloInvalidoError
from ..models import DocumentoCarro, Vendedor


def documentos_completos():
    return [
        DocumentoCarro(
            tipo_documento=DocumentoCarro.Tipo.SOAT,
            fecha_expedicion=date(2026, 1, 10),
            fecha_vencimiento=date(2027, 1, 10),
        ),
        DocumentoCarro(
            tipo_documento=DocumentoCarro.Tipo.TECNOMECANICA,
            fecha_expedicion=date(2026, 2, 1),
            fecha_vencimiento=date(2027, 2, 1),
        ),
    ]


def builder_valido():
    return (
        CarroBuilder()
        .para_vendedor(Vendedor(nombre="Alejandro"))
        .con_identificacion("abc123", "Mazda", "CX-30")
        .con_caracteristicas("Rojo", 15_000, "usado")
        .con_precio(85_000_000)
        .con_documentos(documentos_completos())
    )


class CarroBuilderTest(SimpleTestCase):
    def test_construye_un_carro_valido(self):
        carro = builder_valido().build()

        self.assertEqual(carro.placa, "ABC123")
        self.assertEqual(carro.marca, "Mazda")
        self.assertEqual(carro.precio, 85_000_000)

    def test_normaliza_placa_y_estado_a_mayusculas(self):
        carro = builder_valido().build()

        self.assertEqual(carro.placa, "ABC123")
        self.assertEqual(carro.estado, "USADO")

    def test_los_pasos_devuelven_el_mismo_builder(self):
        builder = CarroBuilder()

        self.assertIs(builder.para_vendedor(Vendedor()), builder)
        self.assertIs(builder.con_precio(1), builder)

    def test_rechaza_placa_con_formato_invalido(self):
        builder = builder_valido().con_identificacion("XX1", "Mazda", "CX-30")

        with self.assertRaises(ArticuloInvalidoError) as capturado:
            builder.build()

        self.assertIn("no cumple el formato colombiano", str(capturado.exception))

    def test_rechaza_carro_nuevo_con_kilometraje_alto(self):
        builder = builder_valido().con_caracteristicas("Rojo", 80_000, "NUEVO")

        with self.assertRaises(ArticuloInvalidoError) as capturado:
            builder.build()

        self.assertIn("NUEVO no puede superar", str(capturado.exception))

    def test_rechaza_precio_cero(self):
        builder = builder_valido().con_precio(0)

        with self.assertRaises(ArticuloInvalidoError) as capturado:
            builder.build()

        self.assertIn("precio debe ser un entero positivo", str(capturado.exception))

    def test_rechaza_publicacion_sin_documentos_obligatorios(self):
        builder = builder_valido().con_documentos([])

        with self.assertRaises(ArticuloInvalidoError) as capturado:
            builder.build()

        self.assertIn("Faltan documentos obligatorios", str(capturado.exception))

    def test_reporta_todos_los_errores_de_una_vez(self):
        builder = (
            CarroBuilder()
            .con_identificacion("", "", "")
            .con_caracteristicas("", -5, "CHATARRA")
            .con_precio(-1)
        )

        with self.assertRaises(ArticuloInvalidoError) as capturado:
            builder.build()

        # vendedor, placa, marca, modelo, color, estado, kilometraje, precio, documentos
        self.assertGreaterEqual(len(capturado.exception.errores), 8)
