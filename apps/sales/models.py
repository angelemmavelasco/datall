from django.db import models
from django.db.models import Q
from decimal import Decimal

class RouteType(models.Model):
    id = models.CharField(max_length=50, primary_key=True, help_text='Identificador único del tipo de ruta')
    name = models.CharField(max_length=255, help_text='Nombre del tipo de ruta')
    description = models.TextField(max_length=500, null=True, blank=True, help_text='Descripción del tipo de ruta')

    class Meta:
        verbose_name = "Tipo de ruta"
        verbose_name_plural = "Tipos de ruta"

class SaleChannel(models.Model):
    id = models.CharField(max_length=50, primary_key=True, help_text='Identificador único del canal de venta')
    name = models.CharField(max_length=255, help_text='Nombre del canal de venta')
    description = models.TextField(max_length=500, null=True, blank=True, help_text='Descripción del canal de venta')

    class Meta:
        verbose_name = "Canal de venta"
        verbose_name_plural = "Canales de venta"

class Route(models.Model):
    id = models.CharField(primary_key=True, max_length=50, help_text='Identificador único de la ruta.')
    name = models.CharField(max_length=50, help_text='Nombre de la ruta. No necesariamente relacionado con el nombre del vendedor')
    warehouse = models.ForeignKey('inventory.Warehouse', on_delete=models.PROTECT, related_name='%(app_label)s_routes', help_text='Centro de distribución asociado a la ruta')
    route_type = models.ForeignKey('RouteType', on_delete=models.PROTECT, related_name='%(app_label)s_routes', help_text='Tipo de ruta')
    sale_channel = models.ForeignKey('SaleChannel', on_delete=models.PROTECT, related_name='%(app_label)s_routes', help_text='Canal de venta asociado a la ruta')
    notes = models.TextField(null=True, blank=True, help_text='Notas sobre la ruta')
    
    class Meta:
        verbose_name = 'Ruta'
        verbose_name_plural = 'Rutas'

class RouteAssignment(models.Model):
    route = models.ForeignKey('Route', on_delete=models.PROTECT, related_name='%(app_label)s_route_assignments', help_text='Ruta asignada')
    employee = models.ForeignKey('human_resources.Employee', on_delete=models.PROTECT, related_name='%(app_label)s_route_assignments', help_text='Colaborador asignado')
    date_start = models.DateField(help_text='Fecha de inicio de la asignación')
    date_end = models.DateField(null=True, blank=True, help_text='Fecha de fin de la asignación')
    notes = models.TextField(null=True, blank=True, help_text='Notas sobre la asignación')
    
    class Meta:
        verbose_name = 'Asignación de ruta'
        verbose_name_plural = 'Asignaciones de ruta'
        constraints = [
            models.UniqueConstraint(
                fields=["route", "employee", "date_start"],
                name="sales_unique_route_assignment"
            ),
            models.UniqueConstraint(
                fields=["route"],
                condition=Q(date_end__isnull=True),
                name="sales_unique_active_assignment_per_route"
            ),
        ]

