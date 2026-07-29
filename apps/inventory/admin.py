import json
from django.contrib import admin
from django.db import models
from django.forms import widgets
from .models import (
    ProductCategory, ProductClass, Product, ProductVariant,
    Attribute, VariantAttribute, Warehouse, Batch,
    Stock, StockMovement
)


from .forms import ProductAdminForm


class PrettyJSONWidget(widgets.Textarea):
    '''
    Widget that formats JSONField content with multi-line indentation 
    and dark-mode code editor styling in Django Admin.
    '''
    def format_value(self, value):
        try:
            if isinstance(value, str):
                value = json.loads(value)
            return json.dumps(value, indent=2, ensure_ascii=False)
        except Exception:
            return super().format_value(value)


json_widget = PrettyJSONWidget(attrs={
    'style': 'font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 13px; background-color: #1e293b; color: #38bdf8; border: 1px solid #334155; border-radius: 6px; padding: 12px; width: 100%; min-height: 240px;',
    'rows': 12,
    'placeholder': '{\n  "target_species": ["caninos"],\n  "administration_route": "Oral"\n}'
})


@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'description')
    search_fields = ('id', 'name')

@admin.register(ProductClass)
class ProductClassAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'product_category')
    list_filter = ('product_category',)
    search_fields = ('id', 'name')

class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1
    show_change_link = True
    formfield_overrides = {
        models.JSONField: {'widget': json_widget}
    }

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    form = ProductAdminForm
    list_display = ('id', 'name', 'product_class', 'is_active')
    list_filter = ('product_class', 'is_active')
    search_fields = ('id', 'name')
    inlines = [ProductVariantInline]

class VariantAttributeInline(admin.TabularInline):
    model = VariantAttribute
    extra = 1

@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'product', 'barcode', 'external_id', 'is_active')
    list_filter = ('product__product_class', 'is_active')
    search_fields = ('id', 'name', 'barcode', 'external_id', 'product__name')
    inlines = [VariantAttributeInline]
    formfield_overrides = {
        models.JSONField: {'widget': json_widget}
    }

@admin.register(Attribute)
class AttributeAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name', 'description')

@admin.register(VariantAttribute)
class VariantAttributeAdmin(admin.ModelAdmin):
    list_display = ('variant', 'attribute', 'value')
    list_filter = ('attribute',)
    search_fields = ('variant__name', 'variant__id', 'attribute__name', 'value')

@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'type')
    list_filter = ('type',)
    search_fields = ('id', 'name')

@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display = ('id', 'variant', 'lot', 'expiration_date', 'manufacturing_date')
    list_filter = ('expiration_date', 'variant__product')
    search_fields = ('id', 'lot', 'variant__id', 'variant__name')

@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = ('warehouse', 'batch', 'quantity', 'updated_at')
    list_filter = ('warehouse', 'batch__variant__product')
    search_fields = ('warehouse__name', 'batch__lot', 'batch__variant__id')

@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ('id', 'stock', 'type', 'quantity', 'reference', 'created_at')
    list_filter = ('type', 'stock__warehouse', 'created_at')
    search_fields = ('reference', 'stock__batch__lot', 'stock__batch__variant__id')
