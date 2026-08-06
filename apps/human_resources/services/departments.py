from dataclasses import dataclass
from typing import ClassVar
from apps.human_resources.models import Department
from apps.core.services.users import UsersService
from django.db.models import QuerySet, Count

from apps.human_resources.services.employees import EmployeesService

class ServiceError(Exception):
    pass

class DepartmentNotFound(ServiceError):
    pass

class PermissionsError(ServiceError):
    pass

@dataclass
class DepartmentsService(UsersService):
    department_model: type = Department
    ACCESS_CONTEXTS: ClassVar[tuple[str, ...]] = (
        'acceso_total_usuarios',
        'acceso_total_departamentos',
        'recursos_humanos',
    )

    def read_departments(self) -> QuerySet:
        if self._is_full_access:
            return self.department_model.objects.all()

        employees_service = EmployeesService(user=self.user)
        accessible_employees = employees_service.read_employees()

        return self.department_model.objects.filter(
            positions__employees__in=accessible_employees
        ).distinct()

    def read_department(self, *, pk: str) -> Department:
        department = self.read_departments().filter(pk=pk).first()
        if department:
            return department

        if self.department_model.objects.filter(pk=pk).exists():
            raise PermissionsError(f'No tienes permiso para acceder al departamento con ID "{pk}".')

        raise DepartmentNotFound(f'No se encontró ningún departamento con el ID "{pk}".')


@dataclass
class DepartmentsStats:
    departments_service: DepartmentsService

    @property
    def _base_qs(self) -> QuerySet:
        return self.departments_service.read_departments()

    def stats(self, qs: QuerySet) -> dict:
        base_qs = qs if qs is not None else self._base_qs
        return base_qs.aggregate(
            departments_count=Count('pk'),
        )