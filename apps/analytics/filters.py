from typing import Any
import django_filters
from django import forms
from django.db.models import Min, Max, Q, QuerySet
from django.utils import timezone
from dateutil.relativedelta import relativedelta

from apps.sales.models import SaleTransaction, Route, Warehouse, SaleTarget
from apps.human_resources.models import BusinessUnit
from apps.customers.models import Customer, CustomerType, CustomerAssignment, AccountsReceivable
from apps.products.models import ProductClass, ProductCategory, Product, Stock
from apps.sales.services.routes import RoutesService
from apps.human_resources.services.business_units import BusinessUnitsService
from apps.customers.filters import AccountsReceivableFilter


class BusinessUnitMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj: BusinessUnit) -> str:
        return obj.name.title()


class BusinessUnitMultipleChoiceFilter(django_filters.ModelMultipleChoiceFilter):
    field_class = BusinessUnitMultipleChoiceField


class ProductClassMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj: ProductClass) -> str:
        return (obj.name or obj.id).title()


class ProductClassMultipleChoiceFilter(django_filters.ModelMultipleChoiceFilter):
    field_class = ProductClassMultipleChoiceField


class ProductCategoryMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj: ProductCategory) -> str:
        return (obj.name or obj.id).title()


class ProductCategoryMultipleChoiceFilter(django_filters.ModelMultipleChoiceFilter):
    field_class = ProductCategoryMultipleChoiceField


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
    region = BusinessUnitMultipleChoiceFilter(
        method='filter_region',
        queryset=BusinessUnit.objects.filter(business_unit_type=BusinessUnit.BusinessUnitTypeChoices.REGION),
        widget=forms.CheckboxSelectMultiple,
        label='Región'
    )
    business_unit = BusinessUnitMultipleChoiceFilter(
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
    product_category = ProductCategoryMultipleChoiceFilter(
        field_name='product_class__product_category',
        queryset=ProductCategory.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label='Categoría de producto'
    )
    product_class = ProductClassMultipleChoiceFilter(
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
            user = request.user if hasattr(request, 'user') else request
            bu_service = BusinessUnitsService(user=user)
            self.filters['region'].queryset = bu_service.read_regions()
            self.filters['business_unit'].queryset = bu_service.read_units()
            self.filters['route'].queryset = RoutesService(user=user).read_routes().order_by('id')
            self.filters['customer'].queryset = Customer.objects.all().order_by('name', 'id')
            self.filters['product_category'].queryset = ProductCategory.objects.all().order_by('name', 'id')
            self.filters['product_class'].queryset = ProductClass.objects.all().order_by('name', 'id')

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


class CustomerKpisFilter(django_filters.FilterSet):
    customer = django_filters.CharFilter(
        method='filter_customer',
        label='Cliente'
    )
    name = django_filters.CharFilter(
        method='filter_name',
        label='Cliente'
    )
    region = BusinessUnitMultipleChoiceFilter(
        method='filter_region',
        queryset=BusinessUnit.objects.filter(business_unit_type=BusinessUnit.BusinessUnitTypeChoices.REGION),
        widget=forms.CheckboxSelectMultiple,
        label='Región'
    )
    business_unit = BusinessUnitMultipleChoiceFilter(
        method='filter_business_unit',
        queryset=BusinessUnit.objects.filter(business_unit_type=BusinessUnit.BusinessUnitTypeChoices.UNIT),
        widget=forms.CheckboxSelectMultiple,
        label='Gerencia'
    )
    route = django_filters.ModelMultipleChoiceFilter(
        method='filter_route',
        queryset=Route.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label='Ruta'
    )
    customer_type = django_filters.ModelMultipleChoiceFilter(
        field_name='customer_type',
        queryset=CustomerType.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label='Tipo de cliente'
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
    order_contrib = django_filters.ChoiceFilter(
        choices=[('net_amount', 'Venta neta'), ('profit', 'Utilidad')],
        label='Ordenar contribución por',
        method='filter_noop',
        empty_label=None,
        null_label=None,
    )
    start_contrib = django_filters.DateFilter(
        label='Contribución desde',
        method='filter_noop',
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    end_contrib = django_filters.DateFilter(
        label='Contribución hasta',
        method='filter_noop',
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    contrib_min_op = django_filters.ChoiceFilter(
        choices=[('gte', '≥'), ('gt', '>')],
        method='filter_noop',
        label='Operador mínimo',
        empty_label=None,
        null_label=None,
        initial='gte',
    )
    contrib_min_amount = django_filters.NumberFilter(
        method='filter_noop',
        label='Contribución mínima',
        widget=forms.NumberInput(attrs={'step': 'any', 'placeholder': '0.00'})
    )
    contrib_max_op = django_filters.ChoiceFilter(
        choices=[('lte', '≤'), ('lt', '<')],
        method='filter_noop',
        label='Operador máximo',
        empty_label=None,
        null_label=None,
        initial='lte',
    )
    contrib_max_amount = django_filters.NumberFilter(
        method='filter_noop',
        label='Contribución máxima',
        widget=forms.NumberInput(attrs={'step': 'any', 'placeholder': 'Sin tope'})
    )
    has_purchases = django_filters.TypedChoiceFilter(
        choices=[('True', 'Con compras'), ('False', 'Sin compras')],
        coerce=lambda x: x == 'True',
        method='filter_has_purchases',
        label='Con compras en el periodo',
        widget=forms.HiddenInput
    )

    def filter_has_purchases(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        if value is None:
            return queryset
        start_date = self.data.get('start_contrib') or self.data.get('date_start')
        end_date = self.data.get('end_contrib') or self.data.get('date_end')

        tx_filter = Q()
        if start_date:
            tx_filter &= Q(sale_transactions__sale_date__gte=start_date)
        if end_date:
            tx_filter &= Q(sale_transactions__sale_date__lte=end_date)

        if value:
            return queryset.filter(tx_filter).distinct()
        else:
            return queryset.exclude(tx_filter).distinct()

    def filter_noop(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        """Filtro no-op para parámetros de configuración que no filtran directamente a Customer."""
        return queryset

    class Meta:
        model = Customer
        fields = []

    def __init__(self, *args, **kwargs):
        request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        if request:
            user = request.user if hasattr(request, 'user') else request
            bu_service = BusinessUnitsService(user=user)
            self.filters['region'].queryset = bu_service.read_regions()
            self.filters['business_unit'].queryset = bu_service.read_units()
            self.filters['route'].queryset = RoutesService(user=user).read_routes().order_by('id')
            self.filters['customer_type'].queryset = CustomerType.objects.all().order_by('name', 'id')

    def filter_customer(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        if not value:
            return queryset
        if self.request:
            raw_list = self.request.GET.getlist('customer')
            if len(raw_list) > 1:
                return queryset.filter(id__in=raw_list)
        if isinstance(value, str):
            ids = [v.strip() for v in value.split(',') if v.strip()]
            return queryset.filter(id__in=ids)
        return queryset.filter(id__in=value if isinstance(value, (list, tuple)) else [value])

    def filter_name(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        if not value:
            return queryset
        return queryset.filter(
            Q(id__icontains=value) | Q(name__icontains=value)
        ).distinct()

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

        today = timezone.now().date()
        return queryset.filter(
            Q(assignments__route__business_unit_id__in=all_bu_ids) &
            (Q(assignments__end_date__isnull=True) | Q(assignments__end_date__gte=today))
        ).distinct()

    def filter_business_unit(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        if not value:
            return queryset

        today = timezone.now().date()
        bu_ids = [bu.pk if hasattr(bu, 'pk') else bu for bu in value]
        return queryset.filter(
            Q(assignments__route__business_unit_id__in=bu_ids) &
            (Q(assignments__end_date__isnull=True) | Q(assignments__end_date__gte=today))
        ).distinct()

    def filter_route(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        if not value:
            return queryset

        today = timezone.now().date()
        return queryset.filter(
            Q(assignments__route__in=value) &
            (Q(assignments__end_date__isnull=True) | Q(assignments__end_date__gte=today))
        ).distinct()


class RouteKpisFilter(django_filters.FilterSet):
    route = django_filters.ModelChoiceFilter(
        queryset=Route.objects.all(),
        widget=forms.RadioSelect,
        label='Ruta',
        empty_label=None,
    )
    date_start = django_filters.DateFilter(
        label='Fecha inicio',
        method='filter_noop',
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    date_end = django_filters.DateFilter(
        label='Fecha fin',
        method='filter_noop',
        widget=forms.DateInput(attrs={'type': 'date'})
    )

    def filter_noop(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        return queryset

    class Meta:
        model = Route
        fields = []

    def __init__(self, *args, **kwargs):
        request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        if request:
            user = request.user if hasattr(request, 'user') else request
            self.filters['route'].queryset = RoutesService(user=user).read_routes().order_by('id')


class CommercialRiskFilter(django_filters.FilterSet):
    route = django_filters.ModelChoiceFilter(
        queryset=Route.objects.all(),
        widget=forms.RadioSelect,
        label='Ruta',
        empty_label=None,
    )
    date_start = django_filters.DateFilter(
        label='Fecha inicio',
        method='filter_noop',
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    date_end = django_filters.DateFilter(
        label='Fecha fin',
        method='filter_noop',
        widget=forms.DateInput(attrs={'type': 'date'})
    )

    def filter_noop(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        return queryset

    class Meta:
        model = Route
        fields = []

    def __init__(self, *args, **kwargs):
        request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        if request:
            user = request.user if hasattr(request, 'user') else request
            self.filters['route'].queryset = RoutesService(user=user).read_routes().order_by('id')

CollectionsDashboardFilter = AccountsReceivableFilter


class TargetAchievementFilter(django_filters.FilterSet):
    date_start = django_filters.DateFilter(
        field_name='period',
        lookup_expr='gte',
        label='Fecha inicio',
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    date_end = django_filters.DateFilter(
        field_name='period',
        lookup_expr='lte',
        label='Fecha fin',
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    region = BusinessUnitMultipleChoiceFilter(
        method='filter_region',
        queryset=BusinessUnit.objects.filter(business_unit_type=BusinessUnit.BusinessUnitTypeChoices.REGION),
        widget=forms.CheckboxSelectMultiple,
        label='Región'
    )
    business_unit = BusinessUnitMultipleChoiceFilter(
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
    product_category = ProductCategoryMultipleChoiceFilter(
        field_name='product_class__product_category',
        queryset=ProductCategory.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label='Categoría de producto'
    )
    product_class = ProductClassMultipleChoiceFilter(
        field_name='product_class',
        queryset=ProductClass.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label='Clase de producto'
    )

    class Meta:
        model = SaleTarget
        fields = []

    def __init__(self, *args, **kwargs):
        request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        if request:
            user = request.user if hasattr(request, 'user') else request
            bu_service = BusinessUnitsService(user=user)
            self.filters['region'].queryset = bu_service.read_regions()
            self.filters['business_unit'].queryset = bu_service.read_units()
            self.filters['route'].queryset = RoutesService(user=user).read_routes().order_by('id')
            self.filters['product_category'].queryset = ProductCategory.objects.all().order_by('name', 'id')
            self.filters['product_class'].queryset = ProductClass.objects.all().order_by('name', 'id')

    def filter_region(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        if not value:
            return queryset
        selected_region_ids = set(r.pk if hasattr(r, 'pk') else r for r in value)
        all_bu_ids = set(selected_region_ids)
        current_parents = set(selected_region_ids)
        while current_parents:
            child_ids = set(
                BusinessUnit.objects.filter(parent_id__in=current_parents).values_list('id', flat=True)
            )
            new_ids = child_ids - all_bu_ids
            if not new_ids:
                break
            all_bu_ids.update(new_ids)
            current_parents = new_ids
        return queryset.filter(
            Q(route__business_unit_id__in=all_bu_ids) | Q(business_unit_id__in=all_bu_ids)
        ).distinct()

    def filter_business_unit(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        if not value:
            return queryset
        bu_ids = [bu.pk if hasattr(bu, 'pk') else bu for bu in value]
        return queryset.filter(
            Q(route__business_unit_id__in=bu_ids) | Q(business_unit_id__in=bu_ids)
        ).distinct()


CUSTOMER_ASSIGNMENT_DIMENSIONS = (
    'customer_productclass_product',
    'productclass_customer_product',
    'product_customer',
)


class YearlySaleBreakdownFilter(django_filters.FilterSet):
    DIMENSION_CHOICES = [
        ('customer_productclass_product', 'Cliente → Clase de producto → Producto'),
        ('productclass_product', 'Clase de producto → Producto'),
        ('productclass_customer_product', 'Clase de producto → Cliente → Producto'),
        ('management_productclass_product', 'Gerencia → Clase de producto → Producto'),
        ('management_route_productclass_product', 'Gerencia → Ruta → Clase de producto → Producto'),
        ('route_productclass_product', 'Ruta → Clase de producto → Producto'),
        ('product_customer', 'Producto → Cliente'),
        ('product_management', 'Producto → Gerencia'),
        ('product_route', 'Producto → Ruta'),
    ]

    MONTH_CHOICES = [
        ('1', 'Enero'),
        ('2', 'Febrero'),
        ('3', 'Marzo'),
        ('4', 'Abril'),
        ('5', 'Mayo'),
        ('6', 'Junio'),
        ('7', 'Julio'),
        ('8', 'Agosto'),
        ('9', 'Septiembre'),
        ('10', 'Octubre'),
        ('11', 'Noviembre'),
        ('12', 'Diciembre'),
    ]

    dimension = django_filters.ChoiceFilter(
        choices=DIMENSION_CHOICES,
        label='Dimensión de visualización',
        widget=forms.RadioSelect,
        method='filter_noop',
        empty_label=None,
        null_label=None,
        initial='customer_productclass_product',
    )
    year = django_filters.MultipleChoiceFilter(
        choices=[],
        method='filter_year',
        widget=forms.CheckboxSelectMultiple,
        label='Año',
    )
    months = django_filters.MultipleChoiceFilter(
        choices=MONTH_CHOICES,
        method='filter_months',
        widget=forms.CheckboxSelectMultiple,
        label='Meses a comparar',
    )
    region = BusinessUnitMultipleChoiceFilter(
        method='filter_region',
        queryset=BusinessUnit.objects.filter(business_unit_type=BusinessUnit.BusinessUnitTypeChoices.REGION),
        widget=forms.CheckboxSelectMultiple,
        label='Región'
    )
    business_unit = BusinessUnitMultipleChoiceFilter(
        method='filter_business_unit',
        queryset=BusinessUnit.objects.filter(business_unit_type=BusinessUnit.BusinessUnitTypeChoices.UNIT),
        widget=forms.CheckboxSelectMultiple,
        label='Gerencia'
    )
    route = django_filters.ModelMultipleChoiceFilter(
        method='filter_route',
        queryset=Route.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label='Ruta'
    )
    product_category = ProductCategoryMultipleChoiceFilter(
        field_name='product_class__product_category',
        queryset=ProductCategory.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label='Categoría de producto'
    )
    product_class = ProductClassMultipleChoiceFilter(
        field_name='product_class',
        queryset=ProductClass.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label='Clase de producto'
    )

    class Meta:
        model = SaleTransaction
        fields = []

    def __init__(self, *args, **kwargs):
        request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)

        today_year = timezone.localdate().year
        qs = self.queryset if self.queryset is not None else SaleTransaction.objects.all()
        dates = qs.order_by().aggregate(
            min_date=Min('sale_date'),
            max_date=Max('sale_date'),
        )
        min_date = dates.get('min_date')
        max_date = dates.get('max_date')
        if min_date and max_date:
            min_year = min_date.year
            max_year = max_date.year
            year_choices = [(str(y), str(y)) for y in range(min_year, max_year + 1)]
        else:
            year_choices = [(str(y), str(y)) for y in range(today_year - 4, today_year + 1)]

        self.filters['year'].extra['choices'] = year_choices
        if hasattr(self, '_form') and self._form is not None and 'year' in self._form.fields:
            self._form.fields['year'].choices = year_choices

        if hasattr(self, 'data') and self.data:
            if 'years' in self.data and 'year' not in self.data:
                if hasattr(self.data, 'setlist'):
                    self.data = self.data.copy()
                    self.data.setlist('year', self.data.getlist('years'))
                elif isinstance(self.data, dict):
                    self.data = dict(self.data)
                    self.data['year'] = self.data['years']

        if request:
            user = request.user if hasattr(request, 'user') else request
            bu_service = BusinessUnitsService(user=user)
            self.filters['region'].queryset = bu_service.read_regions()
            self.filters['business_unit'].queryset = bu_service.read_units()
            self.filters['route'].queryset = RoutesService(user=user).read_routes().order_by('id')
            self.filters['product_category'].queryset = ProductCategory.objects.all().order_by('name', 'id')
            self.filters['product_class'].queryset = ProductClass.objects.all().order_by('name', 'id')

    def filter_noop(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        return queryset

    def filter_year(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        if not value:
            return queryset
        if isinstance(value, (str, int)):
            value = [value]
        year_ints = [int(v) for v in value if str(v).isdigit()]
        if year_ints:
            return queryset.filter(sale_date__year__in=year_ints)
        return queryset

    def filter_months(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        if not value:
            return queryset
        month_ints = [int(v) for v in value if str(v).isdigit()]
        if month_ints:
            return queryset.filter(sale_date__month__in=month_ints)
        return queryset

    def filter_region(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        if not value:
            return queryset
        selected_region_ids = set(r.pk if hasattr(r, 'pk') else r for r in value)
        all_bu_ids = set(selected_region_ids)
        current_parents = set(selected_region_ids)
        while current_parents:
            child_ids = set(
                BusinessUnit.objects.filter(parent_id__in=current_parents).values_list('id', flat=True)
            )
            new_ids = child_ids - all_bu_ids
            if not new_ids:
                break
            all_bu_ids.update(new_ids)
            current_parents = new_ids

        dim = self.data.get('dimension') if self.data else None
        if isinstance(dim, list):
            dim = dim[0] if dim else None
        dim = dim or 'customer_productclass_product'

        if dim in CUSTOMER_ASSIGNMENT_DIMENSIONS:
            today = timezone.localdate()
            customer_ids = CustomerAssignment.objects.filter(
                route__business_unit_id__in=all_bu_ids
            ).filter(
                Q(end_date__isnull=True) | Q(end_date__gte=today)
            ).values('customer_id')
            return queryset.filter(customer_id__in=customer_ids)

        return queryset.filter(route__business_unit_id__in=all_bu_ids)

    def filter_business_unit(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        if not value:
            return queryset
        bu_ids = [bu.pk if hasattr(bu, 'pk') else bu for bu in value]

        dim = self.data.get('dimension') if self.data else None
        if isinstance(dim, list):
            dim = dim[0] if dim else None
        dim = dim or 'customer_productclass_product'

        if dim in CUSTOMER_ASSIGNMENT_DIMENSIONS:
            today = timezone.localdate()
            customer_ids = CustomerAssignment.objects.filter(
                route__business_unit_id__in=bu_ids
            ).filter(
                Q(end_date__isnull=True) | Q(end_date__gte=today)
            ).values('customer_id')
            return queryset.filter(customer_id__in=customer_ids)

        return queryset.filter(route__business_unit_id__in=bu_ids)

    def filter_route(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        if not value:
            return queryset

        dim = self.data.get('dimension') if self.data else None
        if isinstance(dim, list):
            dim = dim[0] if dim else None
        dim = dim or 'customer_productclass_product'

        if dim in CUSTOMER_ASSIGNMENT_DIMENSIONS:
            today = timezone.localdate()
            customer_ids = CustomerAssignment.objects.filter(
                route__in=value
            ).filter(
                Q(end_date__isnull=True) | Q(end_date__gte=today)
            ).values('customer_id')
            return queryset.filter(customer_id__in=customer_ids)

        return queryset.filter(route__in=value)


class MonthlySaleBreakdownFilter(django_filters.FilterSet):
    year = django_filters.ChoiceFilter(
        label='Año',
        widget=forms.RadioSelect,
        method='filter_noop',
        empty_label=None,
        null_label=None,
    )
    region = BusinessUnitMultipleChoiceFilter(
        method='filter_region',
        queryset=BusinessUnit.objects.filter(business_unit_type=BusinessUnit.BusinessUnitTypeChoices.REGION),
        widget=forms.CheckboxSelectMultiple,
        label='Región'
    )
    business_unit = BusinessUnitMultipleChoiceFilter(
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
    product_category = ProductCategoryMultipleChoiceFilter(
        field_name='product_class__product_category',
        queryset=ProductCategory.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label='Categoría de producto'
    )
    product_class = ProductClassMultipleChoiceFilter(
        field_name='product_class',
        queryset=ProductClass.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label='Clase de producto'
    )

    class Meta:
        model = SaleTransaction
        fields = []

    def __init__(self, *args, **kwargs):
        request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)

        today_year = timezone.localdate().year
        # get distinct years from SaleTransaction or generate range
        years = list(SaleTransaction.objects.dates('sale_date', 'year', order='DESC'))
        year_choices = [(str(d.year), str(d.year)) for d in years] if years else []
        if not year_choices:
            year_choices = [(str(y), str(y)) for y in range(today_year, today_year - 5, -1)]
        elif str(today_year) not in [c[0] for c in year_choices]:
            year_choices.insert(0, (str(today_year), str(today_year)))

        self.filters['year'].extra['choices'] = year_choices

        if request:
            user = request.user if hasattr(request, 'user') else request
            bu_service = BusinessUnitsService(user=user)
            self.filters['region'].queryset = bu_service.read_regions()
            self.filters['business_unit'].queryset = bu_service.read_units()
            self.filters['route'].queryset = RoutesService(user=user).read_routes().order_by('id')
            self.filters['product_category'].queryset = ProductCategory.objects.all().order_by('name', 'id')
            self.filters['product_class'].queryset = ProductClass.objects.all().order_by('name', 'id')

    def filter_noop(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        return queryset

    def filter_region(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        if not value:
            return queryset
        selected_region_ids = set(r.pk if hasattr(r, 'pk') else r for r in value)
        all_bu_ids = set(selected_region_ids)
        current_parents = set(selected_region_ids)
        while current_parents:
            child_ids = set(
                BusinessUnit.objects.filter(parent_id__in=current_parents).values_list('id', flat=True)
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


class CustomerProfileFilter(django_filters.FilterSet):
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
    region = BusinessUnitMultipleChoiceFilter(
        method='filter_region',
        queryset=BusinessUnit.objects.filter(business_unit_type=BusinessUnit.BusinessUnitTypeChoices.REGION),
        widget=forms.CheckboxSelectMultiple,
        label='Región'
    )
    business_unit = BusinessUnitMultipleChoiceFilter(
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
    product_category = ProductCategoryMultipleChoiceFilter(
        field_name='product_class__product_category',
        queryset=ProductCategory.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label='Categoría de producto'
    )
    product_class = ProductClassMultipleChoiceFilter(
        field_name='product_class',
        queryset=ProductClass.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label='Clase de producto'
    )

    class Meta:
        model = SaleTransaction
        fields = []

    def __init__(self, *args, **kwargs):
        request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        if request:
            user = request.user if hasattr(request, 'user') else request
            bu_service = BusinessUnitsService(user=user)
            self.filters['region'].queryset = bu_service.read_regions()
            self.filters['business_unit'].queryset = bu_service.read_units()
            self.filters['route'].queryset = RoutesService(user=user).read_routes().order_by('id')
            self.filters['product_category'].queryset = ProductCategory.objects.all().order_by('name', 'id')
            self.filters['product_class'].queryset = ProductClass.objects.all().order_by('name', 'id')

    def filter_region(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        if not value:
            return queryset
        selected_region_ids = set(r.pk if hasattr(r, 'pk') else r for r in value)
        all_bu_ids = set(selected_region_ids)
        current_parents = set(selected_region_ids)
        while current_parents:
            child_ids = set(
                BusinessUnit.objects.filter(parent_id__in=current_parents).values_list('id', flat=True)
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


class WarehouseMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj: Warehouse) -> str:
        return f"{obj.name.title()} - {obj.get_warehouse_type_display().title()}"


class WarehouseMultipleChoiceFilter(django_filters.ModelMultipleChoiceFilter):
    field_class = WarehouseMultipleChoiceField


class ProductMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj: Product) -> str:
        return f"{obj.id.upper()} - {obj.name.title()}"


class ProductMultipleChoiceFilter(django_filters.ModelMultipleChoiceFilter):
    field_class = ProductMultipleChoiceField


class StockBreakdownFilter(django_filters.FilterSet):
    DIMENSION_CHOICES = [
        ('productcategory_productclass_product', 'Categoría de producto → Clase de producto → Producto → Lote'),
    ]

    EXPIRATION_STATUS_CHOICES = [
        ('all', 'Todos'),
        ('expired', 'Caducos'),
        ('not_expired', 'No caducos'),
    ]

    EXPIRATION_BUCKET_CHOICES = [
        ('0_2', 'Caducan 0 - 2 meses'),
        ('3_4', 'Caducan 3 - 4 meses'),
        ('5_6', 'Caducan 5 - 6 meses'),
        ('6_plus', 'Caducan +6 meses'),
    ]

    dimension = django_filters.ChoiceFilter(
        choices=DIMENSION_CHOICES,
        label='Dimensión de visualización',
        widget=forms.RadioSelect,
        method='filter_noop',
        empty_label=None,
        null_label=None,
        initial='productcategory_productclass_product',
    )
    expiration_status = django_filters.ChoiceFilter(
        choices=EXPIRATION_STATUS_CHOICES,
        label='Estado de caducidad',
        widget=forms.RadioSelect,
        method='filter_expiration_status',
        empty_label=None,
        null_label=None,
        initial='all',
    )
    expiration_buckets = django_filters.MultipleChoiceFilter(
        choices=EXPIRATION_BUCKET_CHOICES,
        label='Periodo de caducidad',
        widget=forms.CheckboxSelectMultiple,
        method='filter_expiration_buckets',
    )
    expiration_date_from = django_filters.DateFilter(
        field_name='expiration_date',
        lookup_expr='gte',
        label='Caduca desde',
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    expiration_date_to = django_filters.DateFilter(
        field_name='expiration_date',
        lookup_expr='lte',
        label='Caduca hasta',
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    warehouse = WarehouseMultipleChoiceFilter(
        queryset=Warehouse.objects.all(),
        method='filter_warehouse',
        widget=forms.CheckboxSelectMultiple,
        label='Centro de distribución'
    )
    product_category = ProductCategoryMultipleChoiceFilter(
        field_name='product__product_class__product_category',
        queryset=ProductCategory.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label='Categoría de producto'
    )
    product_class = ProductClassMultipleChoiceFilter(
        field_name='product__product_class',
        queryset=ProductClass.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label='Clase de producto'
    )
    product = ProductMultipleChoiceFilter(
        field_name='product',
        queryset=Product.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label='Producto'
    )

    class Meta:
        model = Stock
        fields = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.filters['warehouse'].queryset = Warehouse.objects.all().order_by('warehouse_type', 'name')
        self.filters['product_category'].queryset = ProductCategory.objects.all().order_by('name', 'id')
        self.filters['product_class'].queryset = ProductClass.objects.all().order_by('name', 'id')
        self.filters['product'].queryset = Product.objects.all().order_by('name', 'id')

        if self.data is not None and 'warehouse' not in self.data:
            default_wh_pks = list(
                Warehouse.objects.filter(warehouse_type=Warehouse.WarehouseTypeChoices.WAREHOUSE)
                .values_list('pk', flat=True)
            )
            if hasattr(self.data, 'setlist'):
                self.data = self.data.copy()
                self.data.setlist('warehouse', default_wh_pks)
            elif isinstance(self.data, dict):
                self.data = dict(self.data)
                self.data['warehouse'] = default_wh_pks

    def filter_noop(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        return queryset

    def filter_warehouse(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        if not value:
            return queryset
        wh_ids = [w.pk if hasattr(w, 'pk') else w for w in value]
        return queryset.filter(warehouse_id__in=wh_ids)

    def filter_expiration_status(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        if not value or value in ('all', 'todos'):
            return queryset
        today = timezone.localdate()
        if value in ('expired', 'caducos'):
            return queryset.filter(expiration_date__isnull=False, expiration_date__lte=today)
        if value in ('not_expired', 'no_caducos'):
            return queryset.filter(Q(expiration_date__gt=today) | Q(expiration_date__isnull=True))
        return queryset

    def filter_expiration_buckets(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        if not value:
            return queryset

        today = timezone.localdate()
        m0_start = today.replace(day=1)

        start_1 = m0_start
        end_1 = (m0_start + relativedelta(months=2)) - relativedelta(days=1)
        start_2 = m0_start + relativedelta(months=2)
        end_2 = (m0_start + relativedelta(months=4)) - relativedelta(days=1)
        start_3 = m0_start + relativedelta(months=4)
        end_3 = (m0_start + relativedelta(months=6)) - relativedelta(days=1)
        start_4 = m0_start + relativedelta(months=6)

        q_filter = Q()
        for val in value:
            if val == '0_2':
                q_filter |= Q(expiration_date__isnull=False, expiration_date__gte=start_1, expiration_date__lte=end_1)
            elif val == '3_4':
                q_filter |= Q(expiration_date__isnull=False, expiration_date__gte=start_2, expiration_date__lte=end_2)
            elif val == '5_6':
                q_filter |= Q(expiration_date__isnull=False, expiration_date__gte=start_3, expiration_date__lte=end_3)
            elif val == '6_plus':
                q_filter |= Q(expiration_date__isnull=False, expiration_date__gte=start_4)

        return queryset.filter(q_filter)




