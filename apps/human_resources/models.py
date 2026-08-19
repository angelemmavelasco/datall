from django.db import models
from django.core.exceptions import ValidationError
from decimal import Decimal
from apps.core.models import TaxRegimeChoices, PaymentFormChoices, PeriodicityChoices
from collections import defaultdict

class Department(models.Model):
    id = models.CharField(max_length=3, primary_key=True, help_text='Identificador único del departamento')
    name = models.CharField(max_length=255, help_text='Nombre del departamento')
    description = models.TextField(default='', blank=True, help_text='Descripción del departamento')

    class Meta:
        verbose_name = "Departamento"
        verbose_name_plural = "Departamentos"

    def __str__(self):
        return f'{self.id.upper()} {self.name.title()}'

class Position(models.Model):
    '''
    header to identofy the main object, which is gonna have multiple employees, skills, etc.
    '''

    class HierarchyLevelChoices(models.TextChoices):
        LEVEL_1 = '1', '1'
        LEVEL_2 = '2', '2'
        LEVEL_3 = '3', '3'
        LEVEL_4 = '4', '4'
        LEVEL_5 = '5', '5'

    id = models.CharField(max_length=20, primary_key=True, help_text='Identificador único del puesto')
    name = models.CharField(max_length=255, unique=True, help_text='Nombre del puesto')
    department = models.ForeignKey('Department', on_delete=models.CASCADE, related_name='positions', help_text='Departamento al que pertenece el puesto')
    description = models.TextField(default='', blank=True, help_text='Descripción del puesto')
    hierarchy_level = models.CharField(max_length=20, choices=HierarchyLevelChoices.choices, default=HierarchyLevelChoices.LEVEL_1, help_text='Nivel jerárquico del puesto')

    class Meta:
        verbose_name = 'Puesto'
        verbose_name_plural = 'Puestos'

    def __str__(self):
        return f'{self.name.title()} ({self.department.id.upper()})'

class PositionKPI(models.Model):
    """
    kpis assigned to the position. They are specific for position, because any single kpis can have a weight for the total
    """
    class MeasurementUnitChoices(models.TextChoices):
        PERCENTAGE = 'percentage', 'Porcentaje (%)'
        CURRENCY = 'currency', 'Monto Moneda'
        NUMERIC = 'numeric', 'Cantidad / Conteo'
        BOOLEAN = 'boolean', 'Cumplimiento (Sí/No)'
        RATING = 'rating', 'Escala / Calificación'

    position = models.ForeignKey('Position', on_delete=models.CASCADE, related_name='kpis', help_text='Puesto al que pertenece este indicador')
    name = models.CharField(max_length=255, help_text='Nombre del indicador (ej. Cumplimiento de cuota de ventas)')
    description = models.TextField(default='', blank=True, help_text='Fórmula o método detallado de cálculo para medir el indicador')
    unit = models.CharField(max_length=20, choices=MeasurementUnitChoices.choices, default=MeasurementUnitChoices.PERCENTAGE, help_text='Unidad de medida del KPI')
    target_value = models.DecimalField(max_digits=12, decimal_places=2, help_text='Meta u objetivo a alcanzar para este puesto')
    weight = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'), help_text='Ponderación o peso relativo del KPI sobre la evaluación total (0 a 100%)')
    frequency = models.CharField(max_length=20, choices=PeriodicityChoices.choices, default=PeriodicityChoices.MONTHLY, help_text='Frecuencia con la que se debe evaluar este KPI')

    class Meta:
        verbose_name = 'KPI de Puesto'
        verbose_name_plural = 'KPIs del Puesto'
        ordering = ['position', '-weight', 'name']

    def __str__(self):
        return f'{self.position.name.title()} -> {self.name.title()} (Meta: {self.target_value})'

class Skill(models.Model):
    '''
    global catalog of reusable skills across the organization.
    '''
    class SkillTypeChoices(models.TextChoices):
        HARD = 'hard', 'Técnica'
        SOFT = 'soft', 'Blanda'
        LANGUAGE = 'language', 'Idioma'
        OTHER = 'other', 'Otra'

    name = models.CharField(max_length=150, unique=True, help_text='Nombre de la habilidad')
    skill_type = models.CharField(max_length=20, choices=SkillTypeChoices.choices, default=SkillTypeChoices.HARD, help_text='Clasificación general de la habilidad')
    description = models.TextField(null=True, blank=True, help_text='Definición o alcance de la habilidad')

    class Meta:
        verbose_name = 'Habilidad / Competencia'
        verbose_name_plural = 'Catálogo de Habilidades'
        ordering = ['skill_type', 'name']

    def __str__(self):
        return f'{self.name.title()} ({self.get_skill_type_display()})'

