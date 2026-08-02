from django import forms
from django.forms import inlineformset_factory

from apps.sales.models import Route, UserRouteAccess


class RouteForm(forms.ModelForm):
    class Meta:
        model = Route
        fields = '__all__'
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, requesting_user=None, is_full_access=False, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk:
            # PK manual: no se permite cambiar el id en update
            self.fields['id'].disabled = True

        if not requesting_user:
            return

        is_superuser = getattr(requesting_user, 'is_superuser', False)
        if not is_full_access and not is_superuser:
            # No hay restricción adicional por ahora para usuarios no-full
            pass


class UserRouteAccessForm(forms.ModelForm):
    '''
    Inline form for assigning a user explicit view access to a route.
    can_sell is intentionally NOT exposed yet (Datall is ETL/BI, not ERP).
    '''
    class Meta:
        model = UserRouteAccess
        fields = ['user', 'can_view']


UserRouteAccessFormSet = inlineformset_factory(
    Route,
    UserRouteAccess,
    form=UserRouteAccessForm,
    fields=['user', 'can_view'],
    extra=1,
    can_delete=True
)
