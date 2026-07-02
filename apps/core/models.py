import uuid
from django.db.models import Q
from django.core.validators import RegexValidator
from django.db import models
from django.contrib.auth.models import Group, AbstractUser
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django .conf import settings

class User(AbstractUser):
    second_last_name = models.CharField(max_length=150, blank=True, null=True)
    birth_date = models.DateField(blank=True, null=True)

    gender = models.CharField(
        max_length=10,
        choices=[
            ('f', 'Femenino'),
            ('m', 'Masculino'),
            ('nb', 'No binario'),
            ('o', 'Otro')
        ],
        null=True,
        blank=True,
    )


    phone = models.CharField(
        max_length=15,
        null=True,
        blank=True,
        validators=[
            RegexValidator(
                regex=r'^\d{10,15}$',
                message='El teléfono debe contener solo números.'
            )
        ]
    )

    street = models.CharField(max_length=255, null=True, blank=True)
    street_no = models.CharField(max_length=255, null=True, blank=True)
    apt_suite = models.CharField(max_length=255, null=True, blank=True)
    city = models.CharField(max_length=255, null=True, blank=True)
    state = models.CharField(max_length=255, null=True, blank=True)
    country = models.CharField(max_length=255, null=True, blank=True)
    zipcode = models.CharField(max_length=255, null=True, blank=True)

    tax_id = models.CharField(max_length=13, null=True, blank=True)
    unique_personal_id = models.CharField(max_length=20, null=True, blank=True)

    notes = models.TextField(max_length=500, null=True, blank=True)

    photo = models.FileField(
        upload_to='users/photos',
        null=True,
        blank=True,
    )

    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.username}"

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        db_table = 'users'



class MenuSection(models.Model):
    """
    Handle module grouping on the navigation bar
    """
    name = models.CharField(max_length=50, unique=True)
    order = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ['order']
        db_table = 'menu_sections'
        
    def __str__(self):
        return self.name



class SystemModule(models.Model):
    """
    Handle each system module
    """
    section = models.ForeignKey(MenuSection, on_delete=models.CASCADE, related_name='modules')
    name = models.CharField(max_length=100)
    url_name = models.CharField(
        max_length=150, 
        help_text="Namespace:name of the URL (e.g. 'business_intelligence:sales_dashboard')"
    )
    # Connect who can see this module
    allowed_groups = models.ManyToManyField(Group, related_name='accessible_modules')
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['section__order', 'order']
        db_table = 'system_modules'

    def __str__(self):
        return f"{self.section.name} -> {self.name}"


class DataHistory(models.Model):
    class Action(models.TextChoices):
        IMPORT = 'importación', 'importación'
        EXPORT = 'exportación', 'exportación'
        CREATE = 'creación', 'creación'
        UPDATE = 'actualización', 'actualización'
        DELETE = 'eliminación', 'eliminación'
        READ = 'lectura', 'lectura'
        LOGIN = 'inicio de sesión', 'inicio de sesión'
        LOGOUT = 'cierre de sesión', 'cierre de sesión'

    class Result(models.TextChoices):
        SUCCESS = 'éxito', 'éxito'
        PARTIAL = 'parcial', 'parcial'
        ERROR = 'error', 'error'

    module = models.ForeignKey(
        SystemModule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="history_logs",
        help_text="Módulo del sistema donde se originó la acción."
    )

    content_type = models.ForeignKey(
        ContentType, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        help_text="Tabla/Modelo afectado, e.g. auth_user, sales_route."
    )
    object_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="ID del registro afectado en esa tabla."
    )
    content_object = GenericForeignKey('content_type', 'object_id')

    action = models.CharField(max_length=50, choices=Action.choices)
    result = models.CharField(max_length=50, choices=Result.choices, default=Result.SUCCESS)

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="data_history"
    )

    description = models.TextField(
        null=True,
        blank=True,
        help_text="Descripción legible para humanos."
    )

    changes = models.JSONField(
        null=True, 
        blank=True, 
        help_text="Payload JSON con el estado anterior y nuevo, o detalles del error."
    )

    metadata = models.JSONField(
        null=True, 
        blank=True, 
        help_text="Filtros de búsqueda, parámetros de URL o metadatos extra."
    )

    class Meta:
        db_table = 'data_history'
        verbose_name = 'Data History'
        verbose_name_plural = 'Data Histories'
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
        ]

    @property
    def filename(self):
        if isinstance(self.changes, dict):
            return self.changes.get('filename')
        return None

    def save(self, *args, **kwargs):
        if self.action:
            self.action = self.action.strip().lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.action} en {self.content_type} por {self.created_by}"




