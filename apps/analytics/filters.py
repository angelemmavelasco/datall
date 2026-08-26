from typing import Any
import django_filters
from django import forms
from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.sales.models import SaleTransaction, Route, Warehouse, SaleTarget
from apps.human_resources.models import BusinessUnit
from apps.customers.models import Customer, CustomerType, CustomerAssignment, AccountsReceivable
from apps.products.models import ProductClass, ProductCategory
from apps.sales.services.routes import RoutesService
from apps.human_resources.services.business_units import BusinessUnitsService


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
            bu_service = BusinessUnitsService(user=request.user)
            self.filters['region'].queryset = bu_service.read_regions()
            self.filters['business_unit'].queryset = bu_service.read_units()
            self.filters['route'].queryset = RoutesService(user=request.user).read_routes()
            self.filters['customer'].queryset = Customer.objects.all().order_by('name', 'id')
            self.filters['product_category'].queryset = ProductCategory.objects.all()
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
            bu_service = BusinessUnitsService(user=request.user)
            self.filters['region'].queryset = bu_service.read_regions()
            self.filters['business_unit'].queryset = bu_service.read_units()
            self.filters['route'].queryset = RoutesService(user=request.user).read_routes()
            self.filters['customer_type'].queryset = CustomerType.objects.all()

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
            self.filters['route'].queryset = RoutesService(user=request.user).read_routes().order_by('id')


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
            self.filters['route'].queryset = RoutesService(user=request.user).read_routes().order_by('id')


