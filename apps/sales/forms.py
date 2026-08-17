from django import forms
from django.forms import inlineformset_factory

from apps.sales.models import (
    Warehouse,
    RouteType,
    SaleChannel,
    Route,
    RouteAssignment,
    UserRouteAccess,
    SaleTarget,
)


class WarehouseForm(forms.ModelForm):
    class Meta:
        model = Warehouse
        fields = ['id', 'name', 'warehouse_type']


class RouteForm(forms.ModelForm):
    class Meta:
        model = Route
        fields = [
            'id',
            'name',
            'business_unit',
            'route_type',
            'sale_channel',
            'is_active',
            'notes',
        ]
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def clean_id(self):
        route_id = self.cleaned_data.get('id')
        if route_id:
            return route_id.strip().upper()
        return route_id


RouteAssignmentFormSet = inlineformset_factory(
    Route,
    RouteAssignment,
    fields=['employee', 'date_start', 'date_end', 'notes'],
    widgets={
        'date_start': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
        'date_end': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
        'notes': forms.Textarea(attrs={'rows': 1}),
    },
    extra=1,
    can_delete=True,
)


UserRouteAccessFormSet = inlineformset_factory(
    Route,
    UserRouteAccess,
    fields=['user', 'can_view', 'can_edit', 'notes'],
    widgets={
        'notes': forms.Textarea(attrs={'rows': 1}),
    },
    extra=1,
    can_delete=True,
)


class SaleTargetForm(forms.ModelForm):
    period = forms.DateField(
        widget=forms.DateInput(format='%Y-%m', attrs={'type': 'month'}),
        input_formats=['%Y-%m', '%Y-%m-%d'],
        label='Periodo (Mes)',
    )

    class Meta:
        model = SaleTarget
        fields = [
            'period',
            'route',
            'business_unit',
            'product_class',
            'target_amount',
            'is_valid_for_comission',
        ]
        widgets = {
            'target_amount': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.period:
            self.initial['period'] = self.instance.period.strftime('%Y-%m')

    def clean_period(self):
        period = self.cleaned_data.get('period')
        if period:
            return period.replace(day=1)
        return period
