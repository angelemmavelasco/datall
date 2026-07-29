from django.db import models
from decimal import Decimal
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
import jsonschema
from .schemas import PRODUCT_PROPERTIES_SCHEMA, VARIANT_PROPERTIES_SCHEMA


def validate_product_properties(value):
    if value:
        try:
            jsonschema.validate(instance=value, schema=PRODUCT_PROPERTIES_SCHEMA)
        except jsonschema.exceptions.ValidationError as e:
            raise ValidationError(f"Error en las propiedades del producto: {e.message}")


def validate_variant_properties(value):
    if value:
        try:
            jsonschema.validate(instance=value, schema=VARIANT_PROPERTIES_SCHEMA)
        except jsonschema.exceptions.ValidationError as e:
            raise ValidationError(f"Error en las propiedades de la variante: {e.message}")


class ProductCategory(models.Model):
    id = models.CharField(max_length=50, primary_key=True, help_text='Identificador único de la categoría')
    name = models.CharField(max_length=255, null=True, blank=True, help_text='Nombre de la categoría')
    description = models.TextField(max_length=500, default='', blank=True, help_text='Descripción detallada de la categoría')

    class Meta:
        verbose_name = 'Categoría de producto'
        verbose_name_plural = 'Categorías de producto'

    def __str__(self):
        return f'{self.id.upper()} {self.name.title()}'

class ProductClass(models.Model):
    id = models.CharField(primary_key=True, max_length=50, help_text='Identificador único de la clase')
    name = models.CharField(max_length=255, null=True, blank=True, help_text='Nombre de la clase')
    product_category = models.ForeignKey('ProductCategory', on_delete=models.PROTECT, related_name='%(app_label)s_product_classes', null=True, blank=True, help_text='Categoría a la que pertenece esta clase')

    class Meta:
        verbose_name = 'Clase de producto'
        verbose_name_plural = 'Clases de producto'

    def __str__(self):
        return f'{self.id.upper()} {self.name.title()}'

class Product(models.Model):
    id = models.CharField(primary_key=True, max_length=50, help_text='Identificador único del producto')
    name = models.CharField(max_length=255, null=True, blank=True, help_text='Nombre general del producto')
    product_class = models.ForeignKey('ProductClass', on_delete=models.PROTECT, related_name='%(app_label)s_products', null=True, blank=True, help_text='Clase a la que pertenece el producto')
    properties = models.JSONField(default=dict, blank=True, validators=[validate_product_properties], help_text='Propiedades del producto')
    is_active = models.BooleanField(default=True, help_text='Indica si el producto está activo')

    class Meta:
        verbose_name = 'Producto'
        verbose_name_plural = 'Productos'

    def __str__(self):
        return f'{self.id.upper()} {self.name.title()}'

class ProductVariant(models.Model):
    id = models.CharField(primary_key=True, max_length=50, help_text='Identificador único de la variante (ej. SKU)')
    barcode = models.CharField(max_length=50, null=True, blank=True, help_text='Código de barras (UPC/EAN)')
    external_id = models.CharField(max_length=50, null=True, blank=True, help_text='Identificador en sistemas externos (ej. ERP, eCommerce, proveedor)')
    product = models.ForeignKey('Product', on_delete=models.PROTECT, related_name='%(app_label)s_product_variants', help_text='Producto base de esta variante')
    name = models.CharField(max_length=255, null=True, blank=True, help_text='Nombre específico de la variante')
    properties = models.JSONField(default=dict, blank=True, validators=[validate_variant_properties], help_text='Propiedades funcionales o intrínsecas (ej. especie destino, calorías). Describen la función, no lo que lo hace una variante. Varias variantes pueden compartir las mismas propiedades. No confundir con los atributos.')
    is_active = models.BooleanField(default=True, help_text='Indica si la variante está activa')
    
    class Meta:
        verbose_name = 'Variante de producto'
        verbose_name_plural = 'Variantes de producto'

    def __str__(self):
        return f'{self.product.id.upper()}. Variante: {self.id.upper()} {self.name.title()}'


class Attribute(models.Model):
    name = models.CharField(max_length=255, help_text='Característica que describe y diferencia al producto (ej. presentación, color), convirtiéndolo en una variante.')
    description = models.TextField(default='', blank=True, help_text='Descripción opcional del atributo')

    class Meta:
        verbose_name = 'Atributo'
        verbose_name_plural = 'Atributos'

    def __str__(self):
        return f'{self.name.title()}'

class VariantAttribute(models.Model):
    variant = models.ForeignKey('ProductVariant', on_delete=models.CASCADE, related_name='%(app_label)s_variant_attributes', help_text='Variante a la que se le asigna el atributo')
    attribute = models.ForeignKey('Attribute', on_delete=models.PROTECT, related_name='%(app_label)s_variant_attributes', help_text='Atributo asignado')
    value = models.CharField(max_length=100, help_text='Valor del atributo para esta variante (ej. Rojo, 500ml)')
    class Meta:
        verbose_name = 'Atributo de Variantes'
        verbose_name_plural = 'Atributos de Variantes'
        unique_together = ('variant', 'attribute')

    def __str__(self):
        return f'{self.variant.id.upper()}. {self.attribute.name.title()}: {self.value.title()}'
    
