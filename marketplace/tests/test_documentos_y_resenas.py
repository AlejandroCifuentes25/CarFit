from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from marketplace.domain.exceptions import ErrorDeDominio
from marketplace.models import Carro, Cliente, DocumentoCarro, Resena, Vendedor
from marketplace.services import DocumentoCarroService, ResenaService


class DocumentoCarroServiceTests(TestCase):
    def setUp(self):
        self.user_vendedor = User.objects.create_user(username="vend_doc", password="123")
        self.vendedor = Vendedor.objects.create(
            usuario=self.user_vendedor,
            nombre="Concesionario Norte",
            correo="norte@carfit.co",
            direccion="Calle 100",
            numero_tel="3001112233",
        )
        self.carro = Carro.objects.create(
            vendedor=self.vendedor,
            placa="DOC123",
            marca="Mazda",
            modelo="3",
            estado="USADO",
            color="Gris",
            kilometraje=25000,
            precio=70000000,
        )
        self.hoy = date.today()

    def test_verificar_cumplimiento_detecta_documentos_faltantes(self):
        reporte = DocumentoCarroService().verificar_cumplimiento(self.carro)
        self.assertFalse(reporte["cumple"])
        self.assertIn("SOAT", reporte["faltantes"])
        self.assertIn("TECNOMECANICA", reporte["faltantes"])

    def test_verificar_cumplimiento_aprueba_cuando_soat_y_tecnomecanica_estan_vigentes(self):
        servicio = DocumentoCarroService()
        servicio.guardar_documento(
            self.vendedor,
            self.carro,
            {
                "tipo_documento": DocumentoCarro.Tipo.SOAT,
                "fecha_expedicion": self.hoy - timedelta(days=30),
                "fecha_vencimiento": self.hoy + timedelta(days=335),
            },
        )
        servicio.guardar_documento(
            self.vendedor,
            self.carro,
            {
                "tipo_documento": DocumentoCarro.Tipo.TECNOMECANICA,
                "fecha_expedicion": self.hoy - timedelta(days=15),
                "fecha_vencimiento": self.hoy + timedelta(days=350),
            },
        )

        reporte = servicio.verificar_cumplimiento(self.carro)
        self.assertTrue(reporte["cumple"])
        self.assertEqual(reporte["faltantes"], [])
        self.assertEqual(len(reporte["documentos"]), 2)

    def test_guardar_documento_impide_que_otro_vendedor_modifique_papeles(self):
        otro_user = User.objects.create_user(username="otro_vend", password="123")
        otro_vendedor = Vendedor.objects.create(
            usuario=otro_user,
            nombre="Otro",
            correo="otro@carfit.co",
            direccion="Cra 1",
            numero_tel="3000000000",
        )
        with self.assertRaises(ErrorDeDominio):
            DocumentoCarroService().guardar_documento(
                otro_vendedor,
                self.carro,
                {
                    "tipo_documento": DocumentoCarro.Tipo.SOAT,
                    "fecha_expedicion": self.hoy,
                    "fecha_vencimiento": self.hoy + timedelta(days=30),
                },
            )

    def test_comprador_ve_vigencia_pero_no_archivo_original_del_propietario(self):
        archivo = SimpleUploadedFile("soat_privado.pdf", b"%PDF-1.4 contenido", content_type="application/pdf")
        DocumentoCarroService().guardar_documento(
            self.vendedor,
            self.carro,
            {
                "tipo_documento": DocumentoCarro.Tipo.SOAT,
                "fecha_expedicion": self.hoy - timedelta(days=10),
                "fecha_vencimiento": self.hoy + timedelta(days=355),
                "archivo": archivo,
            },
        )
        comprador = User.objects.create_user(username="comprador_doc", password="123")
        self.client.force_login(comprador)

        resp_api = self.client.get(reverse("marketplace_api:carro_documentos", args=[self.carro.pk]))
        self.assertEqual(resp_api.status_code, 200)
        doc_json = resp_api.json()["documentos"][0]
        self.assertTrue(doc_json["tiene_soporte"])
        self.assertIsNone(doc_json["archivo_url"])

        # El vendedor dueño sí puede ver la ruta del archivo original
        self.client.force_login(self.user_vendedor)
        resp_dueno = self.client.get(reverse("marketplace_api:carro_documentos", args=[self.carro.pk]))
        self.assertIsNotNone(resp_dueno.json()["documentos"][0]["archivo_url"])

    def test_flujo_solicitar_y_aprobar_acceso_a_archivos_del_vehiculo(self):
        archivo = SimpleUploadedFile("soat_privado.pdf", b"%PDF-1.4 contenido", content_type="application/pdf")
        servicio = DocumentoCarroService()
        servicio.guardar_documento(
            self.vendedor,
            self.carro,
            {
                "tipo_documento": DocumentoCarro.Tipo.SOAT,
                "fecha_expedicion": self.hoy - timedelta(days=10),
                "fecha_vencimiento": self.hoy + timedelta(days=355),
                "archivo": archivo,
            },
        )
        user_comprador = User.objects.create_user(username="comprador_sol", password="123")
        cliente_comprador = Cliente.objects.create(
            usuario=user_comprador,
            nombre="Carlos Interesado",
            correo="carlos@carfit.co",
            direccion="Calle 10",
            numero_tel="3005556677",
        )

        # 1. Inicialmente no tiene acceso
        self.assertFalse(servicio.tiene_acceso_archivos(user_comprador, self.carro))

        # 2. El comprador solicita acceso (queda PENDIENTE, aún sin acceso)
        solicitud = servicio.solicitar_acceso(cliente_comprador, self.carro)
        self.assertEqual(solicitud.estado, "PENDIENTE")
        self.assertFalse(servicio.tiene_acceso_archivos(user_comprador, self.carro))

        # 3. El vendedor aprueba la solicitud -> ahora el comprador sí tiene acceso
        servicio.resolver_solicitud(self.vendedor, solicitud.pk, aprobar=True)
        self.assertTrue(servicio.tiene_acceso_archivos(user_comprador, self.carro))

        # 4. El vendedor revoca el acceso -> vuelve a perder acceso
        servicio.resolver_solicitud(self.vendedor, solicitud.pk, aprobar=False)
        self.assertFalse(servicio.tiene_acceso_archivos(user_comprador, self.carro))