class PositionSkill(models.Model):
    '''
    intermediate table linking Positions to Skills, specifying the target requirements.
    '''
    class RequirementLevelChoices(models.TextChoices):
        REQUIRED = 'required', 'Requerido'
        OPTIONAL = 'optional', 'Opcional'
        PREFERRED = 'preferred', 'Preferente'

    class SkillLevelChoices(models.TextChoices):
        NO_KNOWLEDGE = 'none', 'Sin conocimiento'
        BASIC = 'basic', 'Básico'
        INTERMEDIATE = 'intermediate', 'Intermedio'
        ADVANCED = 'advanced', 'Avanzado'
        EXPERT = 'expert', 'Experto'

    position = models.ForeignKey('Position', on_delete=models.CASCADE, related_name='position_skills', help_text='Puesto al que se le asigna la competencia')
    skill = models.ForeignKey('Skill', on_delete=models.PROTECT, related_name='position_requirements', help_text='Habilidad del catálogo')
    requirement_level = models.CharField(max_length=20, choices=RequirementLevelChoices.choices, default=RequirementLevelChoices.REQUIRED, help_text='Grado de obligatoriedad')
    skill_level = models.CharField(max_length=20, choices=SkillLevelChoices.choices, default=SkillLevelChoices.BASIC, help_text='Nivel de dominio mínimo requerido')
    notes = models.TextField(default='', blank=True, help_text='Especificaciones adicionales para este puesto (ej. Certificación vigente requerida)')

    class Meta:
        verbose_name = 'Requisito de competencia'
        verbose_name_plural = 'Requisitos de competencias'
        unique_together = ('position', 'skill')

    def __str__(self):
        return f'{self.position.name.title()} -> {self.skill.name.title()} ({self.get_skill_level_display()})'

class MonitoringForm(models.Model):
    '''
    the base header to all the different monitoring forms to evaluate skills and kpis
    '''
    id = models.CharField(max_length=50, primary_key=True, help_text='Identificador único del formulario')
    name = models.CharField(max_length=255, help_text='Nombre del formulario')
    version = models.PositiveIntegerField(default=1, help_text='Versión del formulario')
    periodicity = models.CharField(max_length=3, choices=PeriodicityChoices.choices, default=PeriodicityChoices.WEEKLY, help_text='Periodicidad del formulario')
    is_active = models.BooleanField(default=True, help_text='Indica si el formulario está activo')

    class Meta:
        verbose_name = 'Reporte de desempeño'
        verbose_name_plural = 'Reportes de desempeño'

    def __str__(self):
        return f'{self.id.upper()} {self.name.title()} ({self.version})'

class MonitoringFormSchedule(models.Model):
    class DayOfWeek(models.IntegerChoices):
        MONDAY = 0, 'Lunes'
        TUESDAY = 1, 'Martes'
        WEDNESDAY = 2, 'Miércoles'
        THURSDAY = 3, 'Jueves'
        FRIDAY = 4, 'Viernes'
        SATURDAY = 5, 'Sábado'
        SUNDAY = 6, 'Domingo'

    class WeekOfMonth(models.TextChoices):
        FIRST = 'first', 'Primera'
        SECOND = 'second', 'Segunda'
        THIRD = 'third', 'Tercera'
        FOURTH = 'fourth', 'Cuarta'
        LAST = 'last', 'Última'
        EVERY = 'every', 'Todas (Para semanales)'

    form = models.OneToOneField('MonitoringForm', on_delete=models.CASCADE, related_name='schedule', help_text='Formulario asociado')
    open_day = models.IntegerField(choices=DayOfWeek.choices, default=DayOfWeek.FRIDAY, help_text='Día de la semana en que se abre el formulario')
    week_of_month = models.CharField(max_length=10, choices=WeekOfMonth.choices, default=WeekOfMonth.EVERY, help_text='Semana del mes en la que aplica (útil para mensuales)')
    open_time = models.TimeField(default="16:00:00", help_text='Hora exacta de apertura (ej. 16:00)')
    duration_hours = models.PositiveIntegerField(default=48, help_text='Duración en horas del plazo de entrega (ej. 48 para que cierre el domingo a la misma hora)')

    class Meta:
        verbose_name = 'Programación de reporte de desempeño'
        verbose_name_plural = 'Programaciones de reportes de desempeño'

    def __str__(self):
        return f'Horario para {self.form.name}'

class MonitoringPeriod(models.Model):
    form = models.ForeignKey('MonitoringForm', on_delete=models.CASCADE, related_name='periods')
    identifier = models.CharField(max_length=50, help_text='Identificador legible (ej. 2026-Semana30)')
    start_date = models.DateTimeField(help_text='Fecha y hora exacta de inicio del plazo')
    end_date = models.DateTimeField(help_text='Fecha y hora exacta de fin del plazo')
    is_active = models.BooleanField(default=True, help_text='Indica si este periodo está vigente/activo')

    class Meta:
        verbose_name = 'Periodo de evaluación'
        verbose_name_plural = 'Periodos de evaluaciones'
        unique_together = ('form', 'identifier')

    def __str__(self):
        return f'{self.identifier} ({self.form.name})'

