from django.db import models
from django.db.models import Q
from decimal import Decimal

class Warehouse(models.Model):
    class WarehouseTypeChoices(models.TextChoices):
        WAREHOUSE = 'warehouse', 'almacén'
        RETAIL = 'retail', 'tienda'
        TRANSFER = 'transfer', 'traspaso'
        DAMAGED = 'damaged', 'dañado/merma'
        
    id = models.CharField(primary_key=True, max_length=50, help_text='Identificador del centro de distribución')
    name = models.CharField(max_length=50, unique=True, help_text='Nombre del centro de distribución')
    warehouse_type = models.CharField(max_length=20, choices=WarehouseTypeChoices.choices, default=WarehouseTypeChoices.WAREHOUSE, help_text='Tipo de centro de distribución')

    class Meta:
        verbose_name = 'Centro de distribución'
        verbose_name_plural = 'Centros de distribución'

    def __str__(self):
        return f'{self.id.upper()} {self.name.title()} - {self.get_warehouse_type_display().title()}'

class RouteType(models.Model):
    id = models.CharField(max_length=50, primary_key=True, help_text='Identificador del tipo de ruta')
    name = models.CharField(max_length=255, help_text='Nombre del tipo de ruta')
    description = models.TextField(max_length=500, null=True, blank=True, help_text='Descripción del tipo de ruta')

    class Meta:
        verbose_name = "Tipo de ruta"
        verbose_name_plural = "Tipos de ruta"

    def __str__(self):
        return f'{self.id.upper()} {self.name.title()}'

class SaleChannel(models.Model):
    id = models.CharField(max_length=50, primary_key=True, help_text='Identificador único del canal de venta')
    name = models.CharField(max_length=255, help_text='Nombre del canal de venta')
    description = models.TextField(max_length=500, null=True, blank=True, help_text='Descripción del canal de venta')

    class Meta:
        verbose_name = "Canal de venta"
        verbose_name_plural = "Canales de venta"

    def __str__(self):
        return f'{self.id.upper()} {self.name.title()}'

class Route(models.Model):
    id = models.CharField(primary_key=True, max_length=50, help_text='Identificador de la ruta.')
    name = models.CharField(max_length=50, help_text='Nombre de la ruta. No necesariamente relacionado con el nombre del vendedor')
    business_unit = models.ForeignKey('human_resources.BusinessUnit',null=True, blank=True, on_delete=models.PROTECT, related_name='routes', help_text='Unidad de negocio a la que pertenece la ruta. No necesariamente asociada a la unidad de negocio del colaborador que opera la ruta.')
    route_type = models.ForeignKey('RouteType', on_delete=models.PROTECT, related_name='routes', help_text='Tipo de ruta')
    sale_channel = models.ForeignKey('SaleChannel', on_delete=models.PROTECT, related_name='routes', help_text='Canal de venta asociado a la ruta')
    notes = models.TextField(null=True, blank=True, help_text='Notas sobre la ruta')
    is_active = models.BooleanField(default=False, help_text="Indica si la ruta es apta para asignación a un colaborador o esta operando")
    
    class Meta:
        verbose_name = 'Ruta'
        verbose_name_plural = 'Rutas'

    def __str__(self):
        unit_name = self.business_unit.name.title() if self.business_unit else ""
        return f'{self.id.upper()} {self.name.title()}. Gerencia: {unit_name}'

class RouteAssignment(models.Model):
    route = models.ForeignKey('Route', on_delete=models.PROTECT, related_name='route_assignments', help_text='Ruta asignada')
    employee = models.ForeignKey('human_resources.Employee', on_delete=models.PROTECT, related_name='route_assignments', help_text='Colaborador asignado')
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

    def __str__(self):
        return f'{self.route.id.upper()} {self.route.name.title()} -> {self.employee.user.first_name.title()} {self.employee.user.last_name.title()}'