class CollectionsDashboardFilter(django_filters.FilterSet):
    PERSPECTIVE_CHOICES = (
        ('current_customers', 'Clientes asignados'),
        ('emitting_routes', 'Ruta emisora'),
    )

    AGING_CHOICES = (
        ('current', 'Al corriente'),
        ('overdue', 'Con saldo vencido'),
        ('1_15', 'De 1 a 15 días'),
        ('16_30', 'De 16 a 30 días'),
        ('31_60', 'De 31 a 60 días'),
        ('past_due', 'Mayor a 60 días'),
    )

    search = django_filters.CharFilter(
        method='filter_search',
        label='Búsqueda general'
    )
    customer_search = django_filters.CharFilter(
        method='filter_customer_search',
        label='Buscar cliente'
    )
    perspective = django_filters.ChoiceFilter(
        choices=PERSPECTIVE_CHOICES,
        method='filter_perspective',
        label='Forma de visualización',
        empty_label=None
    )
    aging_status = django_filters.MultipleChoiceFilter(
        choices=AGING_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        label='Estatus de saldo',
        method='filter_aging_status'
    )
    issue_date_start = django_filters.DateFilter(
        field_name='issue_date',
        lookup_expr='gte',
        label='Fecha de emisión (Desde)',
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    issue_date_end = django_filters.DateFilter(
        field_name='issue_date',
        lookup_expr='lte',
        label='Fecha de emisión (Hasta)',
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    due_date_start = django_filters.DateFilter(
        field_name='due_date',
        lookup_expr='gte',
        label='Fecha de pago (Desde)',
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    due_date_end = django_filters.DateFilter(
        field_name='due_date',
        lookup_expr='lte',
        label='Fecha de pago (Hasta)',
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    business_unit = BusinessUnitMultipleChoiceFilter(
        method='filter_business_unit',
        queryset=BusinessUnit.objects.filter(business_unit_type=BusinessUnit.BusinessUnitTypeChoices.UNIT),
        widget=forms.CheckboxSelectMultiple,
        label='Gerencia'
    )
    region = BusinessUnitMultipleChoiceFilter(
        method='filter_region',
        queryset=BusinessUnit.objects.filter(business_unit_type=BusinessUnit.BusinessUnitTypeChoices.REGION),
        widget=forms.CheckboxSelectMultiple,
        label='Región'
    )
    route = django_filters.ModelMultipleChoiceFilter(
        method='filter_route',
        queryset=Route.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label='Ruta'
    )
    customer = django_filters.ModelMultipleChoiceFilter(
        field_name='customer',
        queryset=Customer.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label='Cliente'
    )

    class Meta:
        model = AccountsReceivable
        fields = []

    def __init__(self, *args, **kwargs):
        request = kwargs.pop('request', None)
        self.request = request
        super().__init__(*args, **kwargs)
        if request:
            bu_service = BusinessUnitsService(user=request.user)
            self.filters['region'].queryset = bu_service.read_regions()
            self.filters['business_unit'].queryset = bu_service.read_units()
            self.filters['route'].queryset = RoutesService(user=request.user).read_routes()
            self.filters['customer'].queryset = Customer.objects.all().order_by('name', 'id')

    def filter_perspective(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        return queryset

    def _is_emitting_mode(self) -> bool:
        if self.data:
            return self.data.get('perspective') == 'emitting_routes'
        return False

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

        if self._is_emitting_mode():
            return queryset.filter(route__business_unit_id__in=all_bu_ids)
        else:
            today = timezone.localdate()
            customer_ids = CustomerAssignment.objects.filter(
                route__business_unit_id__in=all_bu_ids
            ).filter(
                Q(end_date__isnull=True) | Q(end_date__gte=today)
            ).values('customer_id')
            return queryset.filter(customer_id__in=customer_ids)

    def filter_business_unit(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        if not value:
            return queryset

        bu_ids = [bu.pk if hasattr(bu, 'pk') else bu for bu in value]
        if self._is_emitting_mode():
            return queryset.filter(route__business_unit_id__in=bu_ids)
        else:
            today = timezone.localdate()
            customer_ids = CustomerAssignment.objects.filter(
                route__business_unit_id__in=bu_ids
            ).filter(
                Q(end_date__isnull=True) | Q(end_date__gte=today)
            ).values('customer_id')
            return queryset.filter(customer_id__in=customer_ids)

    def filter_route(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        if not value:
            return queryset

        if self._is_emitting_mode():
            return queryset.filter(route__in=value)
        else:
            today = timezone.localdate()
            customer_ids = CustomerAssignment.objects.filter(
                route__in=value
            ).filter(
                Q(end_date__isnull=True) | Q(end_date__gte=today)
            ).values('customer_id')
            return queryset.filter(customer_id__in=customer_ids)

    def filter_aging_status(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        if not value:
            return queryset

        q_filter = Q()
        for choice in value:
            if choice == 'current':
                q_filter |= ~Q(current_balance=0)
            elif choice == 'overdue':
                q_filter |= (
                    ~Q(balance_15=0) |
                    ~Q(balance_30=0) |
                    ~Q(balance_60=0) |
                    ~Q(past_due=0)
                )
            elif choice == '1_15':
                q_filter |= ~Q(balance_15=0)
            elif choice == '16_30':
                q_filter |= ~Q(balance_30=0)
            elif choice == '31_60':
                q_filter |= ~Q(balance_60=0)
            elif choice == 'past_due':
                q_filter |= ~Q(past_due=0)

        return queryset.filter(q_filter).distinct()

    def filter_search(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        if not value:
            return queryset
        return queryset.filter(
            Q(doc_id__icontains=value) |
            Q(description__icontains=value) |
            Q(customer__id__icontains=value) |
            Q(customer__name__icontains=value)
        ).distinct()

    def filter_customer_search(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        if not value:
            return queryset
        return queryset.filter(
            Q(customer__id__icontains=value) |
            Q(customer__name__icontains=value)
        ).distinct()


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
            bu_service = BusinessUnitsService(user=request.user)
            self.filters['region'].queryset = bu_service.read_regions()
            self.filters['business_unit'].queryset = bu_service.read_units()
            self.filters['route'].queryset = RoutesService(user=request.user).read_routes().order_by('id')
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


class YearlySaleBreakdownFilter(django_filters.FilterSet):
    DIMENSION_CHOICES = [
        ('customer_productclass_product', 'Cliente → Clase de producto → Producto'),
        ('productclass_product', 'Clase de producto → Producto'),
        ('productclass_customer_product', 'Clase de producto → Cliente → Producto'),
        ('management_productclass_product', 'Gerencia → Clase de producto → Producto'),
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
            bu_service = BusinessUnitsService(user=request.user)
            self.filters['region'].queryset = bu_service.read_regions()
            self.filters['business_unit'].queryset = bu_service.read_units()
            self.filters['route'].queryset = RoutesService(user=request.user).read_routes().order_by('id')
            self.filters['product_category'].queryset = ProductCategory.objects.all().order_by('name', 'id')
            self.filters['product_class'].queryset = ProductClass.objects.all().order_by('name', 'id')

    def filter_noop(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
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
        return queryset.filter(route__business_unit_id__in=all_bu_ids)

    def filter_business_unit(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        if not value:
            return queryset
        bu_ids = [bu.pk if hasattr(bu, 'pk') else bu for bu in value]
        return queryset.filter(route__business_unit_id__in=bu_ids)

