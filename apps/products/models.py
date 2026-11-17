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
    barcode = models.CharField(blank=True, default='', max_length=255, help_text='Código de barras del producto')
    name = models.CharField(max_length=255, default='', blank=True, help_text='Nombre del producto')
    product_class = models.ForeignKey('ProductClass', on_delete=models.PROTECT, related_name='products', null=True, blank=True, help_text='Clase del producto')
    cost = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal('0.00'), blank=True, help_text='Costo del producto')
    price = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), blank=True, help_text='Precio del producto')
    unit_of_measure = models.CharField(max_length=255, default='', blank=True, help_text='Unidad de medida del producto')
    weight = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal('0.0000'), blank=True, help_text='Peso unitario del producto en libras')
    pieces_per_box = models.PositiveIntegerField(default=1, blank=True, help_text='Piezas individuales por caja o bulto')
    boxes_per_pallet = models.PositiveIntegerField(default=1, blank=True, help_text='Cajas o bultos por tarima')
    is_active = models.BooleanField(default=True, help_text='Indica si el producto está activo')
    properties = models.ManyToManyField('ProductProperty',through='ProductPropertyValue',related_name='products',blank=True,help_text='Propiedades del producto')

    class Meta:
        verbose_name = 'Producto'
        verbose_name_plural = 'Productos'

    @property
    def units_per_pallet(self) -> int:
        pieces = self.pieces_per_box or 1
        boxes = self.boxes_per_pallet or 1
        return pieces * boxes

    @property
    def box_weight(self) -> Decimal:
        pieces = Decimal(self.pieces_per_box or 1)
        return (self.weight or Decimal('0.0000')) * pieces

    @property
    def pallet_weight(self) -> Decimal:
        return (self.weight or Decimal('0.0000')) * Decimal(self.units_per_pallet)

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


class PurchaseOrder(models.Model):
    class StatusChoices(models.TextChoices):
        REALIZADA = 'realizada', 'Realizada'
        CONFIRMADA = 'confirmada', 'Confirmada'
        EN_TRANSITO = 'en_transito', 'En tránsito'
        COMPLETADA = 'completada', 'Completada'

    class OriginChoices(models.TextChoices):
        IMPORTACION = 'importacion', 'Importación'
        LOCAL = 'local', 'Local'

    class GroupingModeChoices(models.TextChoices):
        ACCUMULATED = 'acumulado', 'Acumulado'
        SEPARATED = 'separado', 'Separado por CEDIS'

    folio = models.CharField(max_length=50, unique=True, help_text='Folio o identificador de la orden de compra')
    origin_type = models.CharField(max_length=20, choices=OriginChoices.choices, default=OriginChoices.IMPORTACION, help_text='Origen de la orden')
    status = models.CharField(max_length=20, choices=StatusChoices.choices, default=StatusChoices.REALIZADA, help_text='Estatus actual de la orden')
    grouping_mode = models.CharField(max_length=20, choices=GroupingModeChoices.choices, default=GroupingModeChoices.SEPARATED, help_text='Modo de agrupación de centros de distribución')
    warehouses = models.ManyToManyField('sales.Warehouse', related_name='purchase_orders', blank=True, help_text='Centros de distribución contemplados')
    evaluation_start_date = models.DateField(null=True, blank=True, help_text='Fecha de inicio del periodo evaluado')
    evaluation_end_date = models.DateField(null=True, blank=True, help_text='Fecha de fin del periodo evaluado')
    coverage_months = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('1.00'), help_text='Meses de cobertura objetivo')
    total_requested_units = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), help_text='Total de unidades requeridas antes de redondeo a tarima')
    total_ordered_units = models.PositiveIntegerField(default=0, help_text='Total de unidades finales ajustadas a múltiplos de tarima')
    total_boxes = models.PositiveIntegerField(default=0, help_text='Total de cajas o bultos ordenados')
    total_pallets = models.PositiveIntegerField(default=0, help_text='Total de tarimas ordenadas')
    total_product_weight = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), help_text='Peso neto total de producto en libras')
    total_pallet_weight = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), help_text='Peso total incluyendo madera de tarimas en libras')
    notes = models.TextField(max_length=1000, default='', blank=True, help_text='Notas u observaciones de la orden')
    created_by = models.ForeignKey('core.User', on_delete=models.PROTECT, related_name='created_purchase_orders', null=True, blank=True, help_text='Usuario que generó la orden')
    confirmed_at = models.DateTimeField(null=True, blank=True, help_text='Fecha de confirmación de la orden')
    in_transit_at = models.DateTimeField(null=True, blank=True, help_text='Fecha de puesta en tránsito')
    completed_at = models.DateTimeField(null=True, blank=True, help_text='Fecha de recepción o completado')
    created_at = models.DateTimeField(auto_now_add=True, help_text='Fecha de creación')
    updated_at = models.DateTimeField(auto_now=True, help_text='Fecha de última actualización')

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = 'Orden de compra'
        verbose_name_plural = 'Órdenes de compra'
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['origin_type', '-created_at']),
            models.Index(fields=['folio']),
        ]

    @property
    def is_pending(self) -> bool:
        return self.status in {
            self.StatusChoices.REALIZADA,
            self.StatusChoices.CONFIRMADA,
            self.StatusChoices.EN_TRANSITO,
        }

    def __str__(self):
        return f'{self.folio.upper()} ({self.get_status_display()})'


