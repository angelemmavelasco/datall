from ..models import (
    MonitoringForm,
    MonitoringFormField,
    MonitoringFormQuestion,
    MonitoringFormSubmission,
    MonitoringFormAnswer,
    Employee,
    Position,
)
from typing import TYPE_CHECKING, Optional, Set, List
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
        ).select_related('user', 'position__department', 'manager__user')

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

    def read_forms(self, *, own_forms: bool = True) -> List[MonitoringForm]:
        '''
        returns unique forms with dynamic count metrics attached.
        '''
        base_qs = self.MonitoringFormModel.objects.filter(is_active=True).prefetch_related(
            'human_resources_form_questions__position__department',
            'human_resources_form_questions__question'
        )

        today = timezone.now().date()
        target_employee_qs = self.EmployeeModel.objects.filter(
            Q(termination_date__isnull=True) | Q(termination_date__gte=today)
        )

        if own_forms:
            own_ids = [emp.id for emp in self._get_active_user_employees()]
            if not own_ids:
                return []
            target_employee_qs = target_employee_qs.filter(id__in=own_ids)
        else:
            if self._is_full_access:
                target_employee_qs = target_employee_qs.exclude(user=self.user)
            else:
                tree_ids = self._get_reporting_tree_employee_ids()
                own_ids = {emp.id for emp in self._get_active_user_employees()}
                subordinate_ids = tree_ids - own_ids
                if not subordinate_ids:
                    return []
                target_employee_qs = target_employee_qs.filter(id__in=subordinate_ids)
        
        valid_positions = set(target_employee_qs.values_list('position_id', flat=True))
        valid_levels = set(target_employee_qs.values_list('position__hierarchy_level', flat=True))

        matched_forms = []
        for form in base_qs:
            q_levels_raw = set()
            q_positions_raw = set()
            for q in form.human_resources_form_questions.all():
                if q.hierarchy_level:
                    q_levels_raw.add(q.hierarchy_level)
                if q.position_id:
                    q_positions_raw.add(q.position_id)
            
            is_relevant = False
            if self._is_full_access and not own_forms:
                is_relevant = True
            else:
                if q_positions_raw.intersection(valid_positions):
                    is_relevant = True
                elif q_levels_raw.intersection(valid_levels):
                    is_relevant = True
                elif not q_positions_raw and not q_levels_raw:
                    is_relevant = True
            
            if is_relevant:
                if not q_positions_raw and not q_levels_raw:
                    count = target_employee_qs.count()
                else:
                    count = target_employee_qs.filter(
                        Q(position_id__in=q_positions_raw) | Q(position__hierarchy_level__in=q_levels_raw)
                    ).distinct().count()
                
                if count == 0 and not (self._is_full_access and not own_forms):
                    continue

                form.assigned_employees_count = count
                
                q_levels_display = {q.get_hierarchy_level_display() for q in form.human_resources_form_questions.all() if q.hierarchy_level}
                q_positions_display = {q.position.name.title() for q in form.human_resources_form_questions.all() if q.position}
                
                form.target_levels_display = ", ".join(sorted(q_levels_display)) if q_levels_display else "Todos"
                form.target_positions_display = ", ".join(sorted(q_positions_display)) if q_positions_display else "Todas"
                
                matched_forms.append(form)

        return matched_forms

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

    def read_form_detail(self, form_id: str) -> Optional[MonitoringForm]:
        # Reuse read_forms logic but filter by ID
        # Since read_forms computes everything globally, we can just filter it.
        own_forms = self.read_forms(own_forms=True)
        sub_forms = self.read_forms(own_forms=False)
        
        for f in own_forms:
            if f.id == form_id:
                return f
        for f in sub_forms:
            if f.id == form_id:
                return f
        
        # If it doesn't match own or subordinates, but user is full access, it might be an inactive form.
        # But read_forms only returns active forms.
        # Let's fallback if the form wasn't in the active matching forms.
        # For full access, they can view inactive forms detail if needed.
        if self._is_full_access:
            return self.MonitoringFormModel.objects.filter(id=form_id).first()
            
        raise MonitoringFormPermissionError('No tienes permiso para ver los detalles de este formulario o no existe.')

    from django.db import transaction

    @transaction.atomic
    def create_form(self, form_data: dict, formset_data: list) -> MonitoringForm:
        if not self._is_full_access:
            raise MonitoringFormPermissionError('Solo los administradores pueden crear formularios de monitoreo.')
            
        form_instance = self.MonitoringFormModel.objects.create(**form_data)
        
        for q_data in formset_data:
            if not q_data.get('DELETE', False):
                self.MonitoringFormQuestionModel.objects.create(
                    form=form_instance,
                    question=q_data['question'],
                    order=q_data.get('order', 1),
                    hierarchy_level=q_data.get('hierarchy_level'),
                    position=q_data.get('position')
                )
                
        return form_instance

    @transaction.atomic
    def update_form(self, form_instance: MonitoringForm, form_data: dict, formset_data: list, deleted_questions: list) -> MonitoringForm:
        if not self._is_full_access:
            raise MonitoringFormPermissionError('Solo los administradores pueden editar formularios de monitoreo.')
            
        for key, value in form_data.items():
            setattr(form_instance, key, value)
        form_instance.save()
        
        # Handle deletes
        if deleted_questions:
            self.MonitoringFormQuestionModel.objects.filter(id__in=deleted_questions).delete()
            
        # Handle updates and creates
        for q_data in formset_data:
            q_id = q_data.get('id')
            if q_id:
                q_instance = self.MonitoringFormQuestionModel.objects.get(id=q_id)
                q_instance.question = q_data['question']
                q_instance.order = q_data.get('order', 1)
                q_instance.hierarchy_level = q_data.get('hierarchy_level')
                q_instance.position = q_data.get('position')
                q_instance.save()
            else:
                self.MonitoringFormQuestionModel.objects.create(
                    form=form_instance,
                    question=q_data['question'],
                    order=q_data.get('order', 1),
                    hierarchy_level=q_data.get('hierarchy_level'),
                    position=q_data.get('position')
                )
                
        return form_instance
