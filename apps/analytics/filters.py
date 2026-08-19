from typing import Any
import django_filters
from django import forms
from django.db.models import Q, QuerySet

from apps.sales.models import SaleTransaction, Route, Warehouse
from apps.human_resources.models import BusinessUnit
from apps.customers.models import Customer
from apps.products.models import ProductClass
from apps.sales.services.routes import RoutesService
from apps.human_resources.services.business_units import BusinessUnitsService


class SalesDashboardFilter(django_filters.FilterSet):
    date_start = django_filters.DateFilter(
        field_name='sale_date',
        lookup_expr='gte',
        label='Fecha inicio',
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    date_end = django_filters.DateFilter(
        field_name='sale_date',
        lookup_expr='lte',
        label='Fecha fin',
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    region = django_filters.ModelMultipleChoiceFilter(
        method='filter_region',
        queryset=BusinessUnit.objects.filter(business_unit_type=BusinessUnit.BusinessUnitTypeChoices.REGION),
        widget=forms.CheckboxSelectMultiple,
        label='Región'
    )
    business_unit = django_filters.ModelMultipleChoiceFilter(
        method='filter_business_unit',
        queryset=BusinessUnit.objects.filter(business_unit_type=BusinessUnit.BusinessUnitTypeChoices.UNIT),
        widget=forms.CheckboxSelectMultiple,
        label='Gerencia'
    )
    route = django_filters.ModelMultipleChoiceFilter(
        field_name='route',
        queryset=Route.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label='Ruta'
    )
    warehouse = django_filters.ModelMultipleChoiceFilter(
        field_name='warehouse',
        queryset=Warehouse.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label='Centro de distribución (Lugar de venta)'
    )
    product_class = django_filters.ModelMultipleChoiceFilter(
        field_name='product_class',
        queryset=ProductClass.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label='Clase de producto'
    )
    customer = django_filters.ModelMultipleChoiceFilter(
        field_name='customer',
        queryset=Customer.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label='Cliente'
    )

    class Meta:
        model = SaleTransaction
        fields = []

    def __init__(self, *args, **kwargs):
        request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        if request:
            bu_service = BusinessUnitsService(user=request.user)
            self.filters['region'].queryset = bu_service.read_regions()
            self.filters['business_unit'].queryset = bu_service.read_units()
            self.filters['route'].queryset = RoutesService(user=request.user).read_routes()
            self.filters['warehouse'].queryset = Warehouse.objects.all()
            self.filters['customer'].queryset = Customer.objects.all().order_by('name', 'id')
            self.filters['product_class'].queryset = ProductClass.objects.all()

    def filter_region(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        if not value:
            return queryset

        selected_region_ids = set(r.pk if hasattr(r, 'pk') else r for r in value)
        all_bu_ids = set(selected_region_ids)

        current_parents = set(selected_region_ids)
        while current_parents:
            child_ids = set(
                BusinessUnit.objects.filter(parent_id__in=current_parents)
                .values_list('id', flat=True)
            )
            new_ids = child_ids - all_bu_ids
            if not new_ids:
                break
            all_bu_ids.update(new_ids)
            current_parents = new_ids
        return queryset.filter(route__business_unit_id__in=all_bu_ids)

    def filter_business_unit(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        if not value:
            return queryset

        bu_ids = [bu.pk if hasattr(bu, 'pk') else bu for bu in value]
        return queryset.filter(route__business_unit_id__in=bu_ids)
