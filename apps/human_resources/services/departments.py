from django.contrib.auth import get_user_model
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional
from django.db.models import QuerySet, Count, Q, Value, When, Case
from django.db import transaction
from django.utils import timezone

from apps.human_resources.models import Department

# exceptions
class ServiceError(Exception):
    pass

class DepartmentNotFoundError(ServiceError):
    pass

class DepartmentPermissionError(ServiceError):
    pass

class DepartmentAuthenticationError(ServiceError):
    pass

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser as UserModel
else:
    UserModel = object

@dataclass
class DepartmentsService:
    '''
    The main service used to read, create, update and delete departments.
    This service handles the business logic of the departments module.
    '''
    user: 'UserModel'
    DepartmentModel: type[Department] = Department
    _is_full_access: bool = field(init=False)

    def __post_init__(self) -> bool:
        self._validate_access()
        self._is_full_access = self._checkout_full_access

    def _validate_access(self) -> None:
        '''
        validates if the user was provided, exists and is authenticated.
        '''
        if not self.user:
            raise DepartmentNotFoundError('No se ha proporcionado un usuario válido.')
        if not self.user.is_authenticated:
            raise DepartmentAuthenticationError('El usuario proporcionado no está autenticado.')
        if not getattr(self.user, 'is_active', True):
            raise DepartmentPermissionError('El usuario se encuentra inactivo.')

    @property
    def _checkout_full_access(self) -> bool:
        '''
        validates if user has total access (or is superuser) or limited access.
        '''
        if getattr(self.user, 'is_superuser', False):
            return True
        return self.user.groups.filter(name__in=['total', 'acceso total', 'admin', 'global', 'acceso global', 'rh', 'hr', 'recursos humanos']).exists()

    def read_departments(self) -> QuerySet:
        '''
        returns a qs which the main user has access to.
        regular users can view only departments which they are associated to, while full access users can view all.
        '''
        today = timezone.now().date()
        base_qs = self.DepartmentModel.objects.annotate(
            positions_count=Count('human_resources_positions', distinct=True),
            active_employees_count=Count(
                'human_resources_positions__human_resources_employees',
                distinct=True,
                filter=(
                    Q(human_resources_positions__human_resources_employees__termination_date__isnull=True) |
                    Q(human_resources_positions__human_resources_employees__termination_date__gt=today)
                )
            ),
            inactive_employees_count=Count(
                'human_resources_positions__human_resources_employees',
                distinct=True,
                filter=(
                    Q(human_resources_positions__human_resources_employees__termination_date__isnull=False) &
                    Q(human_resources_positions__human_resources_employees__termination_date__lte=today)
                )
            ),
        )
        
        if self._is_full_access:
            return base_qs.all()
        return base_qs.filter(human_resources_positions__human_resources_employees__user=self.user).distinct()

    
    def read_department(self, *, pk: str) -> Optional[Department]:
        '''
        return a single object.
        '''
        return self.read_departments().filter(pk=pk).first()
    
    def create_department(self, **data) -> Department:
        '''
        create a new department based on provided data.
        '''
        if not self._is_full_access:
            raise DepartmentPermissionError('El usuario no tiene permisos para crear departamentos.')
        
        with transaction.atomic():
            new_department = self.DepartmentModel(**data)
            new_department.save()
            
        return new_department
    
    def update_department(self, *, pk: str, **new_data) -> Department:
        '''
        update a department based on the provided data.
        '''
        department_to_update = self.read_department(pk=pk)
        if department_to_update is None:
            raise DepartmentNotFoundError(f'No se encontró el departamento con id {pk}.')

        if not self._is_full_access:
            raise DepartmentPermissionError('El usuario no tiene permisos para actualizar departamentos.')

        #since the pk is registered manually, avoid changing is necesary
        disallowed = ['pk']
        for key in disallowed:
            new_data.pop(key, None)

        with transaction.atomic():
            for attr, value in new_data.items():
                setattr(department_to_update, attr, value)
            department_to_update.save()
            
        return department_to_update

@dataclass
class DepartmentsKPIsService:
    '''
    dedicated to read generals stats and information about departments.
    '''
    departments_service: DepartmentsService

    @property
    def _base_qs(self) -> QuerySet:
        '''
        reuse class service base logic to bring allowed departments and calculate over them
        '''
        return self.departments_service.read_departments()

    def stats(self, qs=None) -> dict:
        '''
        returns dictionary with general departments stats, including: registered departments, associated positions, and active employees.
        '''
        today = timezone.now().date()
        base_qs = qs if qs is not None else self._base_qs
        return base_qs.aggregate(
            registered_departments=Count('pk', distinct=True),
            associated_positions=Count('human_resources_positions', distinct=True),
            active_employees=Count(
                'human_resources_positions__human_resources_employees',
                distinct=True,
                filter=(
                    Q(human_resources_positions__human_resources_employees__termination_date__isnull=True)|
                    Q(human_resources_positions__human_resources_employees__termination_date__gt=today)
                )
            ),
            inactive_employees=Count(
                'human_resources_positions__human_resources_employees',
                distinct=True,
                filter=(
                    Q(
                        human_resources_positions__human_resources_employees__termination_date__isnull=False
                    )&
                    Q(
                        human_resources_positions__human_resources_employees__termination_date__lte=today
                    )
                ),
            )
        )
