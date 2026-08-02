import django_filters
from django.db.models import Q
from django import forms
from datetime import date

from apps.sales.models import Route, RouteType, SaleChannel, RouteAssignment
from apps.human_resources.models import BusinessUnit, Employee


class RouteFilter(django_filters.FilterSet):
    '''
    The route list can be filtered by:
      - search: free text against id and name
      - business_unit: exact BU match
      - route_type: exact route type match
      - sale_channel: exact sale channel match
      - is_active: True/False against Route.is_active
      - employee: name match against the user assigned to an active RouteAssignment
    '''
    search = django_filters.CharFilter(
        method='filter_search',
        label='Buscar ruta',
        widget=forms.TextInput(attrs={'placeholder': 'ID o nombre de la ruta...'})
    )

    business_unit = django_filters.ModelChoiceFilter(
        field_name='business_unit',
        queryset=BusinessUnit.objects.all(),
        label='Gerencia',
        widget=forms.Select(attrs={'class': 'w-full bg-page border border-border rounded focus:outline-none focus:border-strong focus:ring-strong p-1 text-title'})
    )

    route_type = django_filters.ModelChoiceFilter(
        field_name='route_type',
        queryset=RouteType.objects.all(),
        label='Tipo de ruta',
        widget=forms.Select(attrs={'class': 'w-full bg-page border border-border rounded focus:outline-none focus:border-strong focus:ring-strong p-1 text-title'})
    )

    sale_channel = django_filters.ModelChoiceFilter(
        field_name='sale_channel',
        queryset=SaleChannel.objects.all(),
        label='Canal de venta',
        widget=forms.Select(attrs={'class': 'w-full bg-page border border-border rounded focus:outline-none focus:border-strong focus:ring-strong p-1 text-title'})
    )

    is_active = django_filters.BooleanFilter(
        method='filter_is_active',
        label='Ruta activa',
        widget=forms.Select(
            choices=[('', '---------'), ('true', 'Activa'), ('false', 'Inactiva')],
            attrs={'class': 'w-full bg-page border border-border rounded focus:outline-none focus:border-strong focus:ring-strong p-1 text-title'}
        )
    )

    employee = django_filters.CharFilter(
        method='filter_employee',
        label='Colaborador asignado',
        widget=forms.TextInput(attrs={'placeholder': 'Nombre o apellido...'})
    )

    class Meta:
        model = Route
        fields = ['search', 'business_unit', 'route_type', 'sale_channel', 'is_active', 'employee']

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(id__icontains=value) |
            Q(name__icontains=value)
        )

    def filter_is_active(self, queryset, name, value):
        if value is None:
            return queryset
        return queryset.filter(is_active=value)

    def filter_employee(self, queryset, name, value):
        today = date.today()
        active_route_ids = RouteAssignment.objects.filter(
            date_start__lte=today
        ).filter(
            Q(date_end__isnull=True) | Q(date_end__gte=today)
        ).filter(
            Q(employee__user__first_name__icontains=value) |
            Q(employee__user__last_name__icontains=value)
        ).values_list('route_id', flat=True)

        return queryset.filter(id__in=active_route_ids).distinct()
