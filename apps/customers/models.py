from django.core.exceptions import ValidationError
from django.db import models
from decimal import Decimal
from django.db.models import Q, F
from django.utils import timezone
from apps.core.models import PeriodicityChoices

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

    class Meta:
        verbose_name = 'Cliente'
        verbose_name_plural = 'Clientes'
        indexes = [models.Index(fields=["registration_date"])]

    @property
    def current_visit_schedule(self):
        today = timezone.localdate()
        return self.visit_schedules.filter(
            start_date__lte=today
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=today)
        ).order_by('-start_date', '-id').first()

    def __str__(self):
        return f'{self.id.upper()} - {self.name.title()}'

class CustomerContactRole(models.TextChoices):
    OWNER = 'owner', 'Dueño / Dirección'
    PURCHASING = 'purchasing', 'Compras / Adquisiciones'
    COLLECTION = 'collection', 'Pagos / Cuentas por pagar'
    WAREHOUSE = 'warehouse', 'Almacén / Recepción'
    GENERAL = 'general', 'Contacto general'

class CustomerContact(models.Model):
    customer = models.ForeignKey('Customer', on_delete=models.CASCADE, related_name='contacts', help_text='Cliente al que pertenece el contacto')
    name = models.CharField(max_length=200, help_text='Nombre completo del contacto')
    role = models.CharField(max_length=30, choices=CustomerContactRole.choices, default=CustomerContactRole.GENERAL, help_text='Función o área del contacto')
    phone = models.CharField(max_length=50, blank=True, null=True, help_text='Teléfono de oficina o directo')
    mobile = models.CharField(max_length=50, blank=True, null=True, help_text='Celular / WhatsApp')
    email = models.EmailField(blank=True, null=True, help_text='Correo electrónico')
    is_primary = models.BooleanField(default=False, help_text='Indica si es el contacto principal')
    notes = models.CharField(max_length=255, blank=True, null=True, help_text='Notas breves')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Contacto de cliente'
        verbose_name_plural = 'Contactos de clientes'
        ordering = ['-is_primary', 'name']


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
                condition=Q(end_date__isnull=True) | Q(end_date__gte=F('start_date')),
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

class CustomerNoteCategoryChoices(models.TextChoices):
    HANDOVER = 'handover', 'Traspaso / Entrega de cuenta'
    COMMERCIAL = 'commercial', 'Preferencia comercial / Negociación'
    COLLECTION = 'collection', 'Cobranza / Condiciones de crédito'
    LOGISTICS = 'logistics', 'Recepción / Restricciones de entrega'
    INCIDENT = 'incident', 'Queja o incidencia'
    GENERAL = 'general', 'Nota general'

