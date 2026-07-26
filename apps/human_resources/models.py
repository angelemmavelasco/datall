from django.db import models

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
    id = models.CharField(max_length=20, primary_key=True, help_text='Identificador único del puesto')
    name = models.CharField(max_length=255, unique=True, help_text='Nombre del puesto')
    department = models.ForeignKey('Department', on_delete=models.CASCADE, related_name='%(app_label)s_positions', help_text='Departamento al que pertenece el puesto')
    description = models.TextField(max_length=255, null=True, blank=True, help_text='Descripción del puesto')

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

    position = models.ForeignKey('Position', on_delete=models.CASCADE, related_name='position_skills', help_text='Puesto al que se le asigna la competencia')
    skill = models.ForeignKey('Skill', on_delete=models.PROTECT, related_name='position_requirements', help_text='Habilidad del catálogo')
    requirement_level = models.CharField(max_length=20, choices=RequirementLevelChoices.choices, default=RequirementLevelChoices.REQUIRED, help_text='Grado de obligatoriedad')
    skill_level = models.CharField(max_length=20, choices=SkillLevelChoices.choices, default=SkillLevelChoices.BASIC, help_text='Nivel de dominio mínimo requerido')
    notes = models.TextField(null=True, blank=True, help_text='Especificaciones adicionales para este puesto (ej. Certificación vigente requerida)')

    class Meta:
        verbose_name = 'Requisito de competencia'
        verbose_name_plural = 'Requisitos de competencias'
        unique_together = ('position', 'skill')

    def __str__(self):
        return f'{self.position.name.title()} -> {self.skill.name.title()} ({self.get_skill_level_display()})'
        

class Employee(models.Model):
    id = models.CharField(max_length=20, primary_key=True, help_text='Identificador único del colaborador')
    user = models.ForeignKey('core.User', on_delete=models.CASCADE, null=True, blank=True, related_name='%(app_label)s_employees')
    position = models.ForeignKey('Position', on_delete=models.CASCADE, null=True, blank=True, related_name='%(app_label)s_employees')
    manager = models.ForeignKey('self', on_delete=models.SET_NULL, blank=True, null=True, related_name='%(app_label)s_direct_reports')
    hire_date = models.DateField()
    termination_date = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = 'Colaborador'
        verbose_name_plural = 'Colaboradores'

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