class MonitoringFormField(models.Model):
    '''
    Questions to be answered in the monitoring forms
    '''

    class ResponseTypeChoices(models.TextChoices):
        TEXT = 'text', 'Texto libre'
        NUMBER = 'number', 'Número / Cantidad'
        PERCENTAGE = 'percentage', 'Porcentaje (%)'
        SCALE_1_5 = 'scale_1_5', 'Escala 1 a 5'
        BOOLEAN = 'boolean', 'Sí / No'
        FILE = 'file', 'Archivo'

    label = models.CharField(max_length=500, help_text='Pregunta o texto que ve el usuario')
    response_type = models.CharField(max_length=20, choices=ResponseTypeChoices.choices,default=ResponseTypeChoices.TEXT, help_text='Tipo de respuesta')
    description = models.TextField(db_default='', blank=True, help_text='Ayuda o guía para responder la pregunta')
    is_active = models.BooleanField(default=True, help_text='Indica si el campo está activo')

    class Meta:
        verbose_name = 'Campo de reporte de desempeño'
        verbose_name_plural = 'Campos de reportes de desempeño'

    def __str__(self):
        return f'{self.label.title()} ({self.get_response_type_display()})'

class MonitoringFormQuestion(models.Model):
    '''
    this connects the questions to the forms and defines in which forms and which positions/levels the questions are used
    '''
    form = models.ForeignKey('MonitoringForm', on_delete=models.CASCADE, related_name='form_questions', help_text='Formulario al que se le asigna la pregunta')
    question = models.ForeignKey('MonitoringFormField', on_delete=models.CASCADE, related_name='form_questions', help_text='Pregunta que se le asigna al formulario')
    hierarchy_level = models.CharField(max_length=20, null=True, blank=True, choices=Position.HierarchyLevelChoices.choices, help_text='Nivel jerárquico al que se le asigna la pregunta')
    position = models.ForeignKey('Position', null=True, blank=True, on_delete=models.CASCADE, related_name='monitoring_form_questions', help_text='Puesto al que se le asigna la pregunta')
    order = models.IntegerField(default=1, help_text='Orden en el que se muestra la pregunta')
    is_required = models.BooleanField(default=True, help_text='Indica si la pregunta es requerida')

    class Meta:
        verbose_name = 'Asignación de campo en reporte de desempeño'
        verbose_name_plural = 'Asignaciones de campos en reportes de desempeño'

    def __str__(self):
        target = self.position.name.title() if self.position else (
            f'Nivel {self.get_hierarchy_level_display()}' if self.hierarchy_level else 'General')
        return f'{self.question.label.title()} ({self.form.name.title()} - {target})'

class MonitoringFormSubmission(models.Model):
    class SubmissionStatus(models.TextChoices):
        DRAFT = 'draft', 'Borrador'
        SUBMITTED = 'submitted', 'Enviado'
        REVIEWED = 'reviewed', 'Revisado'

    employee = models.ForeignKey('Employee', on_delete=models.PROTECT, related_name='monitoring_submissions')
    form = models.ForeignKey('MonitoringForm', on_delete=models.PROTECT, related_name='submissions')
    period = models.ForeignKey('MonitoringPeriod', on_delete=models.PROTECT, related_name='submissions', help_text='Periodo al que corresponde este envío', null=True) # temporarily null=True in case there's data? It's fine without null=True if no data exists.
    submitted_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=SubmissionStatus.choices, default=SubmissionStatus.DRAFT)

    class Meta:
        verbose_name = 'Envío de reporte de desempeño'
        verbose_name_plural = 'Envíos de reportes de desempeño'
        unique_together = ('employee', 'form', 'period')

