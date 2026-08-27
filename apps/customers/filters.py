import django_filters
from django import forms
from django.db.models import Q
from django.utils import timezone

from apps.human_resources.models import BusinessUnit
from apps.human_resources.services.business_units import BusinessUnitsService
from apps.sales.models import Route
from apps.sales.services.routes import RoutesService
from .models import Customer, CustomerType, CustomerAssignment


class BusinessUnitMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj: BusinessUnit) -> str:
        return obj.name.title()


class BusinessUnitMultipleChoiceFilter(django_filters.ModelMultipleChoiceFilter):
    field_class = BusinessUnitMultipleChoiceField


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
    business_unit = BusinessUnitMultipleChoiceFilter(
        method='filter_business_unit',
        queryset=BusinessUnit.objects.filter(business_unit_type=BusinessUnit.BusinessUnitTypeChoices.UNIT),
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
            self.filters['business_unit'].queryset = BusinessUnitsService(user=request.user).read_units()

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
    perspective = django_filters.ChoiceFilter(
        choices=PERSPECTIVE_CHOICES,
        label='Forma de visualización',
        method='filter_perspective',
        empty_label=None
    )
    aging_status = django_filters.MultipleChoiceFilter(
        choices=AGING_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        label='Estatus de saldo',
        method='filter_aging_status'
    )
    issue_date_from = django_filters.DateFilter(
        method='filter_issue_date_from',
        label='Fecha de emisión (Desde)',
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    issue_date_to = django_filters.DateFilter(
        method='filter_issue_date_to',
        label='Fecha de emisión (Hasta)',
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    due_date_from = django_filters.DateFilter(
        method='filter_due_date_from',
        label='Fecha de pago (Desde)',
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    due_date_to = django_filters.DateFilter(
        method='filter_due_date_to',
        label='Fecha de pago (Hasta)',
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
        from .models import AccountsReceivable
        model = AccountsReceivable
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

    def _is_emitting_mode(self) -> bool:
        if self.data:
            return self.data.get('perspective') == 'emitting_routes'
        return False

    def filter_perspective(self, queryset, name, value):
        return queryset

    def filter_region(self, queryset, name, value):
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

    def filter_business_unit(self, queryset, name, value):
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

    def filter_route(self, queryset, name, value):
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

    def filter_aging_status(self, queryset, name, value):
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

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(doc_id__icontains=value) |
            Q(description__icontains=value) |
            Q(customer__id__icontains=value) |
            Q(customer__name__icontains=value)
        ).distinct()

    def filter_issue_date_from(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(Q(issue_date__gte=value) | Q(issue_date__isnull=True))

    def filter_issue_date_to(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(Q(issue_date__lte=value) | Q(issue_date__isnull=True))

    def filter_due_date_from(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(Q(due_date__gte=value) | Q(due_date__isnull=True))

    def filter_due_date_to(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(Q(due_date__lte=value) | Q(due_date__isnull=True))
