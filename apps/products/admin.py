from django.contrib import admin
from .models import (
    ProductCategory,
    ProductClass,
    ProductProperty,
    Product,
    ProductPropertyValue,
    Stock,
)


class ProductPropertyValueInline(admin.TabularInline):
    model = ProductPropertyValue
    extra = 1
    fields = ('property', 'value')
    autocomplete_fields = ['property']
    show_change_link = True


class StockInline(admin.TabularInline):
    model = Stock
    extra = 1
    fields = ('warehouse', 'lot_number', 'expiration_date', 'quantity')
    autocomplete_fields = ['warehouse']
    show_change_link = True


@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'description')
    search_fields = ('id', 'name')
    ordering = ('id',)


@admin.register(ProductClass)
class ProductClassAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'product_category')
    list_filter = ('product_category',)
    search_fields = ('id', 'name', 'product_category__name')
    autocomplete_fields = ['product_category']
    ordering = ('id',)


@admin.register(ProductProperty)
class ProductPropertyAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'description')
    search_fields = ('id', 'name')
    ordering = ('id',)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'name',
        'barcode',
        'product_class',
        'cost',
        'price',
        'unit_of_measure',
        'is_active',
    )
    list_filter = (
        'is_active',
        'product_class__product_category',
        'product_class',
    )
    search_fields = ('id', 'name', 'barcode')
    autocomplete_fields = ['product_class']
    ordering = ('name', 'id')
    inlines = [ProductPropertyValueInline, StockInline]


@admin.register(ProductPropertyValue)
class ProductPropertyValueAdmin(admin.ModelAdmin):
    list_display = ('product', 'property', 'value')
    list_filter = ('property',)
    search_fields = (
        'product__id',
        'product__name',
        'property__name',
        'value',
    )
    autocomplete_fields = ['product', 'property']
    ordering = ('product', 'property')


@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = (
        'product',
        'warehouse',
        'lot_number',
        'expiration_date',
        'quantity',
        'updated_at',
    )
    list_filter = (
        'warehouse__warehouse_type',
        'warehouse',
        'expiration_date',
    )
    search_fields = (
        'product__id',
        'product__name',
        'warehouse__name',
        'lot_number',
    )
    autocomplete_fields = ['product', 'warehouse']
    ordering = ('product', 'warehouse', 'expiration_date')
