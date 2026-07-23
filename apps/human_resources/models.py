import uuid
from django.db import models


class Department(models.Model):
    id = models.CharField(max_length=3, primary_key=True)
    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)

    class Meta:
        verbose_name = "Departamento"
        verbose_name_plural = "Departamentos"

    def __str__(self):
        return f"{self.id.upper()} {self.name.title()}"

class PayrollType(models.Model):
    id = models.CharField(max_length=20, primary_key=True)
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(max_length=500, blank=True, null=True)

    class Meta:
        verbose_name = "Tipo de compensación"
        verbose_name_plural = "Tipos de compensaciones"

    def __str__(self):
        return f"{self.id.upper()} {self.name.title()}"

class Position(models.Model):
    id = models.CharField(max_length=20, primary_key=True)
    name = models.CharField(max_length=255, unique=True)
    department = models.ForeignKey('Department', on_delete=models.CASCADE, related_name='positions')
    description = models.TextField(max_length=255, null=True, blank=True)
    reports_to = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='positions')

    class Meta:
        verbose_name = 'Puesto'
        verbose_name_plural = 'Puestos'

    def __str__(self):
        return f'{self.id.upper()} {self.name.title()}'

class Region(models.Model):
    id = models.CharField(max_length=5, primary_key=True)
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(max_length=500, null=True, blank=True)
    manager = models.ForeignKey('Employee', on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_regions')

    class Meta:
        verbose_name = 'Región'
        verbose_name_plural = 'Regiones'

    def __str__(self):
        return f'{self.id.upper()} {self.name.title()}'
    
class Warehouse(models.Model):
    id = models.CharField(primary_key=True, max_length=20)
    name = models.CharField(max_length=255, unique=True)
    notes = models.TextField(max_length=500, null=True, blank=True)
    manager = models.ForeignKey('Employee', on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_warehouses')
    region = models.ForeignKey('Region', on_delete=models.SET_NULL, null=True, blank=True, related_name='warehouses')

    class Meta:
        verbose_name = 'Gerencia'
        verbose_name_plural = 'Gerencias'

    def __str__(self):
        return f'{self.id.upper()} {self.name.title()}'

class Employee(models.Model):
    id = models.CharField(primary_key=True, max_length=20)
    user = models.ForeignKey('core.User', on_delete=models.CASCADE, null=True, blank=True, related_name='employees')
    position = models.ForeignKey('Position', on_delete=models.CASCADE, null=True, blank=True, related_name='employees')
    manager = models.ForeignKey('self', on_delete=models.SET_NULL, blank=True, null=True, related_name='direct_reports')
    warehouse = models.ForeignKey('Warehouse', on_delete=models.SET_NULL, null=True, blank=True, related_name='employees')
    hire_date = models.DateField()
    termination_date = models.DateField(null=True, blank=True)
    payroll_type = models.ForeignKey('PayrollType', on_delete=models.SET_NULL, null=True, blank=True, related_name='employees')
    payroll_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    payroll_periodicity = models.ForeignKey('core.Periodicity', on_delete=models.SET_NULL, null=True, blank=True, related_name='employees')
    tax_system = models.ForeignKey('accounting.TaxSystem', on_delete=models.SET_NULL, null=True, blank=True, related_name='employees')
    contract = models.FileField(upload_to='employees/contracts/', null=True, blank=True)

    class Meta:
        verbose_name = 'Colaborador'
        verbose_name_plural = 'Colaboradores'

    def __str__(self):
        if not self.position or not self.warehouse:
            return f'{self.user.first_name.title()} {self.user.last_name.title()}, {str(self.id)[:7]}'
        else:
            return f'{self.user.first_name.title()} {self.user.last_name.title()}, {self.position.name.title()}: {self.warehouse.name.title()}'

    def get_reporting_tree_ids(self):

        """
        Returns a flatten list with this employee Id and all the employees that report to this employee directly or indirectly.
        """
        tree_ids = [self.id]
        direct_reports = Employee.objects.filter(manager=self)
        for report in direct_reports:
            tree_ids.extend(report.get_reporting_tree_ids())
        return list(set(tree_ids))

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
        verbose_name = 'Perfil de comisión'
        verbose_name_plural = 'Perfiles de comisión'
    
    def __str__(self):
        return self.name.strip().title()
        
class CommissionTier(models.Model):
    """
    Tier-based commission rules. This works as a range of values. For example, if the global rach is 90% and above, 
    and the profile dont require min lines to complete, then, the multplier is gonne be applied on the potential bonus previously calculated.
    
    """
    commission_profile = models.ForeignKey('CommissionProfile', on_delete=models.CASCADE, related_name='commission_tiers')
    min_global_scope_pct = models.DecimalField(max_digits=5, decimal_places=2) #set from 0 to 100 +
    min_completed_classes = models.IntegerField(default=0) #set as integer
    bonus_multiplier_pct = models.DecimalField(max_digits=5, decimal_places=2)
    extra_flat_bonus = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        ordering = ['-min_global_scope_pct', '-min_completed_classes']
        verbose_name = 'Umbral de comision'
        verbose_name_plural = 'Umbrales de comision'

    def __str__(self):
        return f'{self.commission_profile.name}\nAlcance global: {self.min_global_scope_pct} %\nLíneas requeridas: {self.min_completed_classes}\nMultiplicador: {self.bonus_multiplier_pct}%\nBono extra (si aplica): {self.extra_flat_bonus}'
    
class RouteCommissionSetup(models.Model):
    """
    Register the commission setup for a specific route in a specific period.
    """ 
    BONUS_CHOICES = (('f', 'fijo'), ('v', 'variable'))

    route = models.ForeignKey('sales.Route', on_delete=models.CASCADE, related_name='commission_history')
    profile = models.ForeignKey('CommissionProfile', on_delete=models.PROTECT)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    bonus_type = models.CharField(max_length=10, choices=BONUS_CHOICES, default='v')
    base_bonus_amount = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f'{self.route} | {self.profile} | {self.start_date} - {self.end_date}'

    class Meta:
        verbose_name = 'Configuración de comisión de ruta'
        verbose_name_plural = 'Configuraciones de comisión de ruta'

class RouteCommissionException(models.Model):
    """
    Register the commission exception for a specific route in a specific period. For example, during a period
    the route will receive an extra percentage of the global target scope. This is applicable for incoming employees
    """
    route = models.ForeignKey('sales.Route', on_delete=models.CASCADE, related_name='commission_exceptions')
    start_date = models.DateField()
    end_date = models.DateField()
    scope_tolerance_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    guaranteed_flat_bonus = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    notes = models.CharField(max_length=255)

    def __str__(self):
        return f'{self.route} | tolerancia pct: {self.scope_tolerance_pct} % | monto garantizado: $ {self.guaranteed_flat_bonus} | desde {self.start_date} hasta {self.end_date}'
    
    class Meta:
        verbose_name = 'Excepción de comisión de ruta'
        verbose_name_plural = 'Excepciones de comisión de ruta'

class CommissionSettlement(models.Model):
    """
    This table store the final commission amounts. It can be modified and recalculated only 
    through the admin site or if the status is draft.
    """
    STATUS_CHOICES = (('draft', 'borrador'), ('closed', 'cerrado'))

    period_start = models.DateField()
    period_end = models.DateField()
    route = models.ForeignKey('sales.Route', on_delete=models.PROTECT)
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
    manual_adjustment = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        return f'{self.employee.user} | {self.route} | {self.period_start} - {self.period_end} | monto: ${self.final_calculated_bonus}'

    class Meta:
        verbose_name = 'Liquidación de comisión'
        verbose_name_plural = 'Liquidaciones de comisión'
        ordering = ['-period_start']
    