class UserRouteAccess(models.Model):
    user = models.ForeignKey('core.User', on_delete=models.CASCADE, help_text='Usuario que tiene acceso a la ruta')
    route = models.ForeignKey('Route', on_delete=models.CASCADE, help_text='Ruta a la que el usuario tiene acceso')
    can_view = models.BooleanField(default=True, help_text='Indica si el usuario puede ver la ruta y su información relacionada')
    can_edit = models.BooleanField(default=False, help_text='Indica si el usuario puede editar la ruta y su información relacionada')
    notes = models.TextField(null=True, blank=True, help_text='Notas sobre el acceso del usuario a la ruta')

    class Meta:
        verbose_name = 'Acceso de usuario a ruta'
        verbose_name_plural = 'Accesos de usuarios a rutas'
        constraints = [
            models.UniqueConstraint(
                fields=["user", "route"],
                name="sales_unique_user_route_access"
            ),
        ]

    def __str__(self):
        return f'{self.user.first_name.title()} {self.user.last_name.title()} -> {self.route.id.upper()} {self.route.name.title()}'

class SaleTransaction(models.Model):
    doc_id = models.CharField(max_length=255, default='')
    sale_date = models.DateField()
    cost = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal('0.00'))
    net_amount = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal('0.00'))
    gross_amount= models.DecimalField(max_digits=18, decimal_places=6, default=Decimal('0.00'))
    profit= models.DecimalField(max_digits=18, decimal_places=6, default=Decimal('0.00'))
    quantity = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal('0.0000'))
    customer = models.ForeignKey('customers.Customer',on_delete=models.PROTECT,related_name="sale_transactions")
    route = models.ForeignKey('Route',on_delete=models.PROTECT,related_name="sale_transactions",blank=True,null=True)
    warehouse = models.ForeignKey('Warehouse',on_delete=models.PROTECT,related_name="sale_transactions",blank=True,null=True)
    product_class = models.ForeignKey('products.ProductClass',on_delete=models.PROTECT,related_name="sale_transactions")
    product = models.ForeignKey('products.Product', on_delete=models.PROTECT,related_name="sale_transactions",blank=True,null=True)

    class Meta:
        verbose_name = "Transacción de venta"
        verbose_name_plural = "Transacciones de venta"
        indexes = [
            models.Index(fields=["sale_date"]),
            models.Index(fields=["doc_id"]),
            models.Index(fields=["route", "sale_date"]),
            models.Index(fields=["customer", "sale_date"]),
        ]


    def __str__(self):
        if not self.quantity:
            return f"{self.doc_id.upper()} {self.sale_date}"
        
        return (
            f"{self.doc_id.upper()} ({self.sale_date}) | "
            f"Prd: {self.product_id} x {self.quantity} | "
            f"Cedis: {self.warehouse_id} | Ruta: {self.route_id}"
        )

    @property
    def margin(self) -> Decimal:
        """
        calculates margin percentage.
        """
        if self.net_amount and self.net_amount > 0:
            return (self.profit / self.net_amount) * Decimal('100.00')
        return Decimal('0.00')


class SaleTarget(models.Model):
    period = models.DateField()
    route = models.ForeignKey('Route', on_delete=models.PROTECT, related_name='sale_targets', help_text='Ruta del objetivo')
    business_unit = models.ForeignKey('human_resources.BusinessUnit', on_delete=models.PROTECT, null=True, blank=True, related_name='sale_targets', help_text='Unidad de negocio del objetivo')
    product_class = models.ForeignKey('products.ProductClass', on_delete=models.PROTECT, related_name='sale_targets', help_text='Clase de producto del objetivo')
    target_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal('0.00'), help_text='Monto objetivo')
    is_valid_for_comission = models.BooleanField(default=True, help_text='Indica si el objetivo es válido para comisiones')

    class Meta:
        verbose_name = 'Objetivo de venta'
        verbose_name_plural = 'Objetivos de venta'
        constraints = [
            models.UniqueConstraint(
                fields=["period", "route", "product_class"],
                name="unique_sale_target_per_period_route_class"
            )
        ]

    def __str__(self):
        route = self.route_id
        cls_name = (self.product_class_id or "").title()
        return f'Ruta {route}, clase {cls_name}, periodo {self.period:%b %Y}'
