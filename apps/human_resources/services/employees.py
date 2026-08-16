from dataclasses import dataclass
from typing import ClassVar, Optional
import statistics
from decimal import Decimal

from django.db.models import QuerySet, When, Case, Value, BooleanField, Q, Count
from django.utils import timezone

from apps.human_resources.models import Employee
from apps.core.models import GenderChoices
from apps.core.services.users import UsersService


class ServiceError(Exception):
    pass


class EmployeeNotFound(ServiceError):
    pass


class PermissionsError(ServiceError):
    pass


@dataclass
class EmployeesService(UsersService):
    employee_model: type = Employee
    ACCESS_CONTEXTS: ClassVar[tuple[str, ...]] = (
        'acceso_total_usuarios',
        'acceso_total_colaboradores',
        'recursos_humanos',
    )

    def read_employees(self) -> QuerySet:
        today = timezone.now().date()
        base_qs = self.employee_model.objects.select_related(
            'user', 'position', 'position__department', 'manager', 'business_unit'
        ).annotate(
            employee_status=Case(
                When(
                    Q(hire_date__lte=today) & (Q(termination_date__isnull=True) | Q(termination_date__gte=today)),
                    then=Value(True)
                ),
                default=Value(False),
                output_field=BooleanField()
            )
        ).order_by(
            'position__department__name',
            'position__hierarchy_level',
            'position__name',
            'user__first_name',
            'user__last_name'
        )

        if self._is_full_access:
            return base_qs

        return self._filter_by_hierarchy(base_qs)

    def _filter_by_hierarchy(self, queryset: QuerySet) -> QuerySet:
        '''
        returns a qs with the employees managed by the user
        '''
        user_employees = self.employee_model.objects.filter(user=self.user)

        if not user_employees.exists():
            return queryset.none()

        allowed_ids = set()
        for emp in user_employees:
            allowed_ids.update(emp.get_reporting_tree_ids())

        return queryset.filter(id__in=allowed_ids)

    def read_employee(self, *, pk: str) -> Optional[Employee]:
        '''Returns a single employee object or None if not found or unauthorized.'''
        employee = self.read_employees().filter(pk=pk).first()
        if employee:
            return employee

        if self.employee_model.objects.filter(pk=pk).exists():
            raise PermissionsError(f'No tienes permiso para acceder al colaborador con ID "{pk}".')

        raise EmployeeNotFound(f'No se encontró ningún colaborador con el ID "{pk}".')


@dataclass
class EmployeesStats:
    '''dedicated only to give general stats about employees'''
    employee_service: EmployeesService

    @property
    def _base_qs(self) -> QuerySet:
        return self.employee_service.read_employees()

    def stats(self, *, qs: QuerySet = None) -> dict:
        base_qs = qs if qs is not None else self._base_qs

        agg = base_qs.aggregate(
            employees_count=Count('pk', distinct=True),
            active_employees_count=Count('pk', filter=Q(employee_status=True), distinct=True),
            inactive_employees_count=Count('pk', filter=Q(employee_status=False), distinct=True),
            female_employees_count=Count('pk', filter=Q(user__gender=GenderChoices.FEMALE), distinct=True),
            male_employees_count=Count('pk', filter=Q(user__gender=GenderChoices.MALE), distinct=True),
            occupied_positions_count=Count('position', filter=Q(employee_status=True), distinct=True),
        )

        salaries = [float(s) for s in base_qs.values_list('payroll_payment_amount', flat=True) if s is not None]
        agg['salary_median'] = statistics.median(salaries) if salaries else Decimal('0.00')

        return agg
