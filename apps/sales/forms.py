from django import forms
from apps.sales.models import (
    Warehouse,
    RouteType,
    SaleChannel,
    Route,
    RouteAssignment,
    UserRouteAccess,
)


class WarehouseForm(forms.ModelForm):
    class Meta:
        model = Warehouse
        fields = ['id', 'name', 'warehouse_type']
