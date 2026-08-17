from django.db import models
from decimal import Decimal

class ProductCategory(models.Model):
    id = models.CharField(max_length=50, primary_key=True, help_text='Identificador de la categoría')
    name = models.CharField(max_length=255, default='', blank=True, help_text='Nombre de la categoría')
    description = models.TextField(max_length=500, default='', blank=True, help_text='Descripción de la categoría')

    class Meta:
        verbose_name = 'Categoría de producto'
        verbose_name_plural = 'Categorías de producto'

    def __str__(self):
        name = (self.name or "").title()
        return f'{self.id.upper()} {name}'

class ProductClass(models.Model):
    id = models.CharField(primary_key=True, max_length=50, help_text='Identificador de la clase de producto')
    name = models.CharField(max_length=255, default='', blank=True, help_text='Nombre de la clase de producto')
    product_category = models.ForeignKey(ProductCategory, on_delete=models.PROTECT, related_name='product_classes', null=True, blank=True, help_text='Categoría de la clase de producto')

    class Meta:
        verbose_name = 'Clase de producto'
        verbose_name_plural = 'Clases de producto'

    def save(self, *args, **kwargs):
        if self.name:
            self.name = self.name.strip().lower()

        super().save(*args, **kwargs)

    def __str__(self):
        name = (self.name or "").title()
        return f'{self.id.upper()} {name}'

class ProductProperty(models.Model):
    id = models.CharField(max_length=50, primary_key=True, help_text='Identificador de la propiedad (ej: SUSTANCIA_ACTIVA, LABORATORIO)')
    name = models.CharField(max_length=255, help_text='Nombre de la propiedad')
    description = models.TextField(max_length=500, default='', blank=True, null=True, help_text='Descripción de la propiedad')

    class Meta:
        verbose_name = 'Propiedad de producto'
        verbose_name_plural = 'Propiedades de producto'

    def __str__(self):
        name = (self.name or "").title()
        return f'{self.id.upper()} {name}'

class Product(models.Model):
    id = models.CharField(primary_key=True, max_length=255, help_text='Identificador del producto')
    barcode = models.CharField(blank=True, null=True, max_length=255, help_text='Código de barras del producto')
    name = models.CharField(max_length=255, null=True, blank=True, help_text='Nombre del producto')
    product_class = models.ForeignKey('ProductClass', on_delete=models.PROTECT, related_name='products', null=True, blank=True, help_text='Clase del producto')
    cost = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal('0.00'), blank=True, help_text='Costo del producto')
    price = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), blank=True, help_text='Precio del producto')
    unit_of_measure = models.CharField(max_length=255, null=True, blank=True, help_text='Unidad de medida del producto')
    is_active = models.BooleanField(default=True, help_text='Indica si el producto está activo')
    properties = models.ManyToManyField('ProductProperty',through='ProductPropertyValue',related_name='products',blank=True,help_text='Propiedades del producto')

    class Meta:
        verbose_name = 'Producto'
        verbose_name_plural = 'Productos'

    def __str__(self):
        name = (self.name or "").title()
        return f'{self.id.upper()} {name}'

class ProductPropertyValue(models.Model):
    product = models.ForeignKey('Product', on_delete=models.CASCADE, related_name='property_values', help_text='Producto asociado')
    property = models.ForeignKey('ProductProperty', on_delete=models.PROTECT, related_name='product_values', help_text='Propiedad asignada')
    value = models.CharField(max_length=500, help_text='Valor de la propiedad')

    class Meta:
        verbose_name = 'Valor de propiedad'
        verbose_name_plural = 'Valores de propiedades'
        constraints = [
            models.UniqueConstraint(
                fields=['product', 'property'],
                name='unique_product_property'
            )
        ]
        indexes = [
            models.Index(fields=['property', 'value']),
        ]

    def __str__(self):
        return f'{self.product.id.upper()} -> {self.property.name.title()}: {self.value}'

class Stock(models.Model):
    product = models.ForeignKey('Product', on_delete=models.PROTECT, related_name='stocks', null=True, blank=True)
    warehouse = models.ForeignKey('sales.Warehouse', on_delete=models.PROTECT, related_name='stocks', null=True, blank=True)
    lot_number = models.CharField(max_length=100, default='', blank=True, help_text='Número o identificador del lote')
    expiration_date = models.DateField(null=True, blank=True, help_text='Fecha de expiración del lote')
    quantity = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, help_text='Cantidad en stock')
    updated_at = models.DateTimeField(auto_now=True, help_text='Fecha de la última actualización')

    class Meta:
        verbose_name = 'Existencia'
        verbose_name_plural = 'Existencias'
        constraints = [
            models.UniqueConstraint(
                fields=['product', 'warehouse', 'lot_number'],
                name='unique_stock_product_warehouse_lot'
            )
        ]
        indexes = [
            models.Index(fields=['expiration_date']),
            models.Index(fields=['warehouse', 'expiration_date']),
            models.Index(fields=['product', 'warehouse']),
            models.Index(fields=['lot_number']),
        ]

    def __str__(self):
        lot_str = f' [Lote: {self.lot_number}]' if self.lot_number else ''
        exp_str = f' (Vence: {self.expiration_date:%d/%m/%Y})' if self.expiration_date else ''
        return f'{self.product.id.upper()} @ {self.warehouse.name.title()}: {self.quantity:,.2f}{lot_str}{exp_str}'