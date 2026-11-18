import django_filters
from django import forms
from django.db.models import Q

from apps.sales.models import Warehouse
from .models import Product, ProductCategory, ProductClass, PurchaseOrder


class ProductFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(
        method='filter_search',
        label='Producto'
    )
    product_category = django_filters.ModelMultipleChoiceFilter(
        field_name='product_class__product_category',
        queryset=ProductCategory.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label='Categoría'
    )
    product_class = django_filters.ModelMultipleChoiceFilter(
        field_name='product_class',
        queryset=ProductClass.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label='Clase de producto'
    )
    is_active = django_filters.TypedMultipleChoiceFilter(
        choices=[('True', 'Activo'), ('False', 'Inactivo')],
        coerce=lambda x: x == 'True',
        widget=forms.CheckboxSelectMultiple,
        label='Estatus'
    )

    class Meta:
        model = Product
        fields = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.filters['product_category'].queryset = ProductCategory.objects.all()
        self.filters['product_class'].queryset = ProductClass.objects.all()

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(id__icontains=value) |
            Q(name__icontains=value) |
            Q(barcode__icontains=value)
        ).distinct()


class PurchaseOrderFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(
        method='filter_search',
        label='Buscar orden'
    )
    status = django_filters.MultipleChoiceFilter(
        choices=PurchaseOrder.StatusChoices.choices,
        widget=forms.CheckboxSelectMultiple,
        label='Estatus'
    )
    origin_type = django_filters.MultipleChoiceFilter(
        choices=PurchaseOrder.OriginChoices.choices,
        widget=forms.CheckboxSelectMultiple,
        label='Origen'
    )
    warehouses = django_filters.ModelMultipleChoiceFilter(
        field_name='warehouses',
        queryset=Warehouse.objects.filter(warehouse_type=Warehouse.WarehouseTypeChoices.WAREHOUSE).exclude(id='snc').order_by('name'),
        widget=forms.CheckboxSelectMultiple,
        label='Centro de distribución'
    )

    class Meta:
        model = PurchaseOrder
        fields = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.filters['warehouses'].queryset = Warehouse.objects.filter(
            warehouse_type=Warehouse.WarehouseTypeChoices.WAREHOUSE
        ).exclude(id='snc').order_by('name')

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(folio__icontains=value) |
            Q(notes__icontains=value) |
            Q(created_by__username__icontains=value) |
            Q(created_by__first_name__icontains=value) |
            Q(created_by__last_name__icontains=value)
        ).distinct()
