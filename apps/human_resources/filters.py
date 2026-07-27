import django_filters
from django.db.models import Q
from django import forms
from apps.human_resources.models import Department, Position, Skill, Employee
from apps.accounting.models import TaxRegimeChoices



class EmployeeFilter(django_filters.FilterSet):
    '''
    El listado es capaz de filtrarse por nivel jerarquico que tiene la posicion del empleado, por Nombre completo (first_name, last_name y second_last_name) y id en un text input, tipo de contratacion, por fecha de contratacion (rango) por fecha de baja (rango), por cual es la posicion que tiene asignada y por regimen fiscal del usuario
    '''
    search = django_filters.CharFilter(
        method='filter_search', 
        label='Buscar colaborador',
        widget=forms.TextInput(attrs={'placeholder': 'ID de colaborador o nombre'}))

    hire_date_from = django_filters.DateFilter(
        field_name='hire_date',
        lookup_expr='gte',
        label='Fecha de contratación desde',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'w-full bg-page border border-border rounded focus:outline-none focus:border-strong focus:ring-strong p-1 text-title'}))

    hire_date_to = django_filters.DateFilter(
        field_name='hire_date',
        lookup_expr='lte',
        label='Fecha de contratación hasta',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'w-full bg-page border border-border rounded focus:outline-none focus:border-strong focus:ring-strong p-1 text-title'}))

    termination_date_from = django_filters.DateFilter(
        field_name='termination_date',
        lookup_expr='gte',
        label='Fecha de baja desde',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'w-full bg-page border border-border rounded focus:outline-none focus:border-strong focus:ring-strong p-1 text-title'}))

    termination_date_to = django_filters.DateFilter(
        field_name='termination_date',
        lookup_expr='lte',
        label='Fecha de baja hasta',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'w-full bg-page border border-border rounded focus:outline-none focus:border-strong focus:ring-strong p-1 text-title'}))

    position = django_filters.ModelChoiceFilter(
        queryset=Position.objects.all(),
        label='Posición',
        widget=forms.Select(attrs={'class': 'w-full bg-page border border-border rounded focus:outline-none focus:border-strong focus:ring-strong p-1 text-title'}))

    hierarchy_level = django_filters.ChoiceFilter(
        field_name='position__hierarchy_level',
        choices=Position.HierarchyLevelChoices.choices,
        label='Nivel jerárquico',
        widget=forms.Select(attrs={'class': 'w-full bg-page border border-border rounded focus:outline-none focus:border-strong focus:ring-strong p-1 text-title'}))

    tax_regime = django_filters.ChoiceFilter(
        field_name='tax_regime',
        choices=TaxRegimeChoices.choices,
        label='Régimen fiscal',
        widget=forms.Select(attrs={'class': 'w-full bg-page border border-border rounded focus:outline-none focus:border-strong focus:ring-strong p-1 text-title'}))

    contract_type = django_filters.ChoiceFilter(
        field_name='contract_type',
        choices=Employee.ContractType.choices,
        label='Tipo de contrato',
        widget=forms.Select(attrs={'class': 'w-full bg-page border border-border rounded focus:outline-none focus:border-strong focus:ring-strong p-1 text-title'}))

    department = django_filters.ModelChoiceFilter(
        field_name='position__department',
        queryset=Department.objects.all(),
        label='Departamento',
        widget=forms.Select(attrs={'class': 'w-full bg-page border border-border rounded focus:outline-none focus:border-strong focus:ring-strong p-1 text-title'}))

    is_active = django_filters.BooleanFilter(
        method='filter_active',
        label='Estatus (Activo/Inactivo)',
        widget=forms.Select(
            choices=[('', '---------'), ('true', 'Activo'), ('false', 'Inactivo')],
            attrs={'class': 'w-full bg-page border border-border rounded focus:outline-none focus:border-strong focus:ring-strong p-1 text-title'}
        )
    )

    class Meta:
        model = Employee
        fields = ['contract_type', 'position', 'tax_regime']

    def filter_active(self, queryset, name, value):
        from django.utils import timezone
        today = timezone.now().date()
        active_q = (
            Q(termination_date__isnull=True) |
            Q(termination_date__gt=today)
        )
        if value:
            return queryset.filter(active_q)
        else:
            return queryset.filter(Q(termination_date__isnull=False) & Q(termination_date__lte=today))

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(id__icontains=value) |
            Q(user__first_name__icontains=value) |
            Q(user__last_name__icontains=value) |
            Q(user__second_last_name__icontains=value)
        ).distinct()

class DepartmentFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(
        method='filter_search', 
        label='Buscar departamento',
        widget=forms.TextInput(attrs={'placeholder': 'ID, nombre o descripción...'})
    )

    class Meta:
        model = Department
        fields = ['search']

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(id__icontains=value) |
            Q(name__icontains=value) |
            Q(description__icontains=value)
        )

class PositionFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(
        method='filter_search', 
        label='Buscar puesto',
        widget=forms.TextInput(attrs={'placeholder': 'ID, nombre o descripción...'})
    )
    
    department = django_filters.ModelChoiceFilter(
        queryset=Department.objects.all(),
        label='Departamento',
        widget=forms.Select(attrs={'class': 'w-full bg-page border border-border rounded focus:outline-none focus:border-strong focus:ring-strong p-1 text-title'})
    )
    
    skill = django_filters.ModelChoiceFilter(
        field_name='position_skills__skill',
        queryset=Skill.objects.all(),
        label='Habilidad',
        widget=forms.Select(attrs={'class': 'w-full bg-page border border-border rounded focus:outline-none focus:border-strong focus:ring-strong p-1 text-title'})
    )

    is_active = django_filters.BooleanFilter(
        method='filter_active',
        label='Tiene colaboradores activos',
        widget=forms.Select(
            choices=[('', '---------'), ('true', 'Sí'), ('false', 'No')],
            attrs={'class': 'w-full bg-page border border-border rounded focus:outline-none focus:border-strong focus:ring-strong p-1 text-title'}
        )
    )

    hierarchy_level = django_filters.ChoiceFilter(
        choices=Position.HierarchyLevelChoices.choices,
        label='Nivel jerárquico',
        widget=forms.Select(attrs={'class': 'w-full bg-page border border-border rounded focus:outline-none focus:border-strong focus:ring-strong p-1 text-title'})
    )

    employee = django_filters.CharFilter(
        method='filter_employee',
        label='Colaborador (Nombre)',
        widget=forms.TextInput(attrs={'placeholder': 'Nombre o apellido...'})
    )

    class Meta:
        model = Position
        fields = ['search', 'department', 'hierarchy_level', 'skill', 'is_active', 'employee']

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(id__icontains=value) |
            Q(name__icontains=value) |
            Q(description__icontains=value)
        ).distinct()

    def filter_active(self, queryset, name, value):
        from django.utils import timezone
        today = timezone.now().date()
        
        active_q = (
            Q(human_resources_employees__termination_date__isnull=True) |
            Q(human_resources_employees__termination_date__gt=today)
        )
        
        if value:
            return queryset.filter(active_q).distinct()
        else:
            return queryset.exclude(active_q).distinct()

    def filter_employee(self, queryset, name, value):
        return queryset.filter(
            Q(human_resources_employees__user__first_name__icontains=value) |
            Q(human_resources_employees__user__last_name__icontains=value)
        ).distinct()

class SkillFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(
        method='filter_search', 
        label='Buscar habilidad',
        widget=forms.TextInput(attrs={'placeholder': 'Nombre o descripción...'})
    )
    
    skill_type = django_filters.ChoiceFilter(
        choices=Skill.SkillTypeChoices.choices,
        label='Tipo de habilidad',
        widget=forms.Select(attrs={'class': 'w-full bg-page border border-border rounded focus:outline-none focus:border-strong focus:ring-strong p-1 text-title'})
    )

    class Meta:
        model = Skill
        fields = ['search', 'skill_type']

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(name__icontains=value) |
            Q(description__icontains=value)
        ).distinct()