class Department(models.Model):
    id = models.CharField(
        max_length=3,
        primary_key=True
    )
    name = models.CharField(
        max_length=255
    )
    description = models.TextField(
        null=True,
        blank=True
    )

    class Meta:
        db_table = "departments"
        verbose_name = "Department"
        verbose_name_plural = "Departments"

    def __str__(self):
        return f"{self.id.upper()} {self.name.title()}"


class TaxSystem(models.Model):
    id = models.CharField(max_length=3, primary_key=True)
    name = models.CharField(unique=True, max_length=255)
    description = models.TextField(max_length=500, null=True, blank=True)

    class Meta:
        verbose_name = 'Tax system'
        verbose_name_plural = 'Tax systems'
        db_table = 'tax_systems'

    def __str__(self):
        return f'{self.id.upper()} {self.name.title()}'


class PayrollType(models.Model):

    id = models.CharField(
        max_length=20,
        primary_key=True
    )
    name = models.CharField(
        max_length=100,
        unique=True,
    )

    description = models.TextField(max_length=500, blank=True, null=True)

    class Meta:
        verbose_name = "Payroll type"
        verbose_name_plural = "Payroll types"
        db_table = 'payroll_types'

    def __str__(self):
        return f"{self.id.upper()} {self.name.title()}"


class Periodicity(models.Model):
    id = models.CharField(max_length=20, primary_key=True)
    name = models.CharField(max_length=255)

    class Meta:
        verbose_name = "Periodicity"
        verbose_name_plural = "Periodicities"
        ordering = ["id"]
        db_table = "periodicities"

    def __str__(self):
        return f"{self.id} - {self.name}"

class Position(models.Model):
    id = models.CharField(max_length=20, primary_key=True)
    name = models.CharField(max_length=255, unique=True)
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='positions')
    description = models.TextField(max_length=255, null=True, blank=True)

    reports_to = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='positions')

    class Meta:
        verbose_name = 'Position'
        verbose_name_plural = 'Positions'
        db_table = 'positions'

    def __str__(self):
        return f'{self.id.upper()} {self.name.title()}'





class Region(models.Model):
    id = models.CharField(max_length=5, primary_key=True)
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(max_length=500, null=True, blank=True)
    manager = models.ForeignKey(
        'Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='managed_regions'
    )

    class Meta:
        verbose_name = 'Region'
        verbose_name_plural = 'Regions'
        db_table = 'regions'

    def __str__(self):
        return f'{self.id.upper()} {self.name.title()}'
    




class Warehouse(models.Model):
    id = models.CharField(primary_key=True, max_length=20)
    name = models.CharField(max_length=255, unique=True)
    notes = models.TextField(max_length=500, null=True, blank=True)
    manager = models.ForeignKey(
        'Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='managed_warehouses'
    )

    region = models.ForeignKey(Region, on_delete=models.SET_NULL, null=True, blank=True, related_name='warehouses')

    class Meta:
        verbose_name = 'Warehouse'
        verbose_name_plural = 'Warehouses'
        db_table = 'warehouses'

    def __str__(self):
        return f'{self.id.upper()} {self.name.title()}'





