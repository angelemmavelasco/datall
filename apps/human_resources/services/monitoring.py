from dataclasses import dataclass
from typing import ClassVar, Optional
from apps.human_resources.models import MonitoringForm, Position, MonitoringFormSchedule, MonitoringFormQuestion
from apps.core.services.users import UsersService
from apps.human_resources.services.employees import EmployeesService
from django.db.models import QuerySet, Q
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
        emp_service = EmployeesService(user=self.user)
        my_tree_employees = emp_service.read_employees()

        if not my_tree_employees.exists():
            return queryset.none()

        position_ids = list(my_tree_employees.values_list('position_id', flat=True).distinct())
        
        hierarchy_levels = list(
            Position.objects.filter(id__in=position_ids)
            .exclude(hierarchy_level__isnull=True)
            .exclude(hierarchy_level='')
            .values_list('hierarchy_level', flat=True)
            .distinct()
        )

        return queryset.filter(
            Q(form_questions__position__id__in=position_ids) |
            Q(form_questions__hierarchy_level__in=hierarchy_levels) |
            Q(form_questions__position__isnull=True, form_questions__hierarchy_level__isnull=True)
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