class Warehouse(models.Model):
    class WarehouseTypeChoices(models.TextChoices):
        WAREHOUSE = 'warehouse', 'almacén'
        RETAIL = 'retail', 'tienda'
        TRANSFER = 'transfer', 'traspaso'
        DAMAGED = 'damaged', 'dañado/merma'
        
    id = models.CharField(primary_key=True, max_length=50, help_text='Identificador del centro de distribución')
    name = models.CharField(max_length=50, unique=True, help_text='Nombre del centro de distribución')
    type = models.CharField(max_length=20, choices=WarehouseTypeChoices.choices, default=WarehouseTypeChoices.WAREHOUSE, help_text='Tipo de centro de distribución')

    class Meta:
        verbose_name = 'Centro de distribución'
        verbose_name_plural = 'Centros de distribución'

    def __str__(self):
        return f'{self.id.upper()} {self.name.title()} - {self.get_type_display().title()}'

class Batch(models.Model):
    id = models.CharField(primary_key=True, max_length=50, help_text='Identificador único del lote (ej. BATCH-2026-001)')
    variant = models.ForeignKey('ProductVariant', on_delete=models.PROTECT, related_name='%(app_label)s_batches', help_text='Variante de producto asociada a este lote')
    lot = models.CharField(max_length=50, null=True, blank=True, help_text='Número/Código de lote impreso por proveedor')
    expiration_date = models.DateField(null=True, blank=True, help_text='Fecha de caducidad')
    manufacturing_date = models.DateField(null=True, blank=True, help_text='Fecha de fabricación')
    created_at = models.DateTimeField(auto_now_add=True, help_text='Fecha de registro del lote')

    class Meta:
        verbose_name = 'Lote'
        verbose_name_plural = 'Lotes'
        unique_together = ('variant', 'lot')

    def __str__(self):
        lot_str = self.lot.upper() if self.lot else 'SIN LOTE'
        exp_str = self.expiration_date if self.expiration_date else 'S/EXP'
        return f'{self.variant.id.upper()} Lote: {lot_str}. Exp: {exp_str}'

class Stock(models.Model):
    warehouse = models.ForeignKey('Warehouse', on_delete=models.PROTECT, related_name='%(app_label)s_stocks', help_text='Centro de distribución con dicha existencia')
    batch = models.ForeignKey('Batch', on_delete=models.PROTECT, related_name='%(app_label)s_stocks', help_text='Lote con dicha existencia')
    quantity = models.DecimalField(max_digits=10, decimal_places=2, help_text='Cantidad en existencia')
    updated_at = models.DateTimeField(auto_now=True, help_text='Fecha de la última actualización de la existencia')

    class Meta:
        verbose_name = 'Existencia'
        verbose_name_plural = 'Existencias'
        unique_together = ('warehouse', 'batch')

    def __str__(self):
        lot_str = self.batch.lot.upper() if self.batch.lot else 'SIN LOTE'
        return f'{self.warehouse.id.upper()} -> {self.batch.variant.id.upper()} - Lot: {lot_str} - Cant: {self.quantity}'
    
    
class StockMovement(models.Model):
    class StockMovementTypeChoices(models.TextChoices):
        IN = 'in', 'Entrada'
        OUT = 'out', 'Salida'
        FIX_IN = 'fix_in', 'Ajuste positivo'
        FIX_OUT = 'fix_out', 'Ajuste negativo'

    stock = models.ForeignKey('Stock', on_delete=models.PROTECT, related_name='%(app_label)s_movements', help_text='Registro de existencia que recibe el movimiento')
    type = models.CharField(max_length=20, choices=StockMovementTypeChoices.choices, default=StockMovementTypeChoices.IN, help_text='Indica si el movimiento suma, resta o ajusta el inventario')
    quantity = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))], help_text='Cantidad (siempre positiva)')
    reference = models.CharField(max_length=50, null=True, blank=True, help_text='Referencia (ej. Folio de compra, Factura, Venta)')
    created_at = models.DateTimeField(auto_now_add=True, help_text='Fecha de creación del movimiento')

    class Meta:
        verbose_name = 'Movimiento de existencia'
        verbose_name_plural =  'Movimientos de existencias'
        constraints = [models.CheckConstraint(condition=models.Q(quantity__gt=0), name='stock_movement_quantity_gt_zero')]

    def __str__(self):
        ref_str = f' ({self.reference})' if self.reference else ''
        return f'{self.get_type_display()}: {self.quantity} unidades en {self.stock.warehouse.id.upper()}{ref_str}'

    