class Employee(models.Model):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='employees')
    position = models.ForeignKey(Position, on_delete=models.CASCADE, null=True, blank=True, related_name='employees')
    manager = models.ForeignKey('self', on_delete=models.SET_NULL, blank=True, null=True, related_name='direct_reports')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.SET_NULL, null=True, blank=True, related_name='employees')
    hire_date = models.DateField()
    termination_date = models.DateField(null=True, blank=True)
    payroll_type = models.ForeignKey(PayrollType, on_delete=models.SET_NULL, null=True, blank=True, related_name='employees')
    payroll_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    payroll_periodicity = models.ForeignKey(Periodicity, on_delete=models.SET_NULL, null=True, blank=True, related_name='employees')
    tax_system = models.ForeignKey(TaxSystem, on_delete=models.SET_NULL, null=True, blank=True, related_name='employees')
    contract = models.FileField(upload_to='employees/contracts/', null=True, blank=True)

    class Meta:
        verbose_name = 'Employee'
        verbose_name_plural = 'Employees'
        db_table = 'employees'

    def __str__(self):
        if not self.position or not self.warehouse:
            return f'{self.user.first_name.title()} {self.user.last_name.title()}, {str(self.id)[:7]}'
        else:
            return f'{self.user.first_name.title()} {self.user.last_name.title()}, {self.position.name.title()}: {self.warehouse.name.title()}'

    def get_reporting_tree_ids(self):

        """
        Returns a flatten list with this employee Id and all the employees that report to this employee directly or indirectly.
        """

        #intital list with the self id, in case this employee has no direct reports, they ould be the only one.
        tree_ids = [self.id]

        #get direct reports
        direct_reports = Employee.objects.filter(manager=self)

        for report in direct_reports:
            #recursive call to get the reporting tree of the direct report
            tree_ids.extend(report.get_reporting_tree_ids())

        return list(set(tree_ids))















# Products module

class ProductCategory(models.Model):
    id = models.CharField(max_length=50, primary_key=True)
    name = models.CharField(max_length=255, null=True, blank=True)
    description = models.TextField(max_length=500, default='', blank=True)

    class Meta:
        verbose_name = 'Product category'
        verbose_name_plural = 'Product categories'
        db_table = 'product_categories'

    def __str__(self):
        name = (self.name or "").title()
        return f'{self.id.upper()} {name}'

class ProductClass(models.Model):
    id = models.CharField(primary_key=True, max_length=50)
    name = models.CharField(max_length=255, null=True, blank=True)
    product_category = models.ForeignKey(ProductCategory, on_delete=models.PROTECT, related_name='product_classes', null=True, blank=True)

    class Meta:
        verbose_name = 'Product class'
        verbose_name_plural = 'Product classes'
        db_table = 'product_classes'

    def save(self, *args, **kwargs):
        if self.name:
            self.name = self.name.strip().lower()

        super().save(*args, **kwargs)

    def __str__(self):
        name = (self.name or "").title()
        return f'{self.id.upper()} {name}'

class Product(models.Model):
    id = models.CharField(primary_key=True, max_length=255)
    barcode = models.CharField(blank=True, null=True, max_length=255)
    name = models.CharField(max_length=255, null=True, blank=True)
    product_class = models.ForeignKey(ProductClass, on_delete=models.PROTECT, related_name='products', null=True, blank=True)
    cost = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    unit_of_measure = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        verbose_name = 'Product'
        verbose_name_plural = 'Products'
        db_table = 'products'

    def __str__(self):
        name = (self.name or "").title()
        return f'{self.id.upper()} {name}'




class RouteType(models.Model):
    id = models.CharField(max_length=50, primary_key=True)
    name = models.CharField(max_length=255)
    description = models.TextField(max_length=500, null=True, blank=True)

    class Meta:
        db_table = "route_types"
        verbose_name = "Route type"
        verbose_name_plural = "Route types"

    def __str__(self):
        name = (self.name or '').title()
        return f"{self.id.upper()} {name}"


