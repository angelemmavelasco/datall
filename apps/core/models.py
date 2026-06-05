import uuid
from django.db.models import Q
from django.core.validators import RegexValidator
from django.db import models
from django.contrib.auth.models import Group
from django.contrib.auth.models import AbstractUser

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

    class Meta:
        verbose_name = 'Position'
        verbose_name_plural = 'Positions'
        db_table = 'positions'

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
        if not self.user_id or not self.position_id or not self.warehouse_id:
            return self.code.upper()
        else:
            return f'{self.user.first_name.title()} {self.user.last_name.title()}, {self.position.name.title()} - {self.warehouse.name.title()}'

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
    cost = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
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
    class CommissionType(models.TextChoices):
        PERCENTAGE = 'v', 'Porcentaje'
        FIXED = 'f', 'Monto Fijo'
        NONE = 'na', 'Sin comisión'

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

    commission_type = models.CharField(
        max_length=5, 
        null=True, 
        blank=True, 
        choices=CommissionType.choices, 
        default=CommissionType.NONE
    )
    commission = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True, default=0)

    notes = models.TextField(max_length=500, null=True, blank=True)

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


    class Meta:
        db_table = 'references'
        verbose_name = 'Reference'
        verbose_name_plural = 'References'
        constraints = [
            models.UniqueConstraint(
                fields=['module', 'field_context', 'key'], 
                name='unique_module_context_key_mapping'
            )
        ]
        indexes = [
            models.Index(fields=['module', 'field_context', 'key']),
        ]

    def __str__(self):
        return f'{self.module.name} [{self.field_context}] | {self.key} -> {self.reference}'

