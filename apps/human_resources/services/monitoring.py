from dataclasses import dataclass
from typing import ClassVar, Optional
from apps.human_resources.models import MonitoringForm, Position, MonitoringFormSchedule, MonitoringFormQuestion, MonitoringFormField, MonitoringPeriod, MonitoringFormSubmission, Employee, MonitoringFormAnswer
from apps.core.services.users import UsersService
from apps.human_resources.services.positions import PositionsService
from apps.human_resources.services.employees import EmployeesService
from django.utils import timezone
from django.db.models import QuerySet, Q, Count, Case, When, Value, IntegerField
from django.db import transaction, IntegrityError
from django.core.exceptions import ValidationError

class ServiceError(Exception):
    pass

class FormNotFound(ServiceError):
    pass

class SubmissionNotFound(ServiceError):
    pass

class PermissionsError(ServiceError):
    pass

@dataclass
class MonitoringFormsService(UsersService):
    form_model: type = MonitoringForm
    schedule_model: type = MonitoringFormSchedule
    question_model: type = MonitoringFormQuestion
    field_model: type = MonitoringFormField
    ACCESS_CONTEXTS: ClassVar[tuple[str, ...]] = (
        'acceso_total_usuarios',
        'acceso_total_colaboradores',
        'acceso_total_reportes_evaluaciones',
        'recursos_humanos',
    )

    def read_forms(self) -> QuerySet:
        base_qs = self.form_model.objects.select_related('schedule')
        if self._is_full_access:
            return base_qs
        return self._filter_by_hierarchy(base_qs)

    def _filter_by_hierarchy(self, queryset: QuerySet) -> QuerySet:
        '''
        Returns forms assigned to the user or any of their subordinates.
        '''
        positions_service = PositionsService(user=self.user)
        accessible_positions = positions_service.read_positions().values('id')
        
        hierarchy_levels = Position.objects.filter(id__in=accessible_positions)\
            .exclude(hierarchy_level__isnull=True)\
            .exclude(hierarchy_level='')\
            .values('hierarchy_level')

        return queryset.filter(
            Q(form_questions__position__id__in=accessible_positions) |
            Q(form_questions__hierarchy_level__in=hierarchy_levels) |
            Q(form_questions__position__isnull=True, form_questions__hierarchy_level__isnull=True)
        ).distinct()

    def read_fields(self) -> QuerySet:
        if not self._is_full_access:
            raise PermissionsError('No tienes permisos suficientes para acceder al catálogo de campos.')
            
        return self.field_model.objects.annotate(
            report_count=Count('form_questions__form', distinct=True)
        ).all()

    def read_field(self, *, pk: int) -> Optional[MonitoringFormField]:
        '''Returns a single field object or raises FormNotFound if not found or unauthorized.'''
        if not self._is_full_access:
            raise PermissionsError('No tienes permisos suficientes para acceder al catálogo de campos.')
            
        field = self.read_fields().filter(pk=pk).first()
        if field:
            return field

        raise FormNotFound(f'No se encontró ningún campo con el ID "{pk}".')

    def create_field(self, data: dict) -> MonitoringFormField:
        if not self._is_full_access:
            raise PermissionsError('No tienes permisos suficientes para crear campos de reportes.')

        try:
            with transaction.atomic():
                new_field = self.field_model(**data)
                new_field.full_clean()
                new_field.save()
            return new_field
        except ValidationError as e:
            if hasattr(e, 'message_dict'):
                messages = [f"{k}: {', '.join(v)}" for k, v in e.message_dict.items()]
                raise ServiceError(f"Datos inválidos: {'; '.join(messages)}")
            raise ServiceError(f"Datos inválidos: {', '.join(e.messages)}")
        except Exception as e:
            raise ServiceError(f"Error al crear el campo: {str(e)}")

    def update_field(self, field: MonitoringFormField, data: dict) -> MonitoringFormField:
        if not self._is_full_access:
            raise PermissionsError('No tienes permisos suficientes para actualizar campos de reportes.')

        try:
            with transaction.atomic():
                for key, value in data.items():
                    if key != 'id':  # Prevent modification of id
                        setattr(field, key, value)
                
                field.full_clean()
                field.save()
            return field
        except ValidationError as e:
            if hasattr(e, 'message_dict'):
                messages = [f"{k}: {', '.join(v)}" for k, v in e.message_dict.items()]
                raise ServiceError(f"Datos inválidos: {'; '.join(messages)}")
            raise ServiceError(f"Datos inválidos: {', '.join(e.messages)}")
        except Exception as e:
            raise ServiceError(f"Error al actualizar el campo: {str(e)}")

    def read_questions(self, form: MonitoringForm) -> QuerySet:
        """
        Returns only the questions applicable to the user's hierarchy or general ones.
        """
        questions_qs = form.form_questions.all().select_related('question', 'position')
        if self._is_full_access:
            return questions_qs
            
        positions_service = PositionsService(user=self.user)
        accessible_positions = positions_service.read_positions().values('id')
        
        hierarchy_levels = Position.objects.filter(id__in=accessible_positions)\
            .exclude(hierarchy_level__isnull=True)\
            .exclude(hierarchy_level='')\
            .values('hierarchy_level')
            
        return questions_qs.filter(
            Q(position__id__in=accessible_positions) |
            Q(hierarchy_level__in=hierarchy_levels) |
            Q(position__isnull=True, hierarchy_level__isnull=True)
        ).distinct()

    def read_form(self, *, pk: str) -> Optional[MonitoringForm]:
        '''Returns a single form object or None if not found or unauthorized.'''
        form = self.read_forms().filter(pk=pk).first()
        if form:
            return form

        if self.form_model.objects.filter(pk=pk).exists():
            raise PermissionsError(f'No tienes permiso para acceder al reporte de desempeño con ID "{pk}".')

        raise FormNotFound(f'No se encontró ningún reporte de desempeño con el ID "{pk}".')

    def _validate_schedule_logic(self, periodicity: str, week_of_month: str):
        is_monthly_or_longer = periodicity.endswith('m') or periodicity.endswith('y')
        
        if is_monthly_or_longer and week_of_month == self.schedule_model.WeekOfMonth.EVERY:
            raise ServiceError("Un reporte mensual (o mayor) no puede tener la semana de entrega como 'Todas'. Debe especificar una semana concreta del mes.")
            
        if not is_monthly_or_longer and week_of_month != self.schedule_model.WeekOfMonth.EVERY:
            raise ServiceError("Un reporte semanal o quincenal debe tener la semana de entrega configurada como 'Todas'.")

    def create_form(self, form_data: dict, schedule_data: dict, questions_data: list) -> MonitoringForm:
        if not self._is_full_access:
            raise PermissionsError('No tienes permisos suficientes para crear reportes de desempeño.')

        self._validate_schedule_logic(form_data.get('periodicity'), schedule_data.get('week_of_month'))

        try:
            with transaction.atomic():
                new_form = self.form_model(**form_data)
                new_form.full_clean()
                new_form.save()

                schedule = self.schedule_model(form=new_form, **schedule_data)
                schedule.full_clean()
                schedule.save()

                for q_data in questions_data:
                    if q_data and not q_data.get('DELETE', False):
                        q_data_copy = dict(q_data)
                        q_data_copy.pop('DELETE', None)
                        q_data_copy.pop('id', None)
                        q_data_copy.pop('form', None)
                        
                        question_obj = self.question_model(form=new_form, **q_data_copy)
                        question_obj.full_clean()
                        question_obj.save()

            return new_form
        except ValidationError as e:
            if hasattr(e, 'message_dict'):
                messages = [f"{k}: {', '.join(v)}" for k, v in e.message_dict.items()]
                raise ServiceError(f"Datos inválidos: {'; '.join(messages)}")
            raise ServiceError(f"Datos inválidos: {', '.join(e.messages)}")
        except IntegrityError:
            raise ServiceError("Ya existe un formulario con este ID único.")
        except Exception as e:
            raise ServiceError(f"Error al crear el formulario: {str(e)}")

    def update_form(self, form: MonitoringForm, form_data: dict, schedule_data: dict, questions_data: list) -> MonitoringForm:
        if not self._is_full_access:
            raise PermissionsError('No tienes permisos suficientes para actualizar reportes de desempeño.')

        self._validate_schedule_logic(form_data.get('periodicity', form.periodicity), schedule_data.get('week_of_month'))

        try:
            with transaction.atomic():
                for key, value in form_data.items():
                    if key != 'id':
                        setattr(form, key, value)
                
                form.full_clean()
                form.save()

                if hasattr(form, 'schedule'):
                    for key, value in schedule_data.items():
                        setattr(form.schedule, key, value)
                    form.schedule.full_clean()
                    form.schedule.save()
                else:
                    schedule = self.schedule_model(form=form, **schedule_data)
                    schedule.full_clean()
                    schedule.save()

                for q_data in questions_data:
                    if not q_data:
                        continue
                    
                    q_instance = q_data.get('id')
                    should_delete = q_data.get('DELETE', False)
                    
                    if should_delete:
                        if q_instance and q_instance.pk:
                            q_instance.delete()
                        continue
                        
                    q_data_copy = dict(q_data)
                    q_data_copy.pop('DELETE', None)
                    q_data_copy.pop('id', None)
                    q_data_copy.pop('form', None)

                    if q_instance and q_instance.pk:
                        for k, v in q_data_copy.items():
                            setattr(q_instance, k, v)
                        q_instance.full_clean()
                        q_instance.save()
                    else:
                        question_obj = self.question_model(form=form, **q_data_copy)
                        question_obj.full_clean()
                        question_obj.save()

            return form
        except ValidationError as e:
            if hasattr(e, 'message_dict'):
                messages = [f"{k}: {', '.join(v)}" for k, v in e.message_dict.items()]
                raise ServiceError(f"Datos inválidos: {'; '.join(messages)}")
            raise ServiceError(f"Datos inválidos: {', '.join(e.messages)}")
        except IntegrityError:
            raise ServiceError("Error de integridad de datos. Revisa si hay duplicados.")
        except Exception as e:
            raise ServiceError(f"Error al actualizar el formulario: {str(e)}")