class SaleChannel(models.Model):
    id = models.CharField(max_length=50, primary_key=True)
    name = models.CharField(max_length=255)
    description = models.TextField(max_length=500, null=True, blank=True)

    class Meta:
        db_table = "sale_channels"
        verbose_name = "Sale channel"
        verbose_name_plural = "Sale channels"

    def __str__(self):
        name = (self.name or '').title()
        return f"{self.id.upper()} {name}"


class Route(models.Model):

    id = models.CharField(primary_key=True, max_length=255)
    name = models.CharField(max_length=255, null=True, blank=True)

    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.SET_NULL,
        related_name="routes",
        null=True,
        blank=True
    )

    sale_channel = models.ForeignKey(
        SaleChannel,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="routes"
    )
    route_type = models.ForeignKey(
        "RouteType",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="routes"
    )

    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "routes"
        verbose_name = "Route"
        verbose_name_plural = "Routes"

    def __str__(self):
        name = (self.name or '').title()
        return f"{self.id.upper()} {name}"


class RouteAssignment(models.Model):
    route = models.ForeignKey(
        Route,
        on_delete=models.CASCADE,
        related_name="assignments"
    )
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="route_assignments",
        blank=True,
        null=True
    )

    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)

    notes = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "route_assignments"
        verbose_name = "Route assignment"
        verbose_name_plural = "Route assignments"
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

    def __str__(self):
        route = self.route.id
        
        if self.employee and self.employee.user:
            # Asumiendo que Employee tiene ForeignKey a User
            name = f"{self.employee.user.first_name.title()} {self.employee.user.last_name.title()}"
        else:
            name = "Sin colaborador asignado"

        return f"Ruta {route}, {name}"











# clientes

class CustomerType(models.Model):
    id = models.CharField(
        max_length=100, 
        primary_key=True
    )
    
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'customer_types'
        verbose_name = 'Customer type'
        verbose_name_plural = 'Customer types'

    def __str__(self):
        return f"{self.id} - {self.name}"

class Customer(models.Model):
    id = models.CharField(
        max_length=100, 
        primary_key=True,
    )
    
    name = models.CharField(
        max_length=255
    )
    
    registration_date = models.DateField()
    

    credit_limit = models.DecimalField(
        max_digits=18, 
        decimal_places=2, 
        default=Decimal('0.00'),
    )
    
    credit_days = models.IntegerField(
        default=0,
    )
    
    customer_type = models.ForeignKey(
        'CustomerType',
        on_delete=models.PROTECT,
        related_name='customers',
    )
    
    opinion_leader = models.BooleanField(default=False)
    
    route = models.ForeignKey(
        'Route',
        on_delete=models.PROTECT,
        related_name='customers',
        blank=True,
        null=True,
    )

    class Meta:
        db_table = 'customers'
        verbose_name = 'Customer'
        verbose_name_plural = 'Customers'
        indexes = [
            models.Index(fields=["registration_date"]),
            models.Index(fields=["route", "customer_type"]),
        ]

    def __str__(self):
        return f"{self.id}: {self.name.strip().title()}"



class AccountsReceivable(models.Model):
    #cve_cte
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name='accounts_receivable'
    )
    #cve_age
    route = models.ForeignKey(
        'Route',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='accounts_receivables'
    )
    #falta_fac
    issue_date = models.DateField(null=True)
    #f_pago
    due_date = models.DateField(null=True)
    #subtotal total
    total_balance = models.DecimalField(max_digits=18, decimal_places=4, default=0, blank=True, null=True)
    #concepto
    description = models.CharField(max_length=255, null=True, blank=True)
    #odc_id
    doc_id = models.CharField(max_length=255, null=True, blank=True)
    #rango1
    balance_15 = models.DecimalField(max_digits=18, decimal_places=4, default=0, blank=True, null=True)
    #rango2
    balance_30 = models.DecimalField(max_digits=18, decimal_places=4, default=0, blank=True, null=True)
    #rango3
    balance_60 = models.DecimalField(max_digits=18, decimal_places=4, default=0, blank=True, null=True)
    #rango4 +60
    past_due = models.DecimalField(max_digits=18, decimal_places=4, default=0, blank=True, null=True)
    #rangoc al corriente
    current_balance = models.DecimalField(max_digits=18, decimal_places=4, default=0, blank=True, null=True)


    

    class Meta:
        db_table = 'accounts_receivables'
        verbose_name = 'Accounts receivable'
        verbose_name_plural = 'Accounts receivables'

    def __str__(self):
        return f'{self.customer_id}: total balance $ {self.total_balance}'
    


