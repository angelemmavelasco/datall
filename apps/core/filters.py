from datetime import datetime, time
import django_filters
from django.conf import settings
from django.db.models import Q
from django import forms
from django.contrib.auth.models import Group
from django.utils import timezone
from apps.core.models import User, ActivityLog


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

    groups = django_filters.ModelMultipleChoiceFilter(
        queryset=Group.objects.all().order_by('name'),
        field_name='groups',
        label='Grupo / Rol',
        widget=forms.CheckboxSelectMultiple
    )

    last_login__gte = django_filters.DateFilter(
        field_name='last_login',
        lookup_expr='gte',
        label='Sesiones desde',
        widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'})
    )

    class Meta:
        model = User
        fields = ['search', 'is_active', 'gender', 'groups', 'last_login__gte']

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(username__icontains=value) |
            Q(first_name__icontains=value) |
            Q(last_name__icontains=value) |
            Q(second_last_name__icontains=value)
        ).distinct()


class UserMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj: User) -> str:
        full_name = f"{obj.first_name} {obj.last_name}".strip()
        if full_name:
            return f"{full_name} (@{obj.username})"
        return f"@{obj.username}"


class UserMultipleChoiceFilter(django_filters.ModelMultipleChoiceFilter):
    field_class = UserMultipleChoiceField


class ActivityLogFilter(django_filters.FilterSet):
    date_start = django_filters.DateFilter(
        method='filter_date_start',
        label='Desde',
        widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'})
    )
    date_end = django_filters.DateFilter(
        method='filter_date_end',
        label='Hasta',
        widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'})
    )
    user = UserMultipleChoiceFilter(
        field_name='user',
        queryset=User.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        label='Usuario'
    )

    class Meta:
        model = ActivityLog
        fields = []

    def __init__(self, *args, **kwargs):
        request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        if request and getattr(request, 'user', None):
            from apps.core.services.activity_logs import ActivityLogsService
            service = ActivityLogsService(user=request.user)
            self.filters['user'].queryset = service.read_users().order_by('first_name', 'last_name', 'username')
        else:
            self.filters['user'].queryset = User.objects.all().order_by('first_name', 'last_name', 'username')

    def filter_date_start(self, queryset, name, value):
        if not value:
            return queryset
        start_dt = datetime.combine(value, time.min)
        if settings.USE_TZ and timezone.is_naive(start_dt):
            start_dt = timezone.make_aware(start_dt, timezone.get_current_timezone())
        return queryset.filter(created_at__gte=start_dt)

    def filter_date_end(self, queryset, name, value):
        if not value:
            return queryset
        end_dt = datetime.combine(value, time.max)
        if settings.USE_TZ and timezone.is_naive(end_dt):
            end_dt = timezone.make_aware(end_dt, timezone.get_current_timezone())
        return queryset.filter(created_at__lte=end_dt)