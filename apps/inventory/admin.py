from django.contrib import admin
from .models import (
    ProductCategory, ProductClass, Product, ProductVariant,
    Attribute, VariantAttribute, Warehouse, Batch,
    Stock, StockMovement
)

admin.site.register(ProductCategory)
admin.site.register(ProductClass)
admin.site.register(Product)
admin.site.register(ProductVariant)
admin.site.register(Attribute)
admin.site.register(VariantAttribute)
admin.site.register(Warehouse)
admin.site.register(Batch)
admin.site.register(Stock)
admin.site.register(StockMovement)