# transactions and targets

class SaleTransaction(models.Model):
    doc_id = models.CharField(
        max_length=255
    )

    sale_date = models.DateField()

    cost = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    net_amount = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    gross_amount= models.DecimalField(max_digits=18, decimal_places=6, default=0)
    profit= models.DecimalField(max_digits=18, decimal_places=6, default=0)
    quantity = models.DecimalField(max_digits=18, decimal_places=4, default=0)


    product_class = models.ForeignKey(
        ProductClass,
        on_delete=models.PROTECT,
        related_name="sale_transactions"
    )


    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="sale_transactions",
        blank=True,
        null=True
    )


    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name="sale_transactions"
    )

    route = models.ForeignKey(
        Route,
        on_delete=models.PROTECT,
        related_name="sale_transactions",
        blank=True,
        null=True
    )
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name="sale_transactions",
        blank=True,
        null=True
    )

    class Meta:
        db_table = "sale_transactions"
        verbose_name = "Sale transaction"
        verbose_name_plural = "Sale transactions"
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
            f"Prod: {self.product_id} x {self.quantity} | "
            f"Cedis: {self.warehouse_id} | Ruta: {self.route_id}"
        )


class SaleTarget(models.Model):
    period = models.DateField()
    route = models.ForeignKey(Route, on_delete=models.PROTECT, related_name='sale_targets')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='sale_targets')
    product_class = models.ForeignKey(ProductClass, on_delete=models.PROTECT, related_name='sale_targets')
    target_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal('0.00'))
    is_valid_for_comission = models.BooleanField(default=True)

    class Meta:
        db_table = 'sale_targets'
        verbose_name = 'Sale target'
        verbose_name_plural = 'Sale targets'
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




#commissions

class CommissionProfile(models.Model):
    """
    Commission profiles are the base that define the rules that are gonna 
    be applied in the calculation of the commissions.
    This is a generalization of the commission system, so that we can have
    different commission systems for different profiles.
    """
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'commission_profiles'
        verbose_name = 'Commission profile'
        verbose_name_plural = 'Commission profiles'
    
    def __str__(self):
        return self.name.strip().title()
        
class CommissionTier(models.Model):
    """
    Tier-based commission rules. This works as a range of values. For example, if the global rach is 90% and above, 
    and the profile dont require min lines to complete, then, the multplier is gonne be applied on the potential bonus previously calculated.
    
    """
    commission_profile = models.ForeignKey(CommissionProfile, on_delete=models.CASCADE, related_name='commission_tiers')

    min_global_scope_pct = models.DecimalField(max_digits=5, decimal_places=2) #set from 0 to 100 +
    min_completed_classes = models.IntegerField(default=0) #set as integer
    bonus_multiplier_pct = models.DecimalField(max_digits=5, decimal_places=2)
    extra_flat_bonus = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        ordering = ['-min_global_scope_pct', '-min_completed_classes']
        db_table = 'commission_tiers'
        verbose_name = 'Commission tier'
        verbose_name_plural = 'Commission tiers'

    def __str__(self):
        return f'{self.commission_profile.name}\nAlcance global: {self.min_global_scope_pct} %\nLíneas requeridas: {self.min_completed_classes}\nMultiplicador: {self.bonus_multiplier_pct}%\nBono extra (si aplica): {self.extra_flat_bonus}'
    
    
