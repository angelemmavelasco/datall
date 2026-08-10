import django_filters
from django.db.models import Q
from django import forms
from .models import Department, Position, Skill

class DepartmentFilter(django_filters.FilterSet):
    department = django_filters.CharFilter(
        method='filter_department', 
        label='Departamento (Nombre o ID)'
    )
    position = django_filters.CharFilter(
        field_name='positions__name', 
        lookup_expr='icontains', 
        label='Puesto'
    )
    employee = django_filters.CharFilter(
        method='filter_employee', 
        label='Colaborador (Activo o Inactivo)'
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
        label='Posición (Nombre o ID)'
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
