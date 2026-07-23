from django.db import models
from decimal import Decimal
# Create your models here.
class CustomerType(models.Model):
    id = models.CharField(max_length=100, primary_key=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = 'Tipo de cliente'
        verbose_name_plural = 'Tipos de clientes'

    def __str__(self):
        return f"{self.id} - {self.name}"

class Customer(models.Model):
    id = models.CharField(max_length=100, primary_key=True)
    name = models.CharField(max_length=255)
    registration_date = models.DateField()
    credit_limit = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal('0.00'))
    credit_days = models.IntegerField(default=0)    
    customer_type = models.ForeignKey('CustomerType', on_delete=models.PROTECT, related_name='customers')    
    opinion_leader = models.BooleanField(default=False)
    route = models.ForeignKey('sales.Route', on_delete=models.PROTECT, related_name='customers', blank=True, null=True)

    class Meta:
        verbose_name = 'Cliente'
        verbose_name_plural = 'Clientes'
        indexes = [
            models.Index(fields=["registration_date"]),
            models.Index(fields=["route", "customer_type"]),
        ]

    def __str__(self):
        return f"{self.id}: {self.name.strip().title()}"

class CustomerClassMargin(models.Model):
    customer = models.ForeignKey('Customer', on_delete=models.CASCADE, related_name='class_margins')
    product_class = models.ForeignKey('inventory.ProductClass', on_delete=models.CASCADE, related_name='customer_margins')
    min_margin_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))

    class Meta:
        verbose_name = 'Márgen de clase de producto'
        verbose_name_plural = 'Márgenes de clase de producto'
        unique_together = ('customer', 'product_class')

    def __str__(self):
        return f"{self.customer_id} - {self.product_class_id}: {self.min_margin_percentage}%"

class CommercialBenefit(models.Model):
    class BenefitType(models.TextChoices):
        PHYSICAL_ITEM = 'physical', 'artículo'
        FIXED_DISCOUNT = 'fixed_desc', 'descuento fijo'
        PCT_DISCOUNT = 'pct_desc', 'descuento porcentual'

    name = models.CharField(max_length=255, help_text="Ej: Hielera, Descuento 5%, Bono $1000")
    description = models.TextField(max_length=500, blank=True, null=True)
    benefit_type = models.CharField(max_length=15, choices=BenefitType.choices)
    image = models.FileField(upload_to='benefits', null=True, blank=True)
    stock = models.IntegerField(default=0, help_text="Solo aplica para artículos físicos")
    warehouse = models.ForeignKey('human_resources.Warehouse', on_delete=models.PROTECT, related_name='commercial_benefits', null=True, blank=True, help_text="Requerido si es un artículo físico")
    discount_value = models.DecimalField(max_digits=18, decimal_places=6, default=0, help_text="Monto fijo o porcentaje (%). Solo aplica si es descuento.")
    cost = models.DecimalField(max_digits=18, decimal_places=6, default=0, help_text="Costo del artículo o impacto total para la empresa")
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Beneficio comercial'
        verbose_name_plural = 'Beneficios comerciales'

    def __str__(self):
        return f"{self.name.title()} ({self.get_benefit_type_display()})"

class CustomerAgreement(models.Model):
    class TypesChoices(models.TextChoices):
        LONG_TERM = 'lt', 'largo plazo'
        MEDIUM_TERM = 'mt', 'medio plazo'
        SHORT_TERM = 'st', 'corto plazo'

    customer = models.ForeignKey('Customer', on_delete=models.PROTECT, related_name='agreements')
    route = models.ForeignKey('sales.Route', on_delete=models.PROTECT, related_name='customer_agreements')
    benefit = models.ForeignKey('CommercialBenefit', on_delete=models.PROTECT, related_name='agreements')
    doc_id = models.CharField(max_length=255, null=True, blank=True)
    agreement_name = models.CharField(max_length=255)
    agreement_type = models.CharField(max_length=2, choices=TypesChoices.choices, default=TypesChoices.SHORT_TERM)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    global_target_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    target_freq = models.ForeignKey('core.Periodicity', on_delete=models.PROTECT, related_name='target_agreements')
    penalty_freq = models.ForeignKey('core.Periodicity', on_delete=models.PROTECT, related_name='penalty_agreements', null=True, blank=True)
    growth_freq = models.ForeignKey('core.Periodicity', on_delete=models.PROTECT, related_name='growth_agreements', null=True, blank=True)
    penalty_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    growth_value = models.DecimalField(max_digits=18, decimal_places=2, default=0, help_text="Puede ser % o monto fijo")
    related_doc = models.FileField(upload_to='customer_agreements', null=True, blank=True)

    class Meta:
        verbose_name = 'Convenio'
        verbose_name_plural = 'Convenios'

    def __str__(self):
        return f"Convenio: {self.doc_id} - {self.agreement_name}"

