from dataclasses import dataclass
from typing import ClassVar, Optional
from apps.human_resources.models import Employee
from apps.core.services.users import UsersService
from django.db.models import QuerySet, When, Case, Value, BooleanField, Q
from django.utils import timezone


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
            'user', 'position', 'manager', 'business_unit'
        ).annotate(
            employee_status=Case(
                When(
                    Q(hire_date__lte=today) & (Q(termination_date__isnull=True) | Q(termination_date__gte=today)),
                    then=Value(True)
                ),
                default=Value(False),
                output_field=BooleanField()
            )
        )
        if self._is_full_access:
            return base_qs

        return self._filter_by_hierarchy(base_qs)

    def _filter_by_hierarchy(self, queryset: QuerySet) -> QuerySet:
        '''
        returns a qs with the employees managed by the user
        '''
        user_employees = self.employee_model.objects.filter(user = self.user)

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
