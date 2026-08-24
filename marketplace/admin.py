from django.contrib import admin

from .models import (
    Carro,
    Cliente,
    DocumentoCarro,
    Inventario,
    Pago,
    Repuesto,
    Resena,
    TransaccionPago,
    Vendedor,
)


class DocumentoCarroInline(admin.TabularInline):
    model = DocumentoCarro
    extra = 0


@admin.register(Carro)
class CarroAdmin(admin.ModelAdmin):
    list_display = ("placa", "marca", "modelo", "estado", "precio", "vendedor")
    list_filter = ("estado", "marca")
    search_fields = ("placa", "marca", "modelo")
    inlines = [DocumentoCarroInline]


@admin.register(Repuesto)
class RepuestoAdmin(admin.ModelAdmin):
    list_display = ("tipo", "modelo_carro", "numero_serie", "estado", "precio")
    list_filter = ("estado",)
    search_fields = ("tipo", "numero_serie")


@admin.register(Vendedor)
class VendedorAdmin(admin.ModelAdmin):
    list_display = ("nombre", "correo", "numero_tel", "resena")
    search_fields = ("nombre", "correo")


class TransaccionPagoInline(admin.TabularInline):
    """Bitácora del pago. Es evidencia de auditoría: se lee, no se edita."""

    model = TransaccionPago
    extra = 0
    can_delete = False
    readonly_fields = (
        "operacion",
        "pasarela",
        "estado_resultante",
        "codigo_autorizacion",
        "mensaje",
        "creado_en",
    )

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Pago)
class PagoAdmin(admin.ModelAdmin):
    list_display = (
        "referencia",
        "cliente",
        "metodo_pago",
        "estado",
        "total",
        "fecha",
    )
    list_filter = ("estado", "metodo_pago", "pasarela")
    search_fields = ("referencia", "referencia_pasarela", "codigo_autorizacion")
    date_hierarchy = "fecha"
    inlines = [TransaccionPagoInline]

    # Un pago se corrige con una anulación o un reembolso, nunca editándolo
    # a mano: los importes y el estado los fija el flujo de cobro.
    readonly_fields = (
        "referencia",
        "precio",
        "comision",
        "total",
        "moneda",
        "pasarela",
        "referencia_pasarela",
        "codigo_autorizacion",
        "fecha",
        "actualizado_en",
    )


admin.site.register([Cliente, Inventario, Resena])