class CustomerNote(models.Model):
    customer = models.ForeignKey('Customer', on_delete=models.CASCADE, related_name='notes', help_text='Cliente al que pertenece la nota')
    author = models.ForeignKey('core.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='authored_customer_notes', help_text='Autor de la nota')
    current_route = models.ForeignKey('sales.Route', on_delete=models.SET_NULL, null=True, blank=True, related_name='route_customer_notes', help_text='Ruta asignada al momento de la nota')
    category = models.CharField(max_length=20, choices=CustomerNoteCategoryChoices.choices, default=CustomerNoteCategoryChoices.GENERAL, help_text='Categoría de la nota')
    content = models.TextField(help_text='Contenido de la nota')
    is_pinned = models.BooleanField(default=False, help_text='Indica si la nota está fijada')
    created_at = models.DateTimeField(auto_now_add=True, help_text='Fecha de creación de la nota')
    updated_at = models.DateTimeField(auto_now=True, help_text='Fecha de actualización de la nota')

    class Meta:
        verbose_name = 'Nota de cliente'
        verbose_name_plural = 'Notas de clientes'
        ordering = ['-is_pinned', '-created_at']
        indexes = [
            models.Index(fields=["customer", "-is_pinned", "-created_at"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f'{self.customer.id.upper()}: {self.content[:50]}...'

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


class CommercialBenefitTypeChoices(models.TextChoices):
    PHYSICAL_ITEM = 'physical', 'Artículo'
    FIXED_DISCOUNT = 'fixed_discount', 'Descuento fijo'
    PERCENTAGE_DISCOUNT = 'percentage_discount', 'Descuento porcentual'


class CommercialBenefit(models.Model):
    benefit_type = models.CharField(max_length=25,choices=CommercialBenefitTypeChoices.choices,default=CommercialBenefitTypeChoices.PHYSICAL_ITEM,help_text='Tipo de beneficio comercial')
    name = models.CharField(max_length=255, help_text='Nombre descriptivo del beneficio comercial')
    cost = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Costo total del beneficio para la empresa'
    )
    is_active = models.BooleanField(default=True, help_text='Indica si el beneficio está disponible')

    class Meta:
        verbose_name = 'Beneficio comercial'
        verbose_name_plural = 'Beneficios comerciales'
        ordering = ['name']

    def __str__(self):
        return f"{self.name.title()} ({self.get_benefit_type_display()}) - ${self.cost:,.2f}"


class AgreementTypeChoices(models.TextChoices):
    SHORT_TERM = 'st', 'Corto plazo'
    MEDIUM_TERM = 'mt', 'Medio plazo'
    LONG_TERM = 'lt', 'Largo plazo'


class EvaluationModeChoices(models.TextChoices):
    PERIODIC = 'periodic', 'Corte por periodo (penalización periódica)'
    AT_END = 'at_end', 'Corte al término (seguimiento de comportamiento)'


class CustomerAgreement(models.Model):
    customer = models.ForeignKey(
        'Customer',
        on_delete=models.PROTECT,
        related_name='agreements',
        help_text='Cliente al que se le otorga el convenio'
    )
    route = models.ForeignKey(
        'sales.Route',
        on_delete=models.PROTECT,
        related_name='customer_agreements',
        help_text='Ruta que originó el convenio'
    )
    benefit = models.ForeignKey(
        'CommercialBenefit',
        on_delete=models.PROTECT,
        related_name='agreements',
        help_text='Beneficio comercial pactado'
    )
    doc_id = models.CharField(
        max_length=50,
        unique=True,
        blank=True,
        help_text='Folio único del convenio (autogenerado de 5 caracteres si se omite)'
    )
    agreement_type = models.CharField(
        max_length=5,
        choices=AgreementTypeChoices.choices,
        default=AgreementTypeChoices.SHORT_TERM,
        help_text='Clasificación de plazo del convenio'
    )
    evaluation_mode = models.CharField(
        max_length=10,
        choices=EvaluationModeChoices.choices,
        default=EvaluationModeChoices.PERIODIC,
        help_text='Modalidad de corte: por periodo o acumulada al término del convenio'
    )
    start_date = models.DateField(help_text='Fecha de inicio del convenio (primer día del mes)')
    end_date = models.DateField(null=True, blank=True, help_text='Fecha de fin del convenio (último día del mes)')

    global_target_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Monto objetivo global por periodo de evaluación'
    )
    target_frequency = models.CharField(
        max_length=3,
        choices=PeriodicityChoices.choices,
        default=PeriodicityChoices.MONTHLY,
        help_text='Frecuencia de evaluación y penalización de ventas vs objetivo'
    )
    penalty_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Monto de penalización en caso de incumplimiento del periodo'
    )
    growth_value = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Porcentaje de crecimiento periódico exigido (ej. 5.00 para 5%)'
    )
    growth_frequency = models.CharField(
        max_length=3,
        choices=PeriodicityChoices.choices,
        blank=True,
        default='',
        help_text='Frecuencia en la que se incrementa la cuota de ventas'
    )
    related_doc = models.FileField(
        upload_to='customer_agreements/documents/',
        null=True,
        blank=True,
        help_text='Archivo escaneado o digital del convenio firmado'
    )
    signed = models.BooleanField(
        default=False,
        verbose_name='Firmado',
        help_text='Indica si el cliente ya firmó el documento o contrato del convenio'
    )
    benefit_already_provided = models.BooleanField(
        default=False,
        verbose_name='Beneficio entregado',
        help_text='Indica si el beneficio comercial ya fue entregado al cliente'
    )
    margin_warning_accepted = models.BooleanField(
        default=False,
        help_text='Indica si el usuario autorizó la creación aun con alerta de margen bajo'
    )
    created_by = models.ForeignKey(
        'core.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_agreements',
        help_text='Usuario que registró el convenio'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Convenio comercial'
        verbose_name_plural = 'Convenios comerciales'
        ordering = ['-start_date', '-created_at']
        indexes = [
            models.Index(fields=['customer', 'start_date', 'end_date']),
            models.Index(fields=['doc_id']),
            models.Index(fields=['route', 'start_date']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__isnull=True) | Q(end_date__gte=F('start_date')),
                name='customer_agreement_end_date_gte_start_date'
            )
        ]

    def clean(self):
        super().clean()
        if self.pk:
            original = CustomerAgreement.objects.get(pk=self.pk)
            immutable_fields = [
                'customer_id', 'route_id', 'benefit_id', 'doc_id',
                'agreement_type', 'evaluation_mode', 'start_date', 'end_date', 'global_target_amount',
                'target_frequency', 'penalty_amount',
                'growth_value', 'growth_frequency', 'margin_warning_accepted'
            ]
            for field in immutable_fields:
                if getattr(self, field) != getattr(original, field):
                    raise ValidationError(
                        f"El campo '{field}' es inmutable tras la creación del convenio. Únicamente se permite modificar el estado de firma, entrega del beneficio y documento adjunto."
                    )

    def save(self, *args, **kwargs):
        self.clean()
        if not self.doc_id:
            import random, string
            while True:
                candidate = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
                if not CustomerAgreement.objects.filter(doc_id=candidate).exists():
                    self.doc_id = candidate
                    break
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Convenio {self.doc_id} - {self.customer.id.upper()} ({self.route.id.upper()})"