class PurchaseOrderItem(models.Model):
    purchase_order = models.ForeignKey('PurchaseOrder', on_delete=models.CASCADE, related_name='items', help_text='Orden de compra asociada')
    product = models.ForeignKey('Product', on_delete=models.PROTECT, related_name='purchase_order_items', help_text='Producto ordenado')
    sold_qty = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), help_text='Unidades vendidas en el periodo evaluado')
    avg_monthly = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), help_text='Promedio mensual de ventas')
    current_stock = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), help_text='Existencia física total al momento de la orden')
    in_transit_stock = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), help_text='Existencia en tránsito al momento de la orden')
    coverage_months = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('1.00'), help_text='Meses de cobertura solicitados para el producto')
    suggested_units = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), help_text='Unidades sugeridas por la fórmula de cobertura')
    requested_units = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), help_text='Unidades capturadas antes del ajuste a múltiplo de tarima')
    pieces_per_box = models.PositiveIntegerField(default=1, help_text='Piezas por caja vigente al crear la orden')
    boxes_per_pallet = models.PositiveIntegerField(default=1, help_text='Cajas por tarima vigente al crear la orden')
    units_per_pallet = models.PositiveIntegerField(default=1, help_text='Múltiplo total de piezas por tarima vigente al crear la orden')
    pallets_ordered = models.PositiveIntegerField(default=0, help_text='Cantidad de tarimas cerradas a pedir')
    boxes_ordered = models.PositiveIntegerField(default=0, help_text='Cantidad de cajas o bultos equivalentes')
    ordered_units = models.PositiveIntegerField(default=0, help_text='Unidades finales ordenadas en múltiplo de tarima')
    unit_weight = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal('0.0000'), help_text='Peso unitario en libras')
    total_weight = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), help_text='Peso total del producto en libras')
    warehouse_breakdown = models.JSONField(default=dict, blank=True, help_text='Desglose informativo de unidades capturadas por CEDIS')

    class Meta:
        ordering = ['product__name', 'product__id']
        verbose_name = 'Partida de orden de compra'
        verbose_name_plural = 'Partidas de orden de compra'
        constraints = [
            models.UniqueConstraint(
                fields=['purchase_order', 'product'],
                name='unique_purchase_order_product'
            )
        ]

    def __str__(self):
        return f'{self.purchase_order.folio.upper()} -> {self.product.id.upper()}: {self.ordered_units} uds ({self.pallets_ordered} tarimas)'