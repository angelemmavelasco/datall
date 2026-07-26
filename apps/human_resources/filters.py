import django_filters
from django.db.models import Q
from django import forms
from apps.human_resources.models import Department

class DepartmentFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(
        method='filter_search', 
        label='Buscar departamento',
        widget=forms.TextInput(attrs={'placeholder': 'ID, nombre o descripción...'})
    )

    class Meta:
        model = Department
        fields = ['search']

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(id__icontains=value) |
            Q(name__icontains=value) |
            Q(description__icontains=value)
        )