class AgreementClassTarget(models.Model):
    agreement = models.ForeignKey('CustomerAgreement', on_delete=models.CASCADE, related_name='class_targets')
    product_class = models.ForeignKey('inventory.ProductClass', on_delete=models.PROTECT, related_name='agreement_targets')
    required_target = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    is_mandatory = models.BooleanField(default=True, help_text="Si es falso, suma al global pero no es restrictivo.")

    class Meta:
        verbose_name = 'Objetivo de convenio por clase de producto'
        verbose_name_plural = 'Objetivos de convenio por clase de producto'
        unique_together = ('agreement', 'product_class')

    def __str__(self):
        return f"{self.agreement_id} - Clase: {self.product_class_id} -> Meta: {self.required_target}"

class AgreementEvaluationPeriod(models.Model):
    class StatusChoices(models.TextChoices):
        PENDING = 'pending', 'pendiente'
        EVALUATING = 'evaluating', 'evaluando'
        ACHIEVED = 'achieved', 'alcanzado'
        FAILED = 'not_achieved', 'no alcanzado'

    agreement = models.ForeignKey('CustomerAgreement', on_delete=models.CASCADE, related_name='evaluation_periods')
    period_number = models.PositiveIntegerField()
    start_date = models.DateField()
    end_date = models.DateField()
    expected_global_target = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    achieved_global_sales = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    amortized_benefit_cost = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    period_profit = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    period_margin = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=20, choices=StatusChoices.choices, default=StatusChoices.PENDING)
    penalty_applied = models.BooleanField(default=False)
    observations = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = 'Periodo de evaluación de convenio'
        verbose_name_plural = 'Periodos de evaluación de convenios'

    def __str__(self):
        return f"{self.agreement_id} - Periodo: {self.period_number}"

class AgreementPeriodClassResult(models.Model):
    evaluation_period = models.ForeignKey('AgreementEvaluationPeriod', on_delete=models.CASCADE, related_name='class_results')
    product_class = models.ForeignKey('inventory.ProductClass', on_delete=models.PROTECT, related_name='period_results')
    expected_class_target = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    achieved_class_sales = models.DecimalField(max_digits=18, decimal_places=2, default=0)

    class Meta:
        verbose_name = 'Resultado de periodo por clase de producto'
        verbose_name_plural = 'Resultados de periodos por clase de producto'

class AccountsReceivable(models.Model):
    customer = models.ForeignKey('Customer', on_delete=models.CASCADE, related_name='accounts_receivable')
    route = models.ForeignKey('sales.Route', on_delete=models.SET_NULL, null=True, blank=True, related_name='accounts_receivables')
    issue_date = models.DateField(null=True)
    due_date = models.DateField(null=True)
    total_balance = models.DecimalField(max_digits=18, decimal_places=4, default=0, blank=True, null=True)
    description = models.CharField(max_length=255, null=True, blank=True)
    doc_id = models.CharField(max_length=255, null=True, blank=True)
    balance_15 = models.DecimalField(max_digits=18, decimal_places=4, default=0, blank=True, null=True)
    balance_30 = models.DecimalField(max_digits=18, decimal_places=4, default=0, blank=True, null=True)
    balance_60 = models.DecimalField(max_digits=18, decimal_places=4, default=0, blank=True, null=True)
    past_due = models.DecimalField(max_digits=18, decimal_places=4, default=0, blank=True, null=True)
    current_balance = models.DecimalField(max_digits=18, decimal_places=4, default=0, blank=True, null=True)

    class Meta:
        verbose_name = 'Cuentas por cobrar'
        verbose_name_plural = 'Cuentas por cobrar'

    def __str__(self):
        return f'{self.customer_id}: total balance $ {self.total_balance}'