@dataclass
class ExpectedSubmission:
    employee: object
    period: object
    form: object
    submission: Optional[object]
    status_code: str
    status_label: str
    questions: Optional[list] = None
    general_questions: Optional[list] = None
    hierarchy_questions: Optional[list] = None
    position_questions: Optional[list] = None

    @property
    def pk(self) -> int:
        if self.submission and hasattr(self.submission, 'pk') and self.submission.pk:
            return self.submission.pk
        return self.period.id

    @property
    def is_closed(self) -> bool:
        if not self.submission or self.submission.status == 'draft':
            return False
        return timezone.now() > self.period.end_date

@dataclass
class MonitoringSubmissionService(UsersService):
    ACCESS_CONTEXTS: ClassVar[tuple[str, ...]] = (
        'acceso_total_usuarios',
        'acceso_total_colaboradores',
        'acceso_total_reportes_evaluaciones',
        'recursos_humanos',
    )
    
    def _get_applicable_employees_for_form(self, form: MonitoringForm, allowed_employees: QuerySet) -> list:
        questions = form.form_questions.all()
        applicable = set()
        for q in questions:
            if q.position_id:
                applicable.update(list(allowed_employees.filter(position_id=q.position_id)))
            elif q.hierarchy_level:
                applicable.update(list(allowed_employees.filter(position__hierarchy_level=q.hierarchy_level)))
            else:
                applicable.update(list(allowed_employees))
        return list(applicable)

    def read_periods(self) -> QuerySet:
        emp_service = EmployeesService(user=self.user)
        accessible_employees = emp_service.read_employees()
        
        if not accessible_employees.exists():
            return MonitoringPeriod.objects.none()
            
        position_ids = accessible_employees.values_list('position_id', flat=True)
        hierarchy_levels = Position.objects.filter(id__in=position_ids).exclude(hierarchy_level__isnull=True).exclude(hierarchy_level='').values_list('hierarchy_level', flat=True)
        
        applicable_forms = MonitoringForm.objects.filter(
            Q(form_questions__position_id__in=position_ids) |
            Q(form_questions__hierarchy_level__in=hierarchy_levels) |
            Q(form_questions__position__isnull=True, form_questions__hierarchy_level__isnull=True)
        ).distinct()
        
        return MonitoringPeriod.objects.filter(form__in=applicable_forms).select_related('form').order_by('-start_date')
        
    def read_submissions(self, periods_qs: QuerySet) -> list:
        emp_service = EmployeesService(user=self.user)
        accessible_employees = emp_service.read_employees().select_related('position', 'user')
        
        expected_list = []
        now = timezone.now()
        
        ordered_periods = periods_qs.order_by('-start_date')
        
        for period in ordered_periods:
            applicable_employees = self._get_applicable_employees_for_form(period.form, accessible_employees)
            if not applicable_employees:
                continue
                
            existing_submissions = MonitoringFormSubmission.objects.filter(
                period=period,
                employee__in=applicable_employees
            ).select_related('employee', 'form', 'period')
            
            subs_by_emp_id = {sub.employee_id: sub for sub in existing_submissions}
            
            for emp in applicable_employees:
                sub = subs_by_emp_id.get(emp.id)
                status_code, status_label = self._compute_status(period, sub, now)
                expected_list.append(
                    ExpectedSubmission(
                        employee=emp,
                        period=period,
                        form=period.form,
                        submission=sub,
                        status_code=status_code,
                        status_label=status_label
                    )
                )
        status_priority = {
            'abierto_para_envio': 1,
            'pendiente_de_envio': 1,
            'enviado_a_tiempo': 2,
            'enviado_fuera_de_tiempo': 2,
            'proximo_a_abrir': 3,
        }

        def get_sort_key(es: ExpectedSubmission):
            priority = status_priority.get(es.status_code, 4)
            if priority in (1, 2):
                dt_key = -es.period.start_date.timestamp()
            else:
                dt_key = es.period.start_date.timestamp()
            return (priority, dt_key, -es.period.id, str(es.employee.id))

        expected_list.sort(key=get_sort_key)
        return expected_list

    def read_submission(self, pk: int, employee_id: Optional[str] = None) -> ExpectedSubmission:
        pk_int = int(pk)

        submission = MonitoringFormSubmission.objects.filter(pk=pk_int).select_related(
            'period', 'employee', 'form', 'employee__position', 'employee__user'
        ).first()

        if submission:
            period = submission.period
            employee = submission.employee
        else:
            period = MonitoringPeriod.objects.filter(pk=pk_int).select_related('form').first()
            if not period:
                raise SubmissionNotFound(f'No se encontró ningún reporte o periodo de evaluación con ID "{pk_int}".')

            emp_service = EmployeesService(user=self.user)
            accessible_employees = emp_service.read_employees().select_related('position', 'user')

            if employee_id:
                employee = accessible_employees.filter(pk=employee_id).first()
                if not employee:
                    if Employee.objects.filter(pk=employee_id).exists():
                        raise PermissionsError(f'No tienes permiso para acceder a los reportes del colaborador con ID "{employee_id}".')
                    raise SubmissionNotFound(f'No se encontró ningún colaborador con ID "{employee_id}".')
            else:
                employee = accessible_employees.filter(user=self.user).first()
                if not employee:
                    applicable = self._get_applicable_employees_for_form(period.form, accessible_employees)
                    if applicable:
                        employee = applicable[0]
                    else:
                        employee = accessible_employees.first()

            if not employee:
                raise SubmissionNotFound('No se encontró ningún colaborador asociado para consultar este reporte.')

        emp_service = EmployeesService(user=self.user)
        accessible_employees = emp_service.read_employees()
        if not accessible_employees.filter(pk=employee.id).exists():
            raise PermissionsError(f'No tienes permiso para acceder al reporte del colaborador con ID "{employee.id}".')

        applicable = self._get_applicable_employees_for_form(period.form, Employee.objects.filter(pk=employee.id))
        if not applicable:
            raise PermissionsError('El reporte seleccionado no aplica para este colaborador.')

        now = timezone.now()
        status_code, status_label = self._compute_status(period, submission, now)

        employee_position = employee.position
        hierarchy_level = employee_position.hierarchy_level if employee_position else None

        questions_qs = MonitoringFormQuestion.objects.filter(
            form=period.form
        ).filter(
            Q(position=employee_position) |
            (Q(position__isnull=True) & Q(hierarchy_level=hierarchy_level)) |
            (Q(position__isnull=True) & (Q(hierarchy_level__isnull=True) | Q(hierarchy_level='')))
        ).select_related('question', 'position', 'form')

        if hierarchy_level:
            priority_cases = [
                When(position__isnull=True, hierarchy_level__isnull=True, then=Value(1)),
                When(position__isnull=True, hierarchy_level='', then=Value(1)),
                When(position__isnull=True, hierarchy_level=hierarchy_level, then=Value(2)),
                When(position=employee_position, then=Value(3)),
            ]
        else:
            priority_cases = [
                When(position__isnull=True, hierarchy_level__isnull=True, then=Value(1)),
                When(position__isnull=True, hierarchy_level='', then=Value(1)),
                When(position=employee_position, then=Value(2)),
            ]

        questions = list(
            questions_qs.annotate(
                priority=Case(
                    *priority_cases,
                    default=Value(4),
                    output_field=IntegerField()
                )
            ).order_by('priority', 'order', 'id')
        )

        answers_dict = {} #attach answers to the questions if exist
        if submission:
            answers = MonitoringFormAnswer.objects.filter(submission=submission)
            answers_dict = {ans.question_id: ans.value for ans in answers}
        
        for q in questions:
            q.answer_value = answers_dict.get(q.id)

        general_questions = [q for q in questions if getattr(q, 'priority', 4) == 1]
        hierarchy_questions = [q for q in questions if getattr(q, 'priority', 4) == 2]
        position_questions = [q for q in questions if getattr(q, 'priority', 4) == 3]

        return ExpectedSubmission(
            employee=employee,
            period=period,
            form=period.form,
            submission=submission,
            status_code=status_code,
            status_label=status_label,
            questions=questions,
            general_questions=general_questions,
            hierarchy_questions=hierarchy_questions,
            position_questions=position_questions
        )
        
    @transaction.atomic
    def create_submission(self, period_id: int, employee_id: str, data: dict, is_draft: bool = False) -> MonitoringFormSubmission:
        period = MonitoringPeriod.objects.select_related('form').filter(pk=period_id).first()
        if not period:
            raise SubmissionNotFound("Periodo no encontrado.")
            
        emp_service = EmployeesService(user=self.user)
        accessible_employees = emp_service.read_employees()
        employee = accessible_employees.filter(pk=employee_id).first()
        
        if not employee:
            raise PermissionsError("Colaborador no encontrado o sin acceso.")
            
        if employee.user != self.user:
            raise PermissionsError("No tienes permiso para realizar envíos en nombre de otro colaborador.")
            
        applicable = self._get_applicable_employees_for_form(period.form, Employee.objects.filter(pk=employee.id))
        if not applicable:
            raise PermissionsError('El reporte seleccionado no aplica para este colaborador.')
            
        now = timezone.now()
        if now < period.start_date and not is_draft:
            raise ServiceError("La ventana de envío aún no está abierta. Solo puedes guardar borradores.")
            
        sub = MonitoringFormSubmission.objects.filter(period=period, employee=employee).first()
        if sub and sub.status != MonitoringFormSubmission.SubmissionStatus.DRAFT:
            if now > period.end_date:
                raise ServiceError("El periodo de envío ha cerrado y el reporte ya fue enviado. No puedes hacer modificaciones.")
            
        if not sub:
            sub = MonitoringFormSubmission(period=period, employee=employee, form=period.form)
            
        sub.status = MonitoringFormSubmission.SubmissionStatus.DRAFT if is_draft else MonitoringFormSubmission.SubmissionStatus.SUBMITTED
        if not is_draft:
            sub.submitted_at = now
            
        sub.save()
        self._save_answers(sub, data)
        return sub

    @transaction.atomic
    def update_submission(self, submission_id: int, data: dict, is_draft: bool = False) -> MonitoringFormSubmission:
        sub = MonitoringFormSubmission.objects.select_related('period', 'employee', 'employee__user').filter(pk=submission_id).first()
        if not sub:
            raise SubmissionNotFound("Envío no encontrado.")
            
        if sub.employee.user != self.user:
            raise PermissionsError("No tienes permiso para realizar envíos en nombre de otro colaborador.")
            
        now = timezone.now()
        if sub.status != MonitoringFormSubmission.SubmissionStatus.DRAFT:
            if now > sub.period.end_date:
                raise ServiceError("El periodo de envío ha cerrado y el reporte ya fue enviado. No puedes hacer modificaciones.")

        if now < sub.period.start_date and not is_draft:
            raise ServiceError("La ventana de envío aún no está abierta. Solo puedes guardar borradores.")
            
        sub.status = MonitoringFormSubmission.SubmissionStatus.DRAFT if is_draft else MonitoringFormSubmission.SubmissionStatus.SUBMITTED
        if not is_draft:
            sub.submitted_at = now
            
        sub.save()
        self._save_answers(sub, data)
        return sub

    def _save_answers(self, sub: MonitoringFormSubmission, data: dict):
        employee_position = sub.employee.position
        hierarchy_level = employee_position.hierarchy_level if employee_position else None

        questions_qs = MonitoringFormQuestion.objects.filter(
            form=sub.form
        ).filter(
            Q(position=employee_position) |
            (Q(position__isnull=True) & Q(hierarchy_level=hierarchy_level)) |
            (Q(position__isnull=True) & (Q(hierarchy_level__isnull=True) | Q(hierarchy_level='')))
        ).select_related('question')
        
        answers_to_create = []
        for q in questions_qs:
            raw_val = data.get(f'question_{q.id}')
            if raw_val is not None and str(raw_val).strip() != '':
                if isinstance(raw_val, dict):
                    value_json = raw_val
                else:
                    display_val = str(raw_val)
                    if q.question.response_type == MonitoringFormField.ResponseTypeChoices.BOOLEAN:
                        bool_val = str(raw_val).lower() in ['true', '1', 'on']
                        display_val = "Sí" if bool_val else "No"
                        raw_val = bool_val
                    elif q.question.response_type == MonitoringFormField.ResponseTypeChoices.PERCENTAGE:
                        display_val = f"{raw_val}%"
                    elif q.question.response_type == MonitoringFormField.ResponseTypeChoices.SCALE_1_5:
                        display_val = f"{raw_val}/5"
                        
                    value_json = {
                        "answer": raw_val,
                        "display": display_val
                    }
                
                ans = MonitoringFormAnswer.objects.filter(submission=sub, question=q).first()
                if ans:
                    ans.value = value_json
                    ans.save()
                else:
                    answers_to_create.append(MonitoringFormAnswer(
                        submission=sub,
                        question=q,
                        value=value_json
                    ))
            else:
                MonitoringFormAnswer.objects.filter(submission=sub, question=q).delete()
        
        if answers_to_create:
            MonitoringFormAnswer.objects.bulk_create(answers_to_create)

    @transaction.atomic
    def delete_submission(self, submission_id: int):
        sub = MonitoringFormSubmission.objects.select_related('period', 'employee', 'employee__user').filter(pk=submission_id).first()
        if not sub:
            raise SubmissionNotFound("Envío no encontrado.")
            
        if sub.employee.user != self.user:
            raise PermissionsError("No tienes permiso para eliminar este envío.")
            
        now = timezone.now()
        if now > sub.period.end_date:
            raise ServiceError("El periodo de envío ha cerrado. No puedes eliminar el reporte.")
            
        sub.delete()

    def _compute_status(self, period: MonitoringPeriod, sub: Optional[MonitoringFormSubmission], now) -> tuple[str, str]:
        if sub and sub.status in [MonitoringFormSubmission.SubmissionStatus.SUBMITTED, MonitoringFormSubmission.SubmissionStatus.REVIEWED]:
            if sub.submitted_at and sub.submitted_at <= period.end_date:
                return ('enviado_a_tiempo', 'Enviado a tiempo')
            else:
                return ('enviado_fuera_de_tiempo', 'Enviado fuera de tiempo')
                
        if now < period.start_date:
            return ('proximo_a_abrir', 'Próximo a abrir')
        elif period.start_date <= now <= period.end_date:
            return ('abierto_para_envio', 'Abierto para envío')
        else:
            return ('pendiente_de_envio', 'Pendiente de envío')
            
    def stats(self, expected_submissions: list) -> dict:
        kpis = {
            'open_to_send': 0,

            'sent_on_time': 0,
            'sent_on_time_pct': 0, #which is the percentage of completed reports/submissions vs assigned tasks

            'sent_out_of_time': 0,
            'sent_out_of_time_pct': 0,

            'pending_to_send': 0,
            'pending_to_send_pct': 0,

            'next_to_open': 0,
        }
        for es in expected_submissions:
            if es.status_code == 'abierto_para_envio':
                kpis['open_to_send'] += 1
            elif es.status_code == 'enviado_a_tiempo':
                kpis['sent_on_time'] += 1
            elif es.status_code == 'enviado_fuera_de_tiempo':
                kpis['sent_out_of_time'] += 1
            elif es.status_code == 'pendiente_de_envio':
                kpis['pending_to_send'] += 1
            elif es.status_code == 'proximo_a_abrir':
                kpis['next_to_open'] += 1
        
        effective_submissions = kpis['open_to_send'] + kpis['sent_on_time'] + kpis['sent_out_of_time'] + kpis['pending_to_send']

        kpis['sent_on_time_pct'] = (kpis['sent_on_time'] / effective_submissions) * 100 if effective_submissions > 0 else 0
        kpis['sent_out_of_time_pct'] = (kpis['sent_out_of_time'] / effective_submissions) * 100 if effective_submissions > 0 else 0
        kpis['pending_to_send_pct'] = (kpis['pending_to_send'] / effective_submissions) * 100 if effective_submissions > 0 else 0
        
        return kpis
    