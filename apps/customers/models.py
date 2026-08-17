from django.core.exceptions import ValidationError
from django.db import models
from decimal import Decimal
from django.db.models import Q, F

class CustomerType(models.Model):
    id = models.CharField(max_length=100, primary_key=True, help_text='Identificador unico del tipo de cliente')
    name = models.CharField(max_length=255, help_text='Tipo de cliente')
    description = models.TextField(blank=True, null=True, help_text='Descripción del tipo de cliente')

    class Meta:
        verbose_name = 'Tipo de cliente'
        verbose_name_plural = 'Tipos de cliente'

    def __str__(self):
        return f'{self.id.upper()} - {self.name.title()}'

class Customer(models.Model):
    id = models.CharField(max_length=100, primary_key=True, help_text='Identificador del cliente')
    name = models.CharField(max_length=255, help_text='Nombre del cliente (nombre comercial o encargado de la cuenta)')
    registration_date = models.DateField(help_text='Fecha de registro del cliente')
    credit_limit = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal('0.00'), help_text='Linea de credito del cliente')
    credit_days = models.IntegerField(default=0, help_text='Dias de credito del cliente')
    customer_type = models.ForeignKey('CustomerType', on_delete=models.PROTECT, related_name='customers', help_text='Tipo de cliente')
    opinion_leader = models.BooleanField(default=False, help_text='Indica si el cliente es un lider de opinion')
    # tax_entities = models.JSONField(default=list, blank=True, validators=[validate_tax_entities], help_text='Información fiscal')
    # delivery_addresses = models.JSONField(default=list, blank=True, validators=[validate_delivery_addresses], help_text='Direcciones de entrega')
    # contacts = models.JSONField(default=list, blank=True, validators=[validate_contacts], help_text='Contactos')

    class Meta:
        verbose_name = 'Cliente'
        verbose_name_plural = 'Clientes'
        indexes = [models.Index(fields=["registration_date"])]

    def __str__(self):
        return f'{self.id.upper()} - {self.name.title()}'

class CustomerAssignment(models.Model):
    customer = models.ForeignKey('Customer', on_delete=models.CASCADE, related_name='assignments', help_text='Cliente a asignar')
    route = models.ForeignKey('sales.Route', on_delete=models.PROTECT, related_name='assignments', help_text='Ruta a la que se asigna el cliente')
    start_date = models.DateField(help_text='Fecha de inicio de la asignación')
    end_date = models.DateField(null=True, blank=True, help_text='Fecha de fin de la asignación')
    notes = models.TextField(null=True, blank=True, help_text='Notas sobre la asignación')
    
    class Meta:
        verbose_name = 'Asignación de cliente'
        verbose_name_plural = 'Asignaciones de clientes'
        constraints = [
            models.UniqueConstraint(
                fields=["customer"],
                condition=Q(end_date__isnull=True),
                name="unique_active_assignment_per_customer"
            ),
            models.CheckConstraint(
                check=Q(end_date__isnull=True) | Q(end_date__gte=F('start_date')),
                name="customer_assignment_end_date_gte_start_date"
            ),
        ]

    def clean(self):
        super().clean()

        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({
                'end_date': 'La fecha de fin no puede ser anterior a la fecha de inicio.'
            })

        if self.customer_id and self.start_date:
            qs = CustomerAssignment.objects.filter(customer_id=self.customer_id)
            if self.pk:
                qs = qs.exclude(pk=self.pk)

            if not self.end_date:
                overlapping = qs.filter(
                    Q(end_date__isnull=True) | Q(end_date__gte=self.start_date)
                )
            else:
                overlapping = qs.filter(
                    Q(end_date__isnull=True, start_date__lte=self.end_date) |
                    Q(end_date__isnull=False, start_date__lte=self.end_date, end_date__gte=self.start_date)
                )

            if overlapping.exists():
                first_overlap = overlapping.first()
                overlap_route = first_overlap.route.id.upper() if first_overlap.route else ''
                raise ValidationError(
                    f'Ya existe una asignación para este cliente ({overlap_route}) que se empalma o es simultánea con el rango de fechas seleccionado ({self.start_date} - {self.end_date or "Presente"}).'
                )

    def __str__(self):
        return f'{self.customer.id.upper()} -> {self.route.id.upper()}'

class CustomerClassMargin(models.Model):
    customer = models.ForeignKey('Customer', on_delete=models.CASCADE, related_name='class_margins')
    product_class = models.ForeignKey('products.ProductClass', on_delete=models.CASCADE, related_name='customer_margins')
    min_margin_percentage = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal('0.00'))

    class Meta:
        verbose_name = 'Margen por clase de producto'
        verbose_name_plural = 'Márgenes por clase de producto'
        unique_together = ('customer', 'product_class')


class AccountsReceivable(models.Model):
    #cve_cte
    customer = models.ForeignKey('Customer', on_delete=models.CASCADE, related_name='accounts_receivable', help_text='Cliente')
    #cve_age
    route = models.ForeignKey('sales.Route', on_delete=models.SET_NULL, null=True, blank=True, related_name='accounts_receivables', help_text='Ruta que emitió la factura')
    #falta_fac
    issue_date = models.DateField(null=True, help_text='Fecha de emisión de la factura')
    #f_pago
    due_date = models.DateField(null=True, help_text='Fecha de vencimiento de la factura')
    #subtotal total
    total_balance = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal('0.00'), blank=True, help_text='Saldo total')
    #concepto
    description = models.CharField(max_length=255, default='', blank=True, help_text='Concepto de la factura')
    #odc_id
    doc_id = models.CharField(max_length=255, default='', blank=True, help_text='Documento')
    #rango1
    balance_15 = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal('0.00'), blank=True, help_text='Saldo de 1 a 15 días')
    #rango2
    balance_30 = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal('0.00'), blank=True, help_text='Saldo de 16 a 30 días')
    #rango3
    balance_60 = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal('0.00'), blank=True, help_text='Saldo de 31 a 60 días')
    #rango4 +60
    past_due = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal('0.00'), blank=True, help_text='Saldo mayor a 60 días')
    #rangoc al corriente
    current_balance = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal('0.00'), blank=True, help_text='Saldo al corriente')


    

    class Meta:
        verbose_name = 'Cuenta por cobrar'
        verbose_name_plural = 'Cuentas por cobrar'

    def __str__(self):
        return f'{self.customer_id}: total balance $ {self.total_balance}'


