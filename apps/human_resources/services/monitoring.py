from dataclasses import dataclass
from typing import ClassVar, Optional
from apps.human_resources.models import MonitoringForm, Position, MonitoringFormSchedule, MonitoringFormQuestion, MonitoringFormField
from apps.core.services.users import UsersService
from apps.human_resources.services.positions import PositionsService
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
