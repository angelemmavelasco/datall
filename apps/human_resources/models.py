from django.db import models
from decimal import Decimal
from apps.accounting.models import TaxRegimeChoices, PaymentFormChoices, PeriodicityChoices
    
class Department(models.Model):
    id = models.CharField(max_length=3, primary_key=True, help_text='Identificador único del departamento')
    name = models.CharField(max_length=255, help_text='Nombre del departamento')
    description = models.TextField(null=True, blank=True, help_text='Descripción del departamento')

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
        LEVEL_1 = '1', 'Nivel 1'
        LEVEL_2 = '2', 'Nivel 2'
        LEVEL_3 = '3', 'Nivel 3'
        LEVEL_4 = '4', 'Nivel 4'
        LEVEL_5 = '5', 'Nivel 5'
        
    id = models.CharField(max_length=20, primary_key=True, help_text='Identificador único del puesto')
    name = models.CharField(max_length=255, unique=True, help_text='Nombre del puesto')
    department = models.ForeignKey('Department', on_delete=models.CASCADE, related_name='%(app_label)s_positions', help_text='Departamento al que pertenece el puesto')
    description = models.TextField(max_length=255, null=True, blank=True, help_text='Descripción del puesto')
    hierarchy_level = models.CharField(max_length=20, choices=HierarchyLevelChoices.choices, default=HierarchyLevelChoices.LEVEL_1, help_text='Nivel jerárquico del puesto')

    class Meta:
        verbose_name = 'Puesto'
        verbose_name_plural = 'Puestos'

    def __str__(self):
        return f'{self.name.title()} ({self.department.id.upper()})'

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

    position = models.ForeignKey('Position', on_delete=models.CASCADE, related_name='%(app_label)s_position_skills', help_text='Puesto al que se le asigna la competencia')
    skill = models.ForeignKey('Skill', on_delete=models.PROTECT, related_name='%(app_label)s_position_requirements', help_text='Habilidad del catálogo')
    requirement_level = models.CharField(max_length=20, choices=RequirementLevelChoices.choices, default=RequirementLevelChoices.REQUIRED, help_text='Grado de obligatoriedad')
    skill_level = models.CharField(max_length=20, choices=SkillLevelChoices.choices, default=SkillLevelChoices.BASIC, help_text='Nivel de dominio mínimo requerido')
    notes = models.TextField(null=True, blank=True, help_text='Especificaciones adicionales para este puesto (ej. Certificación vigente requerida)')

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
        verbose_name = 'Formulario'
        verbose_name_plural = 'Formularios'
    
    def __str__(self):
        return f'{self.id.upper()} {self.name.title()} ({self.version})'

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

    label = models.CharField(max_length=500, help_text='Pregunta o texto que ve el usuario')
    response_type = models.CharField(max_length=20, choices=ResponseTypeChoices.choices, default=ResponseTypeChoices.TEXT, help_text='Tipo de respuesta')
    description = models.TextField(null=True, blank=True, help_text='Ayuda o guía para responder la pregunta')
    is_active = models.BooleanField(default=True, help_text='Indica si el campo está activo')

    class Meta:
        verbose_name = 'Campo de formulario de monitoreo'
        verbose_name_plural = 'Campos de formulario de monitoreo'

    def __str__(self):
        return f'{self.label.title()} ({self.get_response_type_display()})'
    
class MonitoringFormQuestion(models.Model):
    '''
    this connects the questions to the forms and defines in which forms and which positions/levels the questions are used
    '''
    form = models.ForeignKey('MonitoringForm', on_delete=models.CASCADE, related_name='%(app_label)s_form_questions', help_text='Formulario al que se le asigna la pregunta')
    question = models.ForeignKey('MonitoringFormField', on_delete=models.CASCADE, related_name='%(app_label)s_form_questions', help_text='Pregunta que se le asigna al formulario')
    hierarchy_level = models.CharField(max_length=20, null=True, blank=True, choices=Position.HierarchyLevelChoices.choices, help_text='Nivel jerárquico al que se le asigna la pregunta')
    position = models.ForeignKey('Position', null=True, blank=True, on_delete=models.CASCADE, related_name='%(app_label)s_monitoring_form_questions', help_text='Puesto al que se le asigna la pregunta')
    order = models.IntegerField(default=1, help_text='Orden en el que se muestra la pregunta')
    is_required = models.BooleanField(default=True, help_text='Indica si la pregunta es requerida')
    
    class Meta:
        verbose_name = 'Pregunta de formulario de monitoreo'
        verbose_name_plural = 'Preguntas de formulario de monitoreo'

    def __str__(self):
        target = self.position.name.title() if self.position else (f'Nivel {self.get_hierarchy_level_display()}' if self.hierarchy_level else 'General')
        return f'{self.question.label.title()} ({self.form.name.title()} - {target})'
    
