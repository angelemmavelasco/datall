from dataclasses import dataclass
from typing import ClassVar, Optional
from apps.human_resources.models import MonitoringForm, Position, MonitoringFormSchedule, MonitoringFormQuestion, MonitoringFormField, MonitoringPeriod, MonitoringFormSubmission
from apps.core.services.users import UsersService
from apps.human_resources.services.positions import PositionsService
from apps.human_resources.services.employees import EmployeesService
from django.utils import timezone
from django.db.models import QuerySet, Q, Count
from django.db import transaction, IntegrityError
from django.core.exceptions import ValidationError

class ServiceError(Exception):
    pass

class FormNotFound(ServiceError):
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
        
        return MonitoringPeriod.objects.filter(form__in=applicable_forms).select_related('form')
        
    def read_submissions(self, periods_qs: QuerySet) -> list:
        emp_service = EmployeesService(user=self.user)
        accessible_employees = emp_service.read_employees().select_related('position', 'user')
        
        expected_list = []
        now = timezone.now()
        
        for period in periods_qs:
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
        return expected_list
        
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
            
    def calculate_kpis(self, expected_submissions: list) -> dict:
        kpis = {
            'open_to_send': 0,
            'sent_on_time': 0,
            'sent_out_of_time': 0,
            'pending_to_send': 0,
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
        return kpis
    