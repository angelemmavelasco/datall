from typing import TYPE_CHECKING, Optional
from django.db import models, transaction
from django.db.models import QuerySet
from apps.human_resources.models import Employee
from django.utils import timezone
from dataclasses import dataclass, field

class ServiceError(Exception):
    pass

class PositionNotFoundError(ServiceError):
    pass

class PositionPermissionError(ServiceError):
    pass

class PositionAuthenticationError(ServiceError):
    pass

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser as UserModel
else:
    UserModel = object

@dataclass
class EmployeesService:
    user: 'UserModel'
    EmployeeModel: type[Employee] = Employee
    _is_full_access: bool = field(init=False)

    def __post_init__(self) -> None:
        self._validate_access()
        self._is_full_access = self._checkout_full_access

    def _validate_access(self) -> None:
        '''
        validates if the user was provided, exists and is authenticated.
        '''
        if not self.user:
            raise PositionNotFoundError('No se ha proporcionado un usuario válido.')
        if not self.user.is_authenticated:
            raise PositionAuthenticationError('El usuario proporcionado no está autenticado.')
        if not getattr(self.user, 'is_active', True):
            raise PositionPermissionError('El usuario se encuentra inactivo.')

    @property
    def _checkout_full_access(self) -> bool:
        '''
        validates if user has total access (or is superuser) or limited access.
        '''
        if getattr(self.user, 'is_superuser', False):
            return True
        return self.user.groups.filter(name__in=[
            'total', 'acceso total', 'admin', 'global', 
            'acceso global', 'rh', 'hr', 'recursos humanos', 'rh admin', 'human resources'
        ]).exists()

    def read_employees(self) -> QuerySet:
        '''
        returns a qs which the main user has access to.
        regular users can view only employees which they are associated to, while full access users can view all.
        '''
        today = timezone.now().date()
        base_qs = self.EmployeeModel.objects.select_related(
            'user', 
            'position', 
            'position__department'
        ).prefetch_related(
            'position__position_skills__skill',
            'human_resources_direct_reports',
            'human_resources_direct_reports__user',
            'human_resources_direct_reports__position'
        ).annotate(
            is_active=models.Case(
                models.When(models.Q(termination_date__isnull=True) | models.Q(termination_date__gt=today), then=models.Value(True)),
                default=models.Value(False),
                output_field=models.BooleanField()
            )
        ).order_by('position__department__name', 'position__name', 'user__first_name')
        if self._is_full_access:
            return base_qs.all()
        user_employees = self.EmployeeModel.objects.filter(user=self.user)
        tree_ids = []
        for emp in user_employees:
            tree_ids.extend(emp.get_reporting_tree_ids())
        return base_qs.filter(id__in=set(tree_ids))

    def read_employee(self, *, pk: str):
        '''
        Returns a single Employee object if the user has access.
        '''
        return self.read_employees().filter(pk=pk).first()
        
    def read_employees_by_user(self, *, user_id: int) -> QuerySet:
        '''
        Returns all Employee records (positions) assigned to a specific user.
        Useful for the user profile view to list their positions.
        '''
        return self.read_employees().filter(user__id=user_id).order_by('-is_active', '-hire_date')