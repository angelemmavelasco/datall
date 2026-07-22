from django.contrib import admin
import nested_admin
from .models import (
    Sale, SaleLine, SaleLineTax,
    Invoice, InvoiceItem, InvoiceItemTax, InvoiceRelation
)

class SaleLineTaxInline(nested_admin.NestedTabularInline):
    model = SaleLineTax
    extra = 0

class SaleLineInline(nested_admin.NestedTabularInline):
    model = SaleLine
    extra = 0
    inlines = [SaleLineTaxInline]

@admin.register(Sale)
class SaleAdmin(nested_admin.NestedModelAdmin):
    list_display = ['doc_id', 'sale_date', 'customer', 'sale_status', 'payment_status', 'total']
    list_filter = ['sale_status', 'payment_status', 'sale_date']
    search_fields = ['doc_id']
    inlines = [SaleLineInline]
    readonly_fields = ['created_at', 'updated_at']

@admin.register(SaleLine)
class SaleLineAdmin(nested_admin.NestedModelAdmin):
    list_display = ['sale', 'product', 'quantity', 'unit_price', 'total']
    search_fields = ['sale__doc_id']
    inlines = [SaleLineTaxInline]
    
    # Ocultar del index del admin para no saturar, se accede a través del Sale
    def get_model_perms(self, request):
        perms = super().get_model_perms(request)
        perms['add'] = False
        return perms

class InvoiceItemTaxInline(admin.TabularInline):
    model = InvoiceItemTax
    extra = 0

class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 0
    show_change_link = True

class InvoiceRelationInline(admin.TabularInline):
    model = InvoiceRelation
    fk_name = 'source_invoice'
    extra = 0

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ['uuid', 'serie', 'folio', 'date', 'receiver_rfc', 'cfdi_type', 'status', 'total']
    list_filter = ['cfdi_type', 'status', 'date']
    search_fields = ['uuid', 'folio', 'receiver_rfc', 'receiver_name']
    inlines = [InvoiceItemInline, InvoiceRelationInline]
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        ('Identificadores', {
            'fields': ('uuid', 'serie', 'folio', 'date', 'status')
        }),
        ('Comprobante', {
            'fields': ('cfdi_type', 'payment_form', 'payment_method', 'currency', 'exchange_rate', 'exportation', 'expedition_place')
        }),
        ('Receptor', {
            'fields': ('receiver_rfc', 'receiver_name', 'receiver_cfdi_use', 'receiver_fiscal_regime', 'receiver_zip_code')
        }),
        ('Emisor', {
            'fields': ('issuer_rfc', 'issuer_name', 'issuer_fiscal_regime', 'issuer_zip_code')
        }),
        ('Totales', {
            'fields': ('subtotal', 'discount', 'total')
        }),
        ('Archivos y Metadatos', {
            'fields': ('xml_file', 'pdf_file', 'api_response', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

@admin.register(InvoiceItem)
class InvoiceItemAdmin(admin.ModelAdmin):
    list_display = ['invoice', 'product_code', 'description', 'quantity', 'total_display']
    search_fields = ['invoice__uuid', 'product_code', 'description']
    inlines = [InvoiceItemTaxInline]
    
    def total_display(self, obj):
        return obj.subtotal - obj.discount
    total_display.short_description = 'Total'
    
    # Ocultar del index del admin
    def get_model_perms(self, request):
        perms = super().get_model_perms(request)
        perms['add'] = False
        return perms