class MonitoringFormSubmission(models.Model):
    class SubmissionStatus(models.TextChoices):
        DRAFT = 'draft', 'Borrador'
        SUBMITTED = 'submitted', 'Enviado'
        REVIEWED = 'reviewed', 'Revisado'

    employee = models.ForeignKey('Employee', on_delete=models.PROTECT, related_name='%(app_label)s_monitoring_submissions')
    form = models.ForeignKey('MonitoringForm', on_delete=models.PROTECT, related_name='%(app_label)s_submissions')
    period_identifier = models.CharField(max_length=20, help_text='Identificador del período (ej. 2026-W30 o 2026-07)')
    submitted_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=SubmissionStatus.choices, default=SubmissionStatus.DRAFT)
    
    class Meta:
        verbose_name = 'Envío de formulario de monitoreo'
        verbose_name_plural = 'Envíos de formularios de monitoreo'
        unique_together = ('employee', 'form', 'period_identifier')

class MonitoringFormAnswer(models.Model):
    submission = models.ForeignKey('MonitoringFormSubmission', on_delete=models.CASCADE, related_name='%(app_label)s_answers')
    question = models.ForeignKey('MonitoringFormQuestion', on_delete=models.PROTECT, related_name='%(app_label)s_answers')
    value = models.JSONField(help_text='Respuesta del usuario guardada de forma estructurada')

    class Meta:
        verbose_name = 'Respuesta de formulario de monitoreo'
        verbose_name_plural = 'Respuestas de formularios de monitoreo'


class BusinessUnit(models.Model):
    id = models.CharField(primary_key=True, max_length=50, help_text='Identificador único (ej. cdmx1, gdl, foráneos)')
    name = models.CharField(max_length=255, help_text='Nombre de la gerencia o unidad de negocio')
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='%(app_label)s_sub_units', help_text='Gerencia padre (ej. Foráneos es padre de Culiacán, Colima, etc.)')
    manager = models.ForeignKey('Employee', on_delete=models.SET_NULL, null=True, blank=True, related_name='%(app_label)s_managed_business_units', help_text='Gerente de la unidad de negocio')

    class Meta:
        verbose_name = 'Unidad de Negocio / Gerencia'
        verbose_name_plural = 'Unidades de Negocio / Gerencias'

    def __str__(self):
        return f'{self.id.upper()} {self.name.title()}'

class Employee(models.Model):
    class ContractType(models.TextChoices):
        TEMPORARY = 'temporary', 'Temporal'
        INDETERMINATE = 'indeterminate', 'Indeterminado'
        SERVICE = 'service', 'Servicios Profesionales / Honorarios'
        INTERNSHIP = 'internship', 'Prácticas / Becario'
        OTHER = 'other', 'Otro'
        
    id = models.CharField(max_length=20, primary_key=True, help_text='Identificador único del colaborador')
    user = models.ForeignKey('core.User', on_delete=models.CASCADE, related_name='%(app_label)s_employees')
    position = models.ForeignKey('Position', on_delete=models.CASCADE, related_name='%(app_label)s_employees')
    manager = models.ForeignKey('self', on_delete=models.SET_NULL, blank=True, null=True, related_name='%(app_label)s_direct_reports')
    business_unit = models.ForeignKey('BusinessUnit', on_delete=models.SET_NULL, null=True, blank=True, related_name='%(app_label)s_employees', help_text='Unidad de negocio a la que pertenece el colaborador')
    hire_date = models.DateField()
    termination_date = models.DateField(null=True, blank=True)
    contract_type = models.CharField(max_length=20, choices=ContractType.choices, default=ContractType.INDETERMINATE, help_text='Tipo de contrato')
    contract_doc = models.FileField(upload_to='contracts', null=True, blank=True, help_text='Documento del contrato')
    tax_doc = models.FileField(upload_to='tax_docs', null=True, blank=True, help_text='Documento de impuestos')
    tax_regime = models.CharField(max_length=3, choices=TaxRegimeChoices.choices, default=TaxRegimeChoices.SUELDOS_SALARIOS, help_text='Régimen fiscal del colaborador (asociado a pago o facturación)')
    tax_id = models.CharField(max_length=13, help_text='RFC del colaborador', default='XAXX010101000')
    payment_form = models.CharField(max_length=2, choices=PaymentFormChoices.choices, default=PaymentFormChoices._99, help_text='Forma de pago al colaborador')
    payroll_payment_amount = models.DecimalField(max_digits=10, decimal_places=2,default=Decimal('0.00'), help_text='Monto del pago al colaborador')
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
        tree_ids = [self.id]
        direct_reports = Employee.objects.filter(manager=self)
        for report in direct_reports:
            tree_ids.extend(report.get_reporting_tree_ids())
        return list(set(tree_ids))




