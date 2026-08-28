from dataclasses import dataclass
from typing import ClassVar

from django.db.models.aggregates import Sum

from apps.human_resources.models import Department
from apps.core.services.users import UsersService
from django.db.models import QuerySet, Count, Q
from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from apps.human_resources.services.employees import EmployeesService
from apps.human_resources.services.positions import PositionsService
from django.utils import timezone

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
        'acceso_total',
    )

    def read_departments(self) -> QuerySet:
        today = timezone.now().date()

        is_active_emp = Q(
            positions__employees__hire_date__lte=today,
        ) & (
            Q(positions__employees__termination_date__isnull=True) |
            Q(positions__employees__termination_date__gte=today)
        )

        is_inactive_emp = Q(
            positions__employees__termination_date__lt=today
        ) | Q(
            positions__employees__hire_date__gt=today
        )

        if self._is_full_access:
            base_qs = self.department_model.objects.all()
            active_employees_filter = is_active_emp
            inactive_employees_filter = is_inactive_emp
        else:
            employees_service = EmployeesService(user=self.user)
            accessible_employees = employees_service.read_employees()

            base_qs = self.department_model.objects.filter(
                positions__employees__in=accessible_employees
            ).distinct()

            active_employees_filter = is_active_emp & Q(positions__employees__in=accessible_employees)
            inactive_employees_filter = is_inactive_emp & Q(positions__employees__in=accessible_employees)

        return base_qs.annotate(
            associated_positions_count=Count('positions__pk', distinct=True),
            associated_active_employees_count=Count(
                'positions__employees__pk',
                filter=active_employees_filter,
                distinct=True
            ),
            associated_inactive_employees_count=Count(
                'positions__employees__pk',
                filter=inactive_employees_filter,
                distinct=True
            ),
        )


    def read_department(self, *, pk: str) -> Department:
        department = self.read_departments().filter(pk=pk).first()
        if department:
            return department

        if self.department_model.objects.filter(pk=pk).exists():
            raise PermissionsError(f'No tienes permiso para acceder al departamento con ID "{pk}".')

        raise DepartmentNotFound(f'No se encontró ningún departamento con el ID "{pk}".')

    def read_department_positions(self, department: Department) -> QuerySet:
        '''returns a list of the associated positions (objects ) to a given department'''
        positions_service = PositionsService(user=self.user)
        return positions_service.read_positions().filter(department=department).order_by('hierarchy_level','name')
        
    def read_department_employees(self, department: Department, active: bool | None = True) -> QuerySet:
        '''returns a list of the associated employees (objects) to a given department (filtered by active/inactive)'''
        today = timezone.now().date()
        employees_service = EmployeesService(user=self.user)
        base_qs = employees_service.read_employees().filter(position__department=department)
        is_active_filter = Q(hire_date__lte=today) & (
            Q(termination_date__isnull=True) | Q(termination_date__gte=today)
        )
        if active is True:
            return base_qs.filter(is_active_filter)
        elif active is False:
            return base_qs.exclude(is_active_filter)
        return base_qs

    def create_department(self, **data) -> Department:
        '''
        Create a new department based on provided data.
        Only allowed users (full access) can do it.
        '''
        if not self._is_full_access:
            raise PermissionsError('No tienes permisos suficientes para crear departamentos.')

        try:
            with transaction.atomic():
                new_department = self.department_model(**data)
                new_department.full_clean()
                new_department.save()

            return new_department

        except ValidationError as e:
            raise ServiceError(f"Datos inválidos: {', '.join(e.messages)}")
        except IntegrityError:
            raise ServiceError("Ya existe un departamento con esos datos únicos (ej. ID o Nombre).")
        except Exception as e:
            raise ServiceError(f"Error al crear el departamento: {str(e)}")

    def update_department(self, *, pk: str, **data) -> Department:
        department_to_update = self.read_department(pk=pk)

        if not self._is_full_access:
            raise PermissionsError('No tienes permisos suficientes para actualizar departamentos.')

        disallowed = {'id', 'pk'}
        for key in disallowed:
            data.pop(key, None)

        try:
            with transaction.atomic():
                for attr, value in data.items():
                    setattr(department_to_update, attr, value)

                department_to_update.full_clean()
                department_to_update.save()

            return department_to_update

        except ValidationError as e:
            raise ServiceError(f"Datos inválidos: {', '.join(e.messages)}")
        except IntegrityError:
            raise ServiceError("Ya existe un departamento con esos datos únicos.")
        except Exception as e:
            raise ServiceError(f"Error al actualizar el departamento: {str(e)}")

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
            positions_count=Count('positions__pk', distinct=True),
            active_employees_count=Sum('associated_active_employees_count'),
            inactive_employees_count=Sum('associated_inactive_employees_count'),
        )