class Sale(models.Model):
    class SaleStatusChoices(models.TextChoices):
        QUOTED = 'quoted', 'cotizada'
        COMPLETED = 'completed', 'completada'
        CANCELLED = 'cancelled', 'cancelada'

    class PaymentStatus(models.TextChoices):
        PENDING = 'pending', 'pendiente'
        PAID = 'paid', 'pagada'
        REFUNDED = 'refunded', 'reembolsada'
    
    id = models.CharField(primary_key=True, max_length=50, help_text='Identificador único de la venta. Formato serie_aaaammdd_consecutivo')
    sale_status = models.CharField(max_length=20, choices=SaleStatusChoices.choices, default=SaleStatusChoices.QUOTED, help_text='Estado de la venta')
    payment_status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING, help_text='Estado del pago de la venta')
    route = models.ForeignKey('Route', on_delete=models.PROTECT, related_name='%(app_label)s_sales', help_text='Ruta asignada a la venta')
    customer = models.ForeignKey('customers.Customer', on_delete=models.PROTECT, related_name='%(app_label)s_sales', help_text='Cliente asociado a la venta')
    sale_date = models.DateTimeField(help_text='Fecha y hora de la venta')
    subtotal = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal('0.00'), help_text='Subtotal de la venta (Monto sin considerar impuestos ni descuentos)')
    discount = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal('0.00'), help_text='Descuento de la venta (aplicado al subtotal)')
    total_tax = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal('0.00'), help_text='Total de impuestos de la venta (aplicado al subtotal)')
    total = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal('0.00'), help_text='Total de la venta (Subtotal - Descuento + Total de impuestos)')
    notes = models.TextField(null=True, blank=True, help_text='Notas generales o comentarios')
    
    class Meta:
        verbose_name = 'Venta'
        verbose_name_plural = 'Ventas'
        indexes = [
            models.Index(fields=["sale_date"]),
            models.Index(fields=["sale_status"]),
            models.Index(fields=["payment_status"]),
            models.Index(fields=["route"]),
            models.Index(fields=["customer"]),
        ]

class SaleLine(models.Model):
    sale = models.ForeignKey('Sale', on_delete=models.CASCADE, related_name='%(app_label)s_lines', help_text='Venta asociada a la línea')
    variant = models.ForeignKey('inventory.ProductVariant', on_delete=models.PROTECT, related_name='%(app_label)s_sale_lines', help_text='Variante del producto vendido')
    quantity = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal('1.00'), help_text='Cantidad vendida')
    unit_price = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal('0.00'), help_text='Precio unitario del producto')
    unit_cost = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal('0.00'), help_text='Costo unitario del producto')
    subtotal = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal('0.00'), help_text='Subtotal de la línea (Monto sin considerar impuestos ni descuentos)')
    discount = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal('0.00'), help_text='Descuento de la línea (aplicado al subtotal)')
    total_tax = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal('0.00'), help_text='Total de impuestos de la línea (aplicado al subtotal)')
    total = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal('0.00'), help_text='Total de la línea (Subtotal - Descuento + Total de impuestos)')
    
    class Meta:
        verbose_name = 'Línea de venta'
        verbose_name_plural = 'Líneas de venta'
        indexes = [
            models.Index(fields=["sale"]),
            models.Index(fields=["variant"]),
        ]

class SaleLineTax(models.Model):
    class TaxType(models.TextChoices):
        IVA = "IVA", "IVA"
        ISR = "ISR", "ISR"
        IEPS = "IEPS", "IEPS"

    class TaxFactorType(models.TextChoices):
        TASA = "Tasa", "Tasa"
        CUOTA = "Cuota", "Cuota"
        EXENTO = "Exento", "Exento"
    
    sale_line = models.ForeignKey('SaleLine', on_delete=models.CASCADE, related_name='%(app_label)s_taxes', help_text='Línea de venta asociada al impuesto')
    tax_type = models.CharField(max_length=20, choices=TaxType.choices, default=TaxType.IVA, help_text='Tipo de impuesto')
    tax_factor_type = models.CharField(max_length=20, choices=TaxFactorType.choices, default=TaxFactorType.TASA, help_text='Tipo de factor de impuesto')
    rate = models.DecimalField(max_digits=10, decimal_places=6, default=Decimal('0.00'), help_text='Tasa o cuota del impuesto. Ej: 0.16 para 16%')
    base = models.DecimalField(max_digits=18, decimal_places=6, help_text='Base gravable')
    amount = models.DecimalField(max_digits=18, decimal_places=6, help_text='Monto del impuesto')
    class Meta:
        verbose_name = 'Impuesto de línea de venta'
        verbose_name_plural = 'Impuestos de líneas de venta'
        indexes = [
            models.Index(fields=["sale_line"]),
            models.Index(fields=["tax_type"]),
        ]