import django_filters
from django import forms
from django.db.models import Q
from django.utils import timezone

from apps.human_resources.models import BusinessUnit
from apps.human_resources.services.business_units import BusinessUnitsService
from apps.sales.models import Route
from apps.sales.services.routes import RoutesService
from .models import Customer, CustomerType


class CustomerFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(
        method='filter_name',
        label='Cliente'
    )
    customer_type = django_filters.ModelMultipleChoiceFilter(
        field_name='customer_type',
        queryset=CustomerType.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label='Tipo de cliente'
    )
    route = django_filters.ModelMultipleChoiceFilter(
        method='filter_route',
        queryset=Route.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label='Ruta asignada'
    )
    business_unit = django_filters.ModelMultipleChoiceFilter(
        method='filter_business_unit',
        queryset=BusinessUnit.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label='Gerencia'
    )
    opinion_leader = django_filters.TypedMultipleChoiceFilter(
        choices=[('True', 'Líder de opinión'), ('False', 'Regular')],
        coerce=lambda x: x == 'True',
        widget=forms.CheckboxSelectMultiple,
        label='Líder de opinión'
    )
    registration_date_start = django_filters.DateFilter(
        field_name='registration_date',
        lookup_expr='gte',
        label='Fecha de registro (Desde)',
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    registration_date_end = django_filters.DateFilter(
        field_name='registration_date',
        lookup_expr='lte',
        label='Fecha de registro (Hasta)',
        widget=forms.DateInput(attrs={'type': 'date'})
    )

    class Meta:
        model = Customer
        fields = []

    def __init__(self, *args, **kwargs):
        request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        if request:
            self.filters['customer_type'].queryset = CustomerType.objects.all()
            self.filters['route'].queryset = RoutesService(user=request.user).read_routes()
            self.filters['business_unit'].queryset = BusinessUnitsService(user=request.user).read_business_units()

    def filter_name(self, queryset, name, value):
        return queryset.filter(
            Q(id__icontains=value) |
            Q(name__icontains=value)
        ).distinct()

    def filter_route(self, queryset, name, value):
        if not value:
            return queryset
        today = timezone.now().date()
        return queryset.filter(
            Q(assignments__route__in=value) &
            (Q(assignments__end_date__isnull=True) | Q(assignments__end_date__gte=today))
        ).distinct()

    def filter_business_unit(self, queryset, name, value):
        if not value:
            return queryset
        today = timezone.now().date()
        return queryset.filter(
            Q(assignments__route__business_unit__in=value) &
            (Q(assignments__end_date__isnull=True) | Q(assignments__end_date__gte=today))
        ).distinct()


class AccountsReceivableFilter(django_filters.FilterSet):
    PERSPECTIVE_CHOICES = (
        ('current_customers', 'Clientes asignados'),
        ('emitting_routes', 'Ruta emisora'),
    )

    search = django_filters.CharFilter(
        method='filter_search',
        label='Búsqueda general'
    )
    perspective = django_filters.ChoiceFilter(
        choices=PERSPECTIVE_CHOICES,
        label='Forma de visualización',
        method='filter_perspective',
        empty_label=None
    )
    issue_date_from = django_filters.DateFilter(
        field_name='issue_date',
        lookup_expr='gte',
        label='Fecha de emisión (Desde)',
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    issue_date_to = django_filters.DateFilter(
        field_name='issue_date',
        lookup_expr='lte',
        label='Fecha de emisión (Hasta)',
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    due_date_from = django_filters.DateFilter(
        field_name='due_date',
        lookup_expr='gte',
        label='Fecha de pago (Desde)',
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    due_date_to = django_filters.DateFilter(
        field_name='due_date',
        lookup_expr='lte',
        label='Fecha de pago (Hasta)',
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    route = django_filters.ModelMultipleChoiceFilter(
        field_name='route',
        queryset=Route.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label='Ruta'
    )
    business_unit = django_filters.ModelMultipleChoiceFilter(
        field_name='route__business_unit',
        queryset=BusinessUnit.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label='Gerencia'
    )
    customer = django_filters.ModelMultipleChoiceFilter(
        field_name='customer',
        queryset=Customer.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label='Cliente'
    )

    class Meta:
        from .models import AccountsReceivable
        model = AccountsReceivable
        fields = []

    def __init__(self, *args, **kwargs):
        request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        if request:
            self.filters['route'].queryset = RoutesService(user=request.user).read_routes()
            self.filters['business_unit'].queryset = BusinessUnitsService(user=request.user).read_business_units()
            self.filters['customer'].queryset = Customer.objects.all().order_by('name', 'id')

    def filter_perspective(self, queryset, name, value):
        return queryset

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(doc_id__icontains=value) |
            Q(description__icontains=value) |
            Q(customer__id__icontains=value) |
            Q(customer__name__icontains=value)
        ).distinct()