class AgreementClassTarget(models.Model):
    agreement = models.ForeignKey(
        CustomerAgreement,
        on_delete=models.CASCADE,
        related_name='class_targets',
        help_text='Convenio al que aplica el objetivo por clase'
    )
    product_class = models.ForeignKey(
        'products.ProductClass',
        on_delete=models.PROTECT,
        related_name='agreement_targets',
        help_text='Clase de producto participante'
    )
    required_target = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Objetivo de compra individual para esta clase de producto'
    )
    is_mandatory = models.BooleanField(
        default=True,
        help_text='Si es verdadero, el no alcanzar este objetivo individual invalida el periodo'
    )

    class Meta:
        verbose_name = 'Objetivo por clase de producto'
        verbose_name_plural = 'Objetivos por clase de producto'
        unique_together = ('agreement', 'product_class')

    def __str__(self):
        return f"{self.agreement.doc_id} - {self.product_class.id.upper()} (${self.required_target:,.2f})"


class PeriodStatusChoices(models.TextChoices):
    PENDING = 'pending', 'En progreso'
    EVALUATING = 'evaluating', 'En evaluación'
    ACHIEVED = 'achieved', 'Alcanzado'
    FAILED = 'failed', 'No alcanzado'


class AgreementEvaluationPeriod(models.Model):
    agreement = models.ForeignKey(
        CustomerAgreement,
        on_delete=models.CASCADE,
        related_name='evaluation_periods',
        help_text='Convenio asociado'
    )
    period_number = models.PositiveIntegerField(help_text='Número secuencial del periodo (1, 2, ...)')
    start_date = models.DateField(help_text='Fecha inicial del periodo de evaluación')
    end_date = models.DateField(help_text='Fecha final del periodo de evaluación')
    expected_global_target = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Objetivo global esperado para este periodo (con crecimiento aplicado si aplica)'
    )
    achieved_global_sales = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Ventas netas globales alcanzadas en el periodo'
    )
    amortized_benefit_cost = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Costo del beneficio amortizado en este periodo'
    )
    period_profit = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Utilidad neta del periodo considerando amortización de beneficio'
    )
    period_margin = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Margen porcentual neto del periodo'
    )
    status = models.CharField(
        max_length=20,
        choices=PeriodStatusChoices.choices,
        default=PeriodStatusChoices.PENDING,
        help_text='Estado de cumplimiento del periodo'
    )
    penalty_applied = models.BooleanField(
        default=False,
        help_text='Indica si se aplicó penalización por incumplimiento'
    )
    is_informative = models.BooleanField(
        default=False,
        help_text='Indica si el periodo es para seguimiento mensual informativo sin penalización'
    )
    observations = models.TextField(blank=True, default='', help_text='Detalles u observaciones del periodo')

    @property
    def compliance_pct(self) -> Decimal:
        if self.expected_global_target and self.expected_global_target > 0:
            return ((self.achieved_global_sales / self.expected_global_target) * Decimal('100.00')).quantize(Decimal('0.1'))
        return Decimal('0.0')

    class Meta:
        verbose_name = 'Periodo de evaluación de convenio'
        verbose_name_plural = 'Periodos de evaluación de convenios'
        unique_together = ('agreement', 'period_number')
        ordering = ['agreement', 'period_number']

    def __str__(self):
        return f"{self.agreement.doc_id} - Periodo {self.period_number} ({self.get_status_display()})"


