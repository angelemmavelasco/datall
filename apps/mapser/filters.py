from typing import Any
import django_filters
from django import forms
from django.db.models import Q, QuerySet
from django.utils import timezone

from apps.customers.models import Customer, CustomerType
from apps.human_resources.models import BusinessUnit
from apps.human_resources.services.business_units import BusinessUnitsService
from apps.mapser.models import DenueInegi
from apps.sales.models import Route
from apps.sales.services.routes import RoutesService


MEXICO_STATES = [
    ('01', 'Aguascalientes'),
    ('02', 'Baja California'),
    ('03', 'Baja California Sur'),
    ('04', 'Campeche'),
    ('05', 'Coahuila de Zaragoza'),
    ('06', 'Colima'),
    ('07', 'Chiapas'),
    ('08', 'Chihuahua'),
    ('09', 'Ciudad de México'),
    ('10', 'Durango'),
    ('11', 'Guanajuato'),
    ('12', 'Guerrero'),
    ('13', 'Hidalgo'),
    ('14', 'Jalisco'),
    ('15', 'México'),
    ('16', 'Michoacán de Ocampo'),
    ('17', 'Morelos'),
    ('18', 'Nayarit'),
    ('19', 'Nuevo León'),
    ('20', 'Oaxaca'),
    ('21', 'Puebla'),
    ('22', 'Querétaro'),
    ('23', 'Quintana Roo'),
    ('24', 'San Luis Potosí'),
    ('25', 'Sinaloa'),
    ('26', 'Sonora'),
    ('27', 'Tabasco'),
    ('28', 'Tamaulipas'),
    ('29', 'Tlaxcala'),
    ('30', 'Veracruz de Ignacio de la Llave'),
    ('31', 'Yucatán'),
    ('32', 'Zacatecas'),
]


class BusinessUnitMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj: BusinessUnit) -> str:
        return obj.name.title()


class BusinessUnitMultipleChoiceFilter(django_filters.ModelMultipleChoiceFilter):
    field_class = BusinessUnitMultipleChoiceField


class MapserFilter(django_filters.FilterSet):
    '''
    filterset for mapser customer geographic exploration
    '''
    customer = django_filters.ModelMultipleChoiceFilter(
        field_name='id',
        to_field_name='id',
        queryset=Customer.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label='Cliente'
    )
    customer_type = django_filters.ModelMultipleChoiceFilter(
        field_name='customer_type',
        queryset=CustomerType.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label='Tipo de cliente'
    )
    registration_date_start = django_filters.DateFilter(
        field_name='registration_date',
        lookup_expr='gte',
        label='Fecha de alta (Desde)',
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    registration_date_end = django_filters.DateFilter(
        field_name='registration_date',
        lookup_expr='lte',
        label='Fecha de alta (Hasta)',
        widget=forms.DateInput(attrs={'type': 'date'})
    )
    state = django_filters.MultipleChoiceFilter(
        method='filter_state',
        choices=MEXICO_STATES,
        widget=forms.CheckboxSelectMultiple,
        label='Entidad federativa'
    )
    route = django_filters.ModelMultipleChoiceFilter(
        method='filter_route',
        queryset=Route.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        label='Ruta'
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
            self.filters['customer'].queryset = Customer.objects.all().order_by('name', 'id')

        db_states = list(
            DenueInegi.objects
            .exclude(state_code='')
            .values_list('state_code', 'state_name')
            .distinct()
            .order_by('state_code')
        )
        if db_states:
            known_dict = dict(MEXICO_STATES)
            merged_choices = []
            seen = set()
            for code, name in db_states:
                code_str = str(code).zfill(2)
                display_name = known_dict.get(code_str) or name.title() or f'Entidad {code_str}'
                if code_str not in seen:
                    seen.add(code_str)
                    merged_choices.append((code_str, display_name))
            for code_str, display_name in MEXICO_STATES:
                if code_str not in seen:
                    seen.add(code_str)
                    merged_choices.append((code_str, display_name))
            self.filters['state'].extra['choices'] = merged_choices

    def filter_state(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        if not value:
            return queryset
        state_codes = [str(v).zfill(2) for v in value]
        state_names = [dict(MEXICO_STATES).get(c) for c in state_codes if dict(MEXICO_STATES).get(c)]

        q_filter = Q(geo_profile__matched_denue__state_code__in=state_codes)
        for s_name in state_names:
            if s_name:
                q_filter |= Q(geo_profile__state__icontains=s_name)
        return queryset.filter(q_filter).distinct()

    def filter_route(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        if not value:
            return queryset
        today = timezone.localdate()
        return queryset.filter(
            Q(assignments__route__in=value) &
            (Q(assignments__end_date__isnull=True) | Q(assignments__end_date__gte=today))
        ).distinct()

    def filter_business_unit(self, queryset: QuerySet, name: str, value: Any) -> QuerySet:
        if not value:
            return queryset
        today = timezone.localdate()
        bu_ids = [bu.pk if hasattr(bu, 'pk') else bu for bu in value]
        return queryset.filter(
            Q(assignments__route__business_unit_id__in=bu_ids) &
            (Q(assignments__end_date__isnull=True) | Q(assignments__end_date__gte=today))
        ).distinct()

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

        today = timezone.localdate()
        return queryset.filter(
            Q(assignments__route__business_unit_id__in=all_bu_ids) &
            (Q(assignments__end_date__isnull=True) | Q(assignments__end_date__gte=today))
        ).distinct()
