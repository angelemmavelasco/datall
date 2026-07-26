import django_filters
from django.db.models import Q
from django import forms
from apps.human_resources.models import Department

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

from apps.human_resources.models import Position, Skill

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

    employee = django_filters.CharFilter(
        method='filter_employee',
        label='Colaborador (Nombre)',
        widget=forms.TextInput(attrs={'placeholder': 'Nombre o apellido...'})
    )

    class Meta:
        model = Position
        fields = ['search', 'department', 'skill', 'is_active', 'employee']

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
