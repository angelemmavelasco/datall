from typing import TYPE_CHECKING, Optional
from django.db import models, transaction, connection
from django.db.models import QuerySet
from apps.human_resources.models import Employee
from django.utils import timezone
from dataclasses import dataclass, field
from django.db.models.functions import Lower, ExtractYear

class ServiceError(Exception):
    pass

class EmployeeNotFoundError(ServiceError):
    pass

class EmployeePermissionError(ServiceError):
    pass

class EmployeeAuthenticationError(ServiceError):
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
            raise EmployeeNotFoundError('No se ha proporcionado un usuario válido.')
        if not self.user.is_authenticated:
            raise EmployeeAuthenticationError('El usuario proporcionado no está autenticado.')
        if not getattr(self.user, 'is_active', True):
            raise EmployeePermissionError('El usuario se encuentra inactivo.')

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
            'position__department',
            'manager__user'
        ).prefetch_related(
            'position__human_resources_position_skills__skill',
            'human_resources_direct_reports',
            'human_resources_direct_reports__user',
            'human_resources_direct_reports__position'
        ).annotate(
            is_active=models.Case(
                models.When(models.Q(termination_date__isnull=True) | models.Q(termination_date__gt=today), then=models.Value(True)),
                default=models.Value(False),
                output_field=models.BooleanField()
            )
        ).order_by('position__hierarchy_level', Lower('position__department__name'), Lower('position__name'), Lower('user__first_name'), Lower('user__last_name'))
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

    def create_user(self, **data) -> Employee:
        '''
        creates a new employee (position assignment) from provided data
        '''
        if not self._is_full_access:
            raise EmployeePermissionError("No se tienen permisos para crear colaboradores")
        with transaction.atomic():
            new_employee = self.EmployeeModel.objects.create(**data)
            new_employee.save()
        return new_employee

    def update_employee(self, *, pk: str, **data) -> Employee:
        '''
        update an employee based on provided data
        '''
        employee = self.read_employee(pk=pk)
        if not employee:
            raise EmployeeNotFoundError('El colaborador no existe o no se tiene permisos para verlo.')
        if not self._is_full_access:
            raise EmployeePermissionError("No se tienen permisos para actualizar colaboradores")
        disallowed = ['pk']
        for key in disallowed:
            data.pop(key, None)
        with transaction.atomic():
            for key, value in data.items():
                if value is False:
                    value = None
                setattr(employee, key, value)
            employee.save()
        return employee


@dataclass
class EmployeesKpisService:
    '''
    dedicated top read and get general kpis and stats over employees
    '''
    employees_service: EmployeesService

    class Median(models.Aggregate):
        function = 'PERCENTILE_CONT'
        template = '%(function)s(0.5) WITHIN GROUP (ORDER BY %(expressions)s)'
        output_field = models.FloatField()

    @property
    def _base_qs(self) -> QuerySet:
        '''
        reuse class service base logic to bring allowed employees and calculate over them
        '''
        return self.employees_service.read_employees()

    def stats(self, qs:QuerySet=None) -> dict:
        '''
        Returns a dictionary with general statistics about the employees.
        '''
        today = timezone.now().date()
        target_qs = qs if qs is not None else self._base_qs
        base_qs = target_qs.annotate(
            age=models.Value(today.year) - ExtractYear('user__birth_date')
        )

        aggregate_kwargs = {
            #personal
            'assigned_positions': models.Count('position__pk', distinct=True, filter=(models.Q(is_active=True))),
            'total_personal': models.Count('user__pk', distinct=True, filter=(models.Q(is_active=True))),
            'active_employees': models.Count('pk', distinct=True, filter=(models.Q(is_active=True))),
            'inactive_employees': models.Count('pk', distinct=True, filter=(models.Q(is_active=False))),
            'total_employees': models.Count('pk', distinct=True),
            'men_count': models.Count('user__pk', distinct=True, filter=(models.Q(is_active=True, user__gender='m'))),
            'women_count': models.Count('user__pk', distinct=True, filter=(models.Q(is_active=True, user__gender='f'))),
            #payroll
            'payroll_mean': models.Avg('payroll_payment_amount', filter=(models.Q(is_active=True))),
            'payroll_max': models.Max('payroll_payment_amount', filter=(models.Q(is_active=True))),
            'payroll_min': models.Min('payroll_payment_amount', filter=(models.Q(is_active=True))),
            'total_payroll': models.Sum('payroll_payment_amount', filter=(models.Q(is_active=True))),
            #age
            'age_mean': models.Avg('age', filter=(models.Q(is_active=True, user__birth_date__isnull=False))),
            'age_max': models.Max('age', filter=(models.Q(is_active=True, user__birth_date__isnull=False))),
            'age_min': models.Min('age', filter=(models.Q(is_active=True, user__birth_date__isnull=False))),
        }
        if connection.vendor == 'postgresql':
            aggregate_kwargs['payroll_median'] = self.Median('payroll_payment_amount')
        else:
            aggregate_kwargs['payroll_median'] = models.Avg('payroll_payment_amount', filter=(models.Q(is_active=True)))

        kpis = base_qs.aggregate(**aggregate_kwargs)
        return kpis
    