class RouteCommissionSetup(models.Model):
    """
    Register the commission setup for a specific route in a specific period.
    """ 
    route = models.ForeignKey('Route', on_delete=models.CASCADE, related_name='commission_history')
    profile = models.ForeignKey(CommissionProfile, on_delete=models.PROTECT)

    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)


    BONUS_CHOICES = (('f', 'fijo'), ('v', 'variable'))

    bonus_type = models.CharField(max_length=10, choices=BONUS_CHOICES, default='v')
    base_bonus_amount = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f'{self.route} | {self.profile} | {self.start_date} - {self.end_date}'

    class Meta:
        db_table = 'route_commission_setup'
        verbose_name = 'Route commission setup'
        verbose_name_plural = 'Route commission setups'


class RouteCommissionException(models.Model):
    """
    Register the commission exception for a specific route in a specific period. For example, during a period
    the route will receive an extra percentage of the global target scope. This is applicable for incoming employees
    """

    route = models.ForeignKey('Route', on_delete=models.CASCADE, related_name='commission_exceptions')
    
    start_date = models.DateField()
    end_date = models.DateField()

    scope_tolerance_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    guaranteed_flat_bonus = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    notes = models.CharField(max_length=255)

    def __str__(self):
        return f'{self.route} | tolerancia pct: {self.scope_tolerance_pct} % | monto garantizado: $ {self.guaranteed_flat_bonus} | desde {self.start_date} hasta {self.end_date}'
    
    class Meta:
        db_table = 'route_commission_exception'
        verbose_name = 'Route commission exception'
        verbose_name_plural = 'Route commission exceptions'


class CommissionSettlement(models.Model):

    """
    This table store the final commission amounts. It can be modified and recalculated only 
    through the admin site or if the status is draft.
    """

    STATUS_CHOICES = (('draft', 'borrador'), ('closed', 'cerrado'))

    period_start = models.DateField()
    period_end = models.DateField()

    route = models.ForeignKey('Route', on_delete=models.PROTECT)
    employee = models.ForeignKey('Employee', on_delete=models.PROTECT)

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
    calculated_at = models.DateTimeField(auto_now=True)

    snapshot_profile_name = models.CharField(max_length=100)
    snapshot_net_sales = models.DecimalField(max_digits=18, decimal_places=2)
    snapshot_target = models.DecimalField(max_digits=18, decimal_places=2)
    snapshot_global_scope = models.DecimalField(max_digits=8, decimal_places=2)
    snapshot_completed_classes = models.IntegerField()
    snapshot_base_bonus = models.DecimalField(max_digits=12, decimal_places=2)

    final_calculated_bonus = models.DecimalField(max_digits=12, decimal_places=2)

    #this field is only for manual adjustments made by the admin when the status is closed and there are unexpected results.
    manual_adjustment = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        return f'{self.employee.user} | {self.route} | {self.period_start} - {self.period_end} | monto: ${self.final_calculated_bonus}'

    class Meta:
        db_table = 'commission_settlement'
        verbose_name = 'Commission settlement'
        verbose_name_plural = 'Commission settlements'
        ordering = ['-period_start']
    









    
    














class Reference(models.Model):

    #which is the module where this reference is gonna be used
    module = models.ForeignKey(SystemModule, on_delete=models.CASCADE, related_name='references')

    #
    field_context = models.CharField(
        max_length=100, 
    )

    #this is the raw value
    key = models.CharField(max_length=255)

    #value which is gonna be stored and accepted by the database
    reference = models.CharField(max_length=255)

    content_type = models.ForeignKey(
        ContentType, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        help_text="Tabla/Modelo afectado, e.g. auth_user, sales_route."
    )


    class Meta:
        db_table = 'references'
        verbose_name = 'Reference'
        verbose_name_plural = 'References'
        constraints = [
            models.UniqueConstraint(
                fields=['module', 'field_context', 'key', 'content_type'], 
                name='unique_module_context_key_mapping'
            )
        ]
        indexes = [
            models.Index(fields=['module', 'field_context', 'key']),
        ]

    def __str__(self):
        return f'{self.module.name} [{self.field_context}] | {self.key} -> {self.reference}'

