from django.db import models
from django.db.models import Q

class Route(models.Model):
    id = models.CharField(primary_key=True, max_length=50, help_text='Identificador único de la ruta.')
    name = models.CharField(max_length=50, help_text='Nombre de la ruta. No ncesariamente relacionado con el nombre del vendedor')
    warehouse = models.ForeignKey('inventory.Warehouse', on_delete=models.PROTECT, related_name='%(app_label)s_routes', help_text='Centro de distribución asociado a la ruta')
    notes = models.TextField(null=True, blank=True, help_text='Notas sobre la ruta')
    
    class Meta:
        verbose_name = 'Ruta'
        verbose_name_plural = 'Rutas'

class RouteAssignment(models.Model):
    route = models.ForeignKey('Route', on_delete=models.PROTECT, related_name='%(app_label)s_route_assignments', help_text='Ruta asignada')
    employee = models.ForeignKey('core.Employee', on_delete=models.PROTECT, related_name='%(app_label)s_route_assignments', help_text='Colaborador asignado')
    date_start = models.DateField(help_text='Fecha de inicio de la asignación')
    date_end = models.DateField(null=True, blank=True, help_text='Fecha de fin de la asignación')
    notes = models.TextField(null=True, blank=True, help_text='Notas sobre la asignación')
    
    class Meta:
        verbose_name = 'Asignación de ruta'
        verbose_name_plural = 'Asignaciones de ruta'
        constraints = [
            # avoid duplicate assignments at the same day
            models.UniqueConstraint(
                fields=["route", "employee", "start_date"],
                name="unique_route_assignment"
            ),
            # only one active assignment (end_date NULL) per route
            models.UniqueConstraint(
                fields=["route"],
                condition=Q(end_date__isnull=True),
                name="unique_active_assignment_per_route"
            ),
        ]

class Sale(models.Model):
    class SaleStatusChoices(models.TextChoices):
        # only for quoted orders which has no stock affection
        QUOTED = 'quoted', 'cotizada'
        # when the sale completed all proccess (stock, if invoice is applicable, etc)
        COMPLETED = 'completed', 'completada'
        # an order which had not affection in the stock or was only quoted
        CANCELLED = 'cancelled', 'cancelada'

    class PaymentStatus(models.TextChoices):
        PENDING = 'pending', 'pendiente'
        PAID = 'paid', 'pagada'
        REFUNDED = 'refunded', 'reembolsada'
    
    id = models.CharField(primary_key=True, max_length=50, help_text='Identificador único de la venta. Formato serie_aaaammdd_consecutivo')
    sale_status = models.CharField(max_length=20, choices=SaleStatusChoices.choices, default=SaleStatusChoices.QUOTED, help_text='Estado de la venta')
    payment_status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID, help_text='Estado del pago de la venta')
    route = models.ForeignKey('Route', on_delete=models.PROTECT, related_name='%(app_label)s_sales', help_text='Ruta asignada a la venta')
    pass

class SaleLine(models.Model):
    pass

class SaleLineTax(models.Model):
    pass

class Quote(models.Model):
    pass

class QuoteLine(models.Model):
    pass

class QuoteLineTax(models.Model):
    pass

