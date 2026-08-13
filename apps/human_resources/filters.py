import django_filters
from django.db.models import Q
from django import forms
from .models import Department, Position, Skill, PositionSkill, Employee, MonitoringForm
from .services.employees import EmployeesService
from .services.positions import PositionsService
from .services.departments import DepartmentsService

class DepartmentFilter(django_filters.FilterSet):
    department = django_filters.CharFilter(
        method='filter_department', 
        label='Departamento'
    )
    position = django_filters.CharFilter(
        field_name='positions__name', 
        lookup_expr='icontains', 
        label='Puesto'
    )
    employee = django_filters.CharFilter(
        method='filter_employee', 
        label='Colaborador'
    )

    class Meta:
        model = Department
        fields = []

    def filter_department(self, queryset, name, value):
        return queryset.filter(
            Q(id__icontains=value) |
            Q(name__icontains=value)
        ).distinct()

    def filter_employee(self, queryset, name, value):
        return queryset.filter(
            Q(positions__employees__user__first_name__icontains=value) |
            Q(positions__employees__user__last_name__icontains=value) |
            Q(positions__employees__user__username__icontains=value)
        ).distinct()

class PositionFilter(django_filters.FilterSet):
    position = django_filters.CharFilter(
        method='filter_position', 
        label='Posición'
    )
    employee = django_filters.CharFilter(
        method='filter_employee', 
        label='Colaborador'
    )
    department = django_filters.ModelMultipleChoiceFilter(
        queryset=Department.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label='Departamento'
    )
    hierarchy_level = django_filters.MultipleChoiceFilter(
        choices=Position.HierarchyLevelChoices.choices,
        widget=forms.CheckboxSelectMultiple,
        label='Nivel de Jerarquía'
    )
    skills = django_filters.ModelMultipleChoiceFilter(
        field_name='position_skills__skill',
        queryset=Skill.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label='Habilidades requeridas'
    )

    class Meta:
        model = Position
        fields = []

    def filter_position(self, queryset, name, value):
        return queryset.filter(
            Q(id__icontains=value) |
            Q(name__icontains=value)
        ).distinct()

    def filter_employee(self, queryset, name, value):
        return queryset.filter(
            Q(employees__user__first_name__icontains=value) |
            Q(employees__user__last_name__icontains=value) |
            Q(employees__user__username__icontains=value)
        ).distinct()

class SkillFilter(django_filters.FilterSet):
    skill = django_filters.CharFilter(
        method='filter_skill',
        label='Id o Nombre de la habilidad'
    )
    employee = django_filters.ModelMultipleChoiceFilter(
        field_name='position_requirements__position__employees',
        queryset=Employee.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label='Colaborador'
    )
    skill_type = django_filters.MultipleChoiceFilter(
        field_name='skill_type',
        choices=Skill.SkillTypeChoices.choices,
        widget=forms.CheckboxSelectMultiple,
        label='Tipo de habilidad'
    )
    requirement_level = django_filters.MultipleChoiceFilter(
        field_name='position_requirements__requirement_level',
        choices=PositionSkill.RequirementLevelChoices.choices,
        widget=forms.CheckboxSelectMultiple,
        label='Tipo de requerimiento'
    )
    skill_level = django_filters.MultipleChoiceFilter(
        field_name='position_requirements__skill_level',
        choices=PositionSkill.SkillLevelChoices.choices,
        widget=forms.CheckboxSelectMultiple,
        label='Nivel de conocimiento'
    )
    position = django_filters.ModelMultipleChoiceFilter(
        field_name='position_requirements__position',
        queryset=Position.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label='Posición'
    )
    department = django_filters.ModelMultipleChoiceFilter(
        field_name='position_requirements__position__department',
        queryset=Department.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label='Departamento'
    )

    class Meta:
        model = Skill
        fields = []

    def __init__(self, *args, **kwargs):
        request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        
        if request:
            self.filters['employee'].queryset = EmployeesService(user=request.user).read_employees()
            self.filters['position'].queryset = PositionsService(user=request.user).read_positions()
            self.filters['department'].queryset = DepartmentsService(user=request.user).read_departments()

    def filter_skill(self, queryset, name, value):
        return queryset.filter(
            Q(id__icontains=value) |
            Q(name__icontains=value)
        ).distinct()

class MonitoringFormFilter(django_filters.FilterSet):
    form = django_filters.CharFilter(
        method='filter_form',
        label='Id o Nombre del reporte'
    )
    employee = django_filters.CharFilter(
        method='filter_employee',
        label='Id o Nombre de colaborador'
    )
    position = django_filters.ModelMultipleChoiceFilter(
        field_name='form_questions__position',
        queryset=Position.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label='Posición'
    )
    hierarchy_level = django_filters.MultipleChoiceFilter(
        field_name='form_questions__hierarchy_level',
        choices=Position.HierarchyLevelChoices.choices,
        widget=forms.CheckboxSelectMultiple,
        label='Nivel jerárquico'
    )
    periodicity = django_filters.MultipleChoiceFilter(
        choices=MonitoringForm.periodicity.field.choices,
        widget=forms.CheckboxSelectMultiple,
        label='Periodicidad'
    )
    is_active = django_filters.TypedMultipleChoiceFilter(
        choices=[('True', 'Activos'), ('False', 'Inactivos')],
        coerce=lambda x: x == 'True',
        widget=forms.CheckboxSelectMultiple,
        label='Estatus'
    )

    class Meta:
        model = MonitoringForm
        fields = []

    def __init__(self, data=None, *args, **kwargs):
        request = kwargs.pop('request', None)
        
        if not data:
            data = data.copy() if data is not None else {}
            data.setlist('is_active', ['True']) if hasattr(data, 'setlist') else data.update({'is_active': ['True']})
            
        super().__init__(data, *args, **kwargs)
        
        if request:
            self.emp_service = EmployeesService(user=request.user)
            self.filters['position'].queryset = PositionsService(user=request.user).read_positions()

    def filter_form(self, queryset, name, value):
        return queryset.filter(
            Q(id__icontains=value) |
            Q(name__icontains=value)
        ).distinct()

    def filter_employee(self, queryset, name, value):
        if not hasattr(self, 'emp_service'):
            return queryset
            
        employees = self.emp_service.read_employees().filter(
            Q(id__icontains=value) |
            Q(user__first_name__icontains=value) |
            Q(user__last_name__icontains=value)
        )
        
        position_ids = employees.values_list('position_id', flat=True)
        hierarchy_levels = Position.objects.filter(id__in=position_ids).values_list('hierarchy_level', flat=True)
        
        return queryset.filter(
            Q(form_questions__position__id__in=position_ids) |
            Q(form_questions__hierarchy_level__in=hierarchy_levels)
        ).distinct()
