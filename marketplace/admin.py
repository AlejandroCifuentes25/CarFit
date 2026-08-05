from django.contrib import admin

from .models import (
    Carro,
    Cliente,
    DocumentoCarro,
    Inventario,
    Pago,
    Repuesto,
    Resena,
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


admin.site.register([Cliente, Inventario, Resena, Pago])
