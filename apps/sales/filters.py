import django_filters
from django import forms
from django.db.models import Q
from django.utils import timezone

from apps.human_resources.models import Employee, BusinessUnit
from apps.human_resources.services.employees import EmployeesService
from apps.human_resources.services.business_units import BusinessUnitsService
from .models import Warehouse, Route, RouteType, SaleChannel


class WarehouseFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(
        method='filter_name',
        label='Centro de distribución'
    )
    warehouse_type = django_filters.MultipleChoiceFilter(
        field_name='warehouse_type',
        choices=Warehouse.WarehouseTypeChoices.choices,
        widget=forms.CheckboxSelectMultiple,
        label='Tipo de centro'
    )

    class Meta:
        model = Warehouse
        fields = []

    def filter_name(self, queryset, name, value):
        return queryset.filter(
            Q(id__icontains=value) |
            Q(name__icontains=value)
        ).distinct()


class RouteFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(
        method='filter_name',
        label='Ruta'
    )
    employee = django_filters.ModelMultipleChoiceFilter(
        method='filter_employee',
        queryset=Employee.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label='Colaborador asignado'
    )
    business_unit = django_filters.ModelMultipleChoiceFilter(
        field_name='business_unit',
        queryset=BusinessUnit.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label='Gerencia'
    )
    route_type = django_filters.ModelMultipleChoiceFilter(
        field_name='route_type',
        queryset=RouteType.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label='Tipo de ruta'
    )
    sale_channel = django_filters.ModelMultipleChoiceFilter(
        field_name='sale_channel',
        queryset=SaleChannel.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label='Canal de venta'
    )
    is_active = django_filters.TypedMultipleChoiceFilter(
        choices=[('True', 'Activa'), ('False', 'Inactiva')],
        coerce=lambda x: x == 'True',
        widget=forms.CheckboxSelectMultiple,
        label='Estatus'
    )
    assignment_date_start_from = django_filters.DateFilter(
        field_name='route_assignments__date_start',
        lookup_expr='gte',
        label='Inicio asignación (Desde)',
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    assignment_date_start_to = django_filters.DateFilter(
        field_name='route_assignments__date_start',
        lookup_expr='lte',
        label='Inicio asignación (Hasta)',
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    assignment_date_end_from = django_filters.DateFilter(
        field_name='route_assignments__date_end',
        lookup_expr='gte',
        label='Fin asignación (Desde)',
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    assignment_date_end_to = django_filters.DateFilter(
        field_name='route_assignments__date_end',
        lookup_expr='lte',
        label='Fin asignación (Hasta)',
        widget=forms.DateInput(attrs={'type': 'date'})
    )

    class Meta:
        model = Route
        fields = []

    def __init__(self, *args, **kwargs):
        request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        if request:
            self.filters['employee'].queryset = EmployeesService(user=request.user).read_employees()
            self.filters['business_unit'].queryset = BusinessUnitsService(user=request.user).read_business_units()
            self.filters['route_type'].queryset = RouteType.objects.all()
            self.filters['sale_channel'].queryset = SaleChannel.objects.all()

    def filter_name(self, queryset, name, value):
        return queryset.filter(
            Q(id__icontains=value) |
            Q(name__icontains=value)
        ).distinct()

    def filter_employee(self, queryset, name, value):
        if not value:
            return queryset
        today = timezone.now().date()
        return queryset.filter(
            Q(route_assignments__employee__in=value) &
            (Q(route_assignments__date_end__isnull=True) | Q(route_assignments__date_end__gte=today))
        ).distinct()
