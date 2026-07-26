import django_filters
from django.db.models import Q
from django import forms
from apps.core.models import User

class UserFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(
        method='filter_search', 
        label='Buscar usuario',
        widget=forms.TextInput(attrs={'placeholder': 'Nombre, apellido o usuario...'})
    )
    
    is_active = django_filters.ChoiceFilter(
        choices=[(True, 'Activo'), (False, 'Inactivo')],
        label='Estado',
        empty_label='Todos'
    )

    last_login__gte = django_filters.DateFilter(
        field_name='last_login', 
        lookup_expr='gte', 
        label='Sesiones desde',
        widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'})
    )

    class Meta:
        model = User
        fields = ['search', 'is_active', 'gender', 'last_login__gte']

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(username__icontains=value) |
            Q(first_name__icontains=value) |
            Q(last_name__icontains=value) |
            Q(second_last_name__icontains=value)
        )
