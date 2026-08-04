import django_filters
from django import forms
from apps.core.models import SaleTransaction, Route, Warehouse, Region, ProductCategory, ProductClass, Product, Customer

class ProductKPIFilter(django_filters.FilterSet):
    date_start = django_filters.DateFilter(
        field_name='sale_date', 
        lookup_expr='gte',
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    date_end = django_filters.DateFilter(
        field_name='sale_date', 
        lookup_expr='lte',
        widget=forms.DateInput(attrs={'type': 'date'})
    )

    route = django_filters.ModelMultipleChoiceFilter(
        queryset=Route.objects.filter(is_active=True),
        field_name='route'
    )

    warehouse = django_filters.ModelMultipleChoiceFilter(
        queryset=Warehouse.objects.all(),
        field_name='route__warehouse'
    )
    
    region = django_filters.ModelMultipleChoiceFilter(
        queryset=Region.objects.all(),
        field_name='route__warehouse__region'
    )

    product_category = django_filters.ModelMultipleChoiceFilter(
        queryset=ProductCategory.objects.all(),
        field_name='product_class__product_category'
    )

    product_class = django_filters.ModelMultipleChoiceFilter(
        queryset=ProductClass.objects.all(),
        field_name='product_class'
    )

    product = django_filters.ModelMultipleChoiceFilter(
        queryset=Product.objects.all(),
        field_name='product',
        widget=forms.SelectMultiple()
    )

    customer = django_filters.ModelMultipleChoiceFilter(
        queryset=Customer.objects.all(),
        field_name='customer'
    )

    class Meta:
        model = SaleTransaction
        fields = ['date_start', 'date_end', 'route', 'warehouse', 'region', 'product_category', 'product_class', 'product', 'customer']