class ResenaServiceAndViewsTests(TestCase):
    def setUp(self):
        self.user_vendedor = User.objects.create_user(username="vend_res", password="123")
        self.vendedor = Vendedor.objects.create(
            usuario=self.user_vendedor,
            nombre="Autos Premium",
            correo="premium@carfit.co",
            direccion="Av 68",
            numero_tel="3109998877",
        )
        self.user_cliente = User.objects.create_user(username="cli_res", password="123")
        self.cliente = Cliente.objects.create(
            usuario=self.user_cliente,
            nombre="Laura Compradora",
            correo="laura@carfit.co",
            direccion="Calle 50",
            numero_tel="3201112233",
        )

    def test_crear_resena_actualiza_promedio_del_vendedor(self):
        servicio = ResenaService()
        servicio.crear_resena(
            self.cliente,
            self.vendedor.pk,
            {"calificacion": 5, "tipo": "COMPRA", "contenido": "Excelente atención."},
        )
        servicio.crear_resena(
            self.cliente,
            self.vendedor.pk,
            {"calificacion": 3, "tipo": "ATENCION", "contenido": "Demoró un poco."},
        )

        self.vendedor.refresh_from_db()
        self.assertEqual(self.vendedor.resena, 4)
        resumen = servicio.listar_por_vendedor(self.vendedor.pk)
        self.assertEqual(resumen["total_resenas"], 2)
        self.assertEqual(resumen["promedio"], 4.0)

    def test_vendedor_no_puede_resenarse_a_si_mismo(self):
        cliente_propio = Cliente.objects.create(
            usuario=self.user_vendedor,
            nombre="Autos Premium",
            correo="premium@carfit.co",
            direccion="Av 68",
            numero_tel="3109998877",
        )
        with self.assertRaises(ErrorDeDominio):
            ResenaService().crear_resena(
                cliente_propio,
                self.vendedor.pk,
                {"calificacion": 5, "tipo": "GENERAL", "contenido": "Auto reseña"},
            )

    def test_vista_y_api_resenas_vendedor_funcionan(self):
        self.client.force_login(self.user_cliente)
        url_vista = reverse("marketplace:resenas_vendedor", args=[self.vendedor.pk])
        resp = self.client.post(
            url_vista,
            {"calificacion": 5, "tipo": "COMPRA", "contenido": "Muy cumplido con los papeles."},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Resena.objects.filter(vendedor=self.vendedor).count(), 1)

        url_api = reverse("marketplace_api:vendedor_resenas", args=[self.vendedor.pk])
        resp_api = self.client.get(url_api)
        self.assertEqual(resp_api.status_code, 200)
        self.assertEqual(resp_api.json()["total_resenas"], 1)
