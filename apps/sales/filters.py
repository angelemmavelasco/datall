import django_filters
from django import forms
from django.db.models import Q
from .models import Warehouse


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