class MonitoringFormAnswer(models.Model):
    submission = models.ForeignKey('MonitoringFormSubmission', on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey('MonitoringFormQuestion', on_delete=models.PROTECT, related_name='answers')
    value = models.JSONField(help_text='Respuesta del usuario guardada de forma estructurada')

    class Meta:
        verbose_name = 'Respuesta de reporte de desempeño'
        verbose_name_plural = 'Respuestas de reportes de desempeño'


class BusinessUnit(models.Model):
    class BusinessUnitTypeChoices(models.TextChoices):
        UNIT = 'unit', 'Unidad'
        REGION = 'region', 'Región'

    id = models.CharField(primary_key=True, max_length=50, help_text='Identificador único (ej. cdmx1, gdl, foráneos)')
    name = models.CharField(max_length=255, help_text='Nombre de la gerencia o unidad de negocio')
    business_unit_type = models.CharField(max_length=20, choices=BusinessUnitTypeChoices.choices, default=BusinessUnitTypeChoices.UNIT, db_index=True, help_text='Tipo de unidad de negocio')
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='sub_units', help_text='Gerencia o región padre (ej. Foráneos es padre de Culiacán, Colima, etc.)')
    manager = models.ForeignKey('Employee', on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_business_units', help_text='Gerente o responsable de la unidad de negocio / región')

    class Meta:
        verbose_name = 'Unidad de Negocio / Gerencia'
        verbose_name_plural = 'Unidades de Negocio / Gerencias'

    def __str__(self):
        return f'{self.id.upper()} {self.name.title()}'

    @property
    def is_region(self) -> bool:
        return self.business_unit_type == self.BusinessUnitTypeChoices.REGION

    @property
    def is_unit(self) -> bool:
        return self.business_unit_type == self.BusinessUnitTypeChoices.UNIT

    def clean(self):
        super().clean()

        if self.parent_id:
            if self.pk and self.parent_id == self.pk:
                raise ValidationError({'parent': 'Una unidad de negocio no puede ser su propio padre.'})

            if self.pk:
                curr = self.parent
                visited = {self.pk}
                while curr:
                    if curr.pk in visited:
                        raise ValidationError({'parent': 'Se detectó una referencia circular en la jerarquía de unidades de negocio.'})
                    visited.add(curr.pk)
                    curr = curr.parent


class Employee(models.Model):
    class ContractType(models.TextChoices):
        TEMPORARY = 'temporary', 'Temporal'
        INDETERMINATE = 'indeterminate', 'Indeterminado'
        SERVICE = 'service', 'Servicios Profesionales / Honorarios'
        INTERNSHIP = 'internship', 'Prácticas / Becario'
        OTHER = 'other', 'Otro'

    id = models.CharField(max_length=20, primary_key=True, help_text='Identificador único del colaborador')
    user = models.ForeignKey('core.User', on_delete=models.CASCADE, related_name='employees')
    position = models.ForeignKey('Position', on_delete=models.CASCADE, related_name='employees')
    manager = models.ForeignKey('self', on_delete=models.SET_NULL, blank=True, null=True, related_name='direct_reports')
    business_unit = models.ForeignKey('BusinessUnit', on_delete=models.SET_NULL, null=True, blank=True, related_name='employees', help_text='Unidad de negocio a la que pertenece el colaborador')
    hire_date = models.DateField()
    termination_date = models.DateField(null=True, blank=True)
    contract_type = models.CharField(max_length=20, choices=ContractType.choices, default=ContractType.INDETERMINATE, help_text='Tipo de contrato')
    contract_doc = models.FileField(upload_to='contracts', null=True, blank=True, help_text='Documento del contrato')
    tax_doc = models.FileField(upload_to='tax_docs', null=True, blank=True, help_text='Documento de impuestos')
    tax_regime = models.CharField(max_length=3, choices=TaxRegimeChoices.choices, default=TaxRegimeChoices.SUELDOS_SALARIOS, help_text='Régimen fiscal del colaborador (asociado a pago o facturación)')
    tax_id = models.CharField(max_length=13, help_text='RFC del colaborador', default='XAXX010101000')
    payment_form = models.CharField(max_length=2, choices=PaymentFormChoices.choices, default=PaymentFormChoices._99, help_text='Forma de pago al colaborador')
    payroll_payment_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), help_text='Monto del pago al colaborador')
    payroll_frequency = models.CharField(max_length=3, choices=PeriodicityChoices.choices, default=PeriodicityChoices.FORTNIGHTLY, help_text='Periodicidad del pago al colaborador')

    class Meta:
        verbose_name = 'Colaborador'
        verbose_name_plural = 'Colaboradores'
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'position'],
                condition=models.Q(termination_date__isnull=True),
                name='unique_active_user_position_pair'
            )
        ]

    def __str__(self):
        return f'{self.position.name.title()}: {self.user.first_name.title()} {self.user.last_name.title()} (@{self.user.username.lower()})'

    def get_reporting_tree_ids(self):
        """
        Returns a flatten list with this employee Id and all the employees that report to this employee directly or indirectly.
        """
        relations = Employee.objects.values_list('id', 'manager_id')
        tree = defaultdict(list)

        for emp_id, manager_id in relations:
            if manager_id:
                tree[manager_id].append(emp_id)

        tree_ids = {self.id}
        queue = [self.id]

        while queue:
            current_id = queue.pop(0)
            for report_id in tree.get(current_id, []):
                if report_id not in tree_ids:
                    tree_ids.add(report_id)
                    queue.append(report_id)

        return list(tree_ids)