class AgreementPeriodClassResult(models.Model):
    evaluation_period = models.ForeignKey(
        AgreementEvaluationPeriod,
        on_delete=models.CASCADE,
        related_name='class_results',
        help_text='Periodo de evaluación'
    )
    product_class = models.ForeignKey(
        'products.ProductClass',
        on_delete=models.PROTECT,
        related_name='period_class_results',
        help_text='Clase de producto evaluada'
    )
    expected_class_target = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Objetivo individual esperado para esta clase en el periodo'
    )
    achieved_class_sales = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text='Venta neta real alcanzada en esta clase en el periodo'
    )

    class Meta:
        verbose_name = 'Resultado de clase por periodo'
        verbose_name_plural = 'Resultados de clase por periodo'
        unique_together = ('evaluation_period', 'product_class')

    def __str__(self):
        return f"{self.evaluation_period.agreement.doc_id} - P{self.evaluation_period.period_number} - {self.product_class.id.upper()}: ${self.achieved_class_sales:,.2f} / ${self.expected_class_target:,.2f}"


class CustomerVisitSchedule(models.Model):
    customer = models.ForeignKey(
        'Customer',
        on_delete=models.CASCADE,
        related_name='visit_schedules',
        help_text='Cliente al que pertenece el esquema de visitas'
    )
    route = models.ForeignKey(
        'sales.Route',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='customer_visit_schedules',
        help_text='Ruta activa asignada al cliente al momento de la configuración'
    )
    created_by = models.ForeignKey(
        'core.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_visit_schedules',
        help_text='Usuario que registró o modificó este esquema de visitas'
    )
    periodicity = models.CharField(
        max_length=5,
        choices=[
            (c[0], c[1]) for c in PeriodicityChoices.choices
            if c[0] not in (PeriodicityChoices.DAILY, PeriodicityChoices.WEEKLY, PeriodicityChoices.AT_END)
        ],
        null=True,
        blank=True,
        help_text='Periodicidad de la visita comercial según PeriodicityChoices (ej. 2w, 1m). Si se deja en blanco, la visita es semanal en los días asignados.'
    )
    visit_monday = models.BooleanField(default=False, verbose_name='Lunes')
    visit_tuesday = models.BooleanField(default=False, verbose_name='Martes')
    visit_wednesday = models.BooleanField(default=False, verbose_name='Miércoles')
    visit_thursday = models.BooleanField(default=False, verbose_name='Jueves')
    visit_friday = models.BooleanField(default=False, verbose_name='Viernes')
    visit_saturday = models.BooleanField(default=False, verbose_name='Sábado')
    visit_sunday = models.BooleanField(default=False, verbose_name='Domingo')

    start_date = models.DateField(help_text='Fecha de inicio de vigencia de este esquema de visitas')
    end_date = models.DateField(null=True, blank=True, help_text='Fecha de término de vigencia de este esquema de visitas')
    notes = models.TextField(blank=True, default='', help_text='Observaciones o especificaciones sobre las visitas')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Esquema de visitas de cliente'
        verbose_name_plural = 'Esquemas de visitas de clientes'
        ordering = ['-start_date', '-created_at']
        indexes = [
            models.Index(fields=['customer', 'start_date', 'end_date']),
            models.Index(fields=['start_date']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['customer'],
                condition=Q(end_date__isnull=True),
                name='unique_active_visit_schedule_per_customer'
            ),
            models.CheckConstraint(
                condition=Q(end_date__isnull=True) | Q(end_date__gte=F('start_date')),
                name='customer_visit_schedule_end_date_gte_start_date'
            ),
        ]

    @property
    def selected_days(self) -> list[str]:
        days = []
        if self.visit_monday:
            days.append('Lunes')
        if self.visit_tuesday:
            days.append('Martes')
        if self.visit_wednesday:
            days.append('Miércoles')
        if self.visit_thursday:
            days.append('Jueves')
        if self.visit_friday:
            days.append('Viernes')
        if self.visit_saturday:
            days.append('Sábado')
        if self.visit_sunday:
            days.append('Domingo')
        return days

    @property
    def days_display(self) -> str:
        days = self.selected_days
        if not days:
            return 'Sin días asignados'
        if len(days) == 1:
            return days[0]
        if len(days) == 2:
            return f"{days[0]} y {days[1]}"
        return f"{', '.join(days[:-1])} y {days[-1]}"

    @property
    def days_short_display(self) -> str:
        mapping = {
            'Lunes': 'Lun',
            'Martes': 'Mar',
            'Miércoles': 'Mié',
            'Jueves': 'Jue',
            'Viernes': 'Vie',
            'Sábado': 'Sáb',
            'Domingo': 'Dom',
        }
        return ', '.join(mapping.get(d, d) for d in self.selected_days) or '-'

    @property
    def periodicity_display(self) -> str:
        if not self.periodicity:
            return 'Cada semana'
        try:
            p_label = PeriodicityChoices(self.periodicity).label.lower()
            return f"Cada {p_label}"
        except (ValueError, KeyError):
            return self.periodicity or 'Cada semana'

    @property
    def summary(self) -> str:
        days_str = self.days_display
        if not self.periodicity:
            if not self.selected_days:
                return 'Visitas semanales'
            return f"{days_str} cada semana"

        try:
            p_label = PeriodicityChoices(self.periodicity).label.lower()
            freq_text = 'mes' if p_label == '1 mes' else p_label
            return f"{days_str} cada {freq_text}"
        except (ValueError, KeyError):
            return f"{days_str} ({self.periodicity})"

    @property
    def is_active(self) -> bool:
        today = timezone.localdate()
        if self.start_date > today:
            return False
        return self.end_date is None or self.end_date >= today

    def get_relativedelta(self):
        from dateutil.relativedelta import relativedelta
        if not self.periodicity:
            return relativedelta(weeks=1)
        try:
            return PeriodicityChoices(self.periodicity).get_relativedelta()
        except Exception:
            return relativedelta(weeks=1)

    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({
                'end_date': 'La fecha de fin no puede ser anterior a la fecha de inicio.'
            })

        if not any([
            self.visit_monday, self.visit_tuesday, self.visit_wednesday,
            self.visit_thursday, self.visit_friday, self.visit_saturday, self.visit_sunday
        ]):
            raise ValidationError(
                'Debes seleccionar al menos un día de la semana para la visita.'
            )

        if self.customer_id and self.start_date:
            qs = CustomerVisitSchedule.objects.filter(customer_id=self.customer_id)
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
                start_str = first_overlap.start_date.strftime('%d/%m/%Y') if first_overlap.start_date else ''
                end_str = first_overlap.end_date.strftime('%d/%m/%Y') if first_overlap.end_date else 'Presente'
                raise ValidationError(
                    f'Este cliente ya cuenta con un esquema de visitas ({first_overlap.summary}) programado del {start_str} al {end_str}. Para modificarlo, ajusta las fechas de vigencia o edita el esquema actual.'
                )

    def __str__(self):
        return f'{self.customer.id.upper()} - {self.summary} ({self.start_date} - {self.end_date or "Presente"})'


