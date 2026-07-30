from ..models import (
    MonitoringForm,
    MonitoringFormField,
    MonitoringFormQuestion,
    MonitoringFormSubmission,
    MonitoringFormAnswer,
    Employee,
    Position,
)
from typing import TYPE_CHECKING, Optional, Set
from django.db.models import QuerySet, Q
from django.utils import timezone
from dataclasses import dataclass, field

class ServiceError(Exception):
    pass

class MonitoringFormNotFoundError(ServiceError):
    pass

class MonitoringFormPermissionError(ServiceError):
    pass

class SubmissionError(ServiceError):
    pass

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser as UserModel
else:
    UserModel = object

@dataclass
class MonitoringService:
    user: 'UserModel'
    MonitoringFormModel: type[MonitoringForm] = MonitoringForm
    MonitoringFormFieldModel: type[MonitoringFormField] = MonitoringFormField
    MonitoringFormQuestionModel: type[MonitoringFormQuestion] = MonitoringFormQuestion
    MonitoringFormSubmissionModel: type[MonitoringFormSubmission] = MonitoringFormSubmission
    MonitoringFormAnswerModel: type[MonitoringFormAnswer] = MonitoringFormAnswer
    EmployeeModel: type[Employee] = Employee
    PositionModel: type[Position] = Position
    _is_full_access: bool = field(init=False)

    def __post_init__(self) -> None:
        self._validate_access()
        self._is_full_access = self._checkout_full_access

    def _validate_access(self) -> None:
        '''
        validates if the user was provided, exists and is authenticated.
        '''
        if not self.user:
            raise MonitoringFormPermissionError('No se ha proporcionado un usuario válido.')
        if not self.user.is_authenticated:
            raise MonitoringFormPermissionError('El usuario proporcionado no está autenticado.')
        if not getattr(self.user, 'is_active', True):
            raise MonitoringFormPermissionError('El usuario se encuentra inactivo.')

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

    def _get_active_user_employees(self) -> QuerySet[Employee]:
        '''
        fetches active employee records linked to the current user.
        an employee is active if termination_date is null or >= today.
        '''
        today = timezone.now().date()
        return self.EmployeeModel.objects.filter(
            user=self.user
        ).filter(
            Q(termination_date__isnull=True) | Q(termination_date__gte=today)
        ).select_related('position')

    def _get_reporting_tree_employee_ids(self) -> Set[str]:
        '''
        uses Employee.get_reporting_tree_ids() to collect all employee IDs in the
        reporting tree (self and direct/indirect subordinates).
        '''
        tree_ids: Set[str] = set()
        user_employees = self._get_active_user_employees()
        for emp in user_employees:
            tree_ids.update(emp.get_reporting_tree_ids())
        return tree_ids

    def read_forms(self) -> QuerySet[MonitoringForm]:
        '''
        returns a queryset of allowed active forms to submit/view.
        '''
        base_qs = self.MonitoringFormModel.objects.filter(is_active=True)

        if self._is_full_access:
            return base_qs

        tree_ids = self._get_reporting_tree_employee_ids()
        if not tree_ids:
            return self.MonitoringFormModel.objects.none()

        today = timezone.now().date()
        employee_positions = self.EmployeeModel.objects.filter(
            id__in=tree_ids
        ).filter(
            Q(termination_date__isnull=True) | Q(termination_date__gte=today)
        ).values_list('position_id', 'position__hierarchy_level')

        positions = {pos_id for pos_id, _ in employee_positions if pos_id}
        hierarchy_levels = {h_level for _, h_level in employee_positions if h_level}

        if not positions and not hierarchy_levels:
            return self.MonitoringFormModel.objects.none()

        return base_qs.filter(
            human_resources_form_questions__question__is_active=True
        ).filter(
            Q(human_resources_form_questions__hierarchy_level__in=hierarchy_levels) |
            Q(human_resources_form_questions__position_id__in=positions) |
            Q(human_resources_form_questions__hierarchy_level__isnull=True, 
              human_resources_form_questions__position__isnull=True)
        ).distinct()

    def read_form_questions(self, form_id: str) -> QuerySet[MonitoringFormQuestion]:
        '''
        retrieves ordered questions for a specific form filtered by employee hierarchy level and position.
        '''
        tree_ids = self._get_reporting_tree_employee_ids()
        if not tree_ids and not self._is_full_access:
            return self.MonitoringFormQuestionModel.objects.none()

        base_qs = self.MonitoringFormQuestionModel.objects.filter(
            form_id=form_id,
            question__is_active=True
        ).select_related('question', 'position')

        if self._is_full_access:
            return base_qs.order_by('order')

        today = timezone.now().date()
        employee_positions = self.EmployeeModel.objects.filter(
            id__in=tree_ids
        ).filter(
            Q(termination_date__isnull=True) | Q(termination_date__gte=today)
        ).values_list('position_id', 'position__hierarchy_level')

        positions = {pos_id for pos_id, _ in employee_positions if pos_id}
        hierarchy_levels = {h_level for _, h_level in employee_positions if h_level}

        return base_qs.filter(
            Q(hierarchy_level__in=hierarchy_levels) |
            Q(position_id__in=positions) |
            Q(hierarchy_level__isnull=True, position__isnull=True)
        ).order_by('order')

    def read_submissions(self) -> QuerySet[MonitoringFormSubmission]:
        '''
        shows sent submissions from employees in the reporting tree (or all if full access),
        using select_related to optimize query loading.
        '''
        base_qs = self.MonitoringFormSubmissionModel.objects.select_related(
            'employee__user', 'employee__position', 'form'
        )

        if self._is_full_access:
            return base_qs

        tree_ids = self._get_reporting_tree_employee_ids()
        if not tree_ids:
            return self.MonitoringFormSubmissionModel.objects.none()

        return base_qs.filter(employee_id__in=tree_ids)
