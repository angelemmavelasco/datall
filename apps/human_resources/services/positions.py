from dataclasses import dataclass
from typing import ClassVar, Optional
from django.utils import timezone
from django.db import transaction, IntegrityError
from django.core.exceptions import ValidationError

from apps.human_resources.models import Position, PositionSkill, Skill, PositionKPI
from apps.core.services.users import UsersService
from apps.human_resources.services.employees import EmployeesService
from django.db.models import QuerySet, Count, Q, When, Value, Case, Sum, Prefetch


class ServiceError(Exception):
    pass

class PositionNotFound(ServiceError):
    pass

class PermissionsError(ServiceError):
    pass

@dataclass
class PositionsService(UsersService):
    position_model: type = Position
    position_skill_model: type = PositionSkill
    position_kpi_model: type = PositionKPI
    ACCESS_CONTEXTS: ClassVar[tuple[str, ...]] = (
        'acceso_total_usuarios',
        'acceso_total_posiciones',
        'recursos_humanos',
    )

    def read_positions(self) -> QuerySet:
        today = timezone.now().date()
        is_active_emp = Q(
            employees__hire_date__lte=today,
        ) & (
            Q(employees__termination_date__isnull=True) |
            Q(employees__termination_date__gte=today)
        )
        if self._is_full_access:
            base_qs = self.position_model.objects.select_related('department').annotate(
                associated_skills_count = Count('position_skills', distinct=True),
                associated_kpis_count = Count('kpis', distinct=True),
                associated_active_employees_count = Count('employees',filter=is_active_emp, distinct=True),
                profile_completed=Case(
                    When(
                        Q(
                            associated_skills_count__gt=0
                        ) & Q(
                            associated_kpis_count__gt=0
                        ) & ~Q(
                            description__isnull=True
                        ) & ~Q(
                            description=''
                        ), then=Value(True)), default=Value(False),
                ),
            )
        else:
            employees_service = EmployeesService(user=self.user)
            accessible_employees = employees_service.read_employees()

            base_qs = self.position_model.objects.select_related('department').filter(
                employees__in=accessible_employees
            ).annotate(
                associated_skills_count = Count('position_skills', distinct=True),
                associated_kpis_count = Count('kpis', distinct=True),
                associated_active_employees_count = Count('employees',filter=is_active_emp, distinct=True),
                profile_completed=Case(
                    When(
                        Q(
                            associated_skills_count__gt=0
                        ) & Q(
                            associated_kpis_count__gt=0
                        ) & ~Q(
                            description__isnull=True
                        ) & ~Q(
                            description=''
                        ), then=Value(True)), default=Value(False),
                ),
            )

        return base_qs

    def create_position(self, position_data: dict, skills_data: list, kpis_data: list) -> Position:
        if not self._is_full_access:
            raise PermissionsError('No tienes permisos suficientes para crear posiciones.')

        try:
            with transaction.atomic():
                new_position = self.position_model(**position_data)
                new_position.full_clean()
                new_position.save()

                for skill_data in skills_data:
                    if skill_data and not skill_data.get('DELETE', False):
                        skill_data_copy = dict(skill_data)
                        skill_data_copy.pop('DELETE', None)
                        skill_data_copy.pop('id', None)
                        skill_data_copy.pop('position', None)
                        
                        position_skill = self.position_skill_model(position=new_position, **skill_data_copy)
                        position_skill.full_clean()
                        position_skill.save()

                for kpi_data in kpis_data:
                    if kpi_data and not kpi_data.get('DELETE', False):
                        kpi_data_copy = dict(kpi_data)
                        kpi_data_copy.pop('DELETE', None)
                        kpi_data_copy.pop('id', None)
                        kpi_data_copy.pop('position', None)
                        
                        position_kpi = self.position_kpi_model(position=new_position, **kpi_data_copy)
                        position_kpi.full_clean()
                        position_kpi.save()

            return new_position
        except ValidationError as e:
            if hasattr(e, 'message_dict'):
                messages = [f"{k}: {', '.join(v)}" for k, v in e.message_dict.items()]
                raise ServiceError(f"Datos inválidos: {'; '.join(messages)}")
            raise ServiceError(f"Datos inválidos: {', '.join(e.messages)}")
        except IntegrityError:
            raise ServiceError("Ya existe una posición con esos datos únicos.")
        except Exception as e:
            raise ServiceError(f"Error al crear la posición: {str(e)}")

    def update_position(self, position: Position, position_data: dict, skills_data: list, kpis_data: list) -> Position:
        if not self._is_full_access:
            raise PermissionsError('No tienes permisos suficientes para actualizar posiciones.')

        try:
            with transaction.atomic():
                for key, value in position_data.items():
                    if key != 'id':
                        setattr(position, key, value)
                
                position.full_clean()
                position.save()

                for skill_data in skills_data:
                    if not skill_data:
                        continue
                    
                    skill_instance = skill_data.get('id')
                    should_delete = skill_data.get('DELETE', False)
                    
                    if should_delete:
                        if skill_instance and skill_instance.pk:
                            skill_instance.delete()
                        continue
                        
                    skill_data_copy = dict(skill_data)
                    skill_data_copy.pop('DELETE', None)
                    skill_data_copy.pop('id', None)
                    skill_data_copy.pop('position', None)

                    if skill_instance and skill_instance.pk:
                        for k, v in skill_data_copy.items():
                            setattr(skill_instance, k, v)
                        skill_instance.full_clean()
                        skill_instance.save()
                    else:
                        position_skill = self.position_skill_model(position=position, **skill_data_copy)
                        position_skill.full_clean()
                        position_skill.save()

                for kpi_data in kpis_data:
                    if not kpi_data:
                        continue
                        
                    kpi_instance = kpi_data.get('id')
                    should_delete = kpi_data.get('DELETE', False)
                    
                    if should_delete:
                        if kpi_instance and kpi_instance.pk:
                            kpi_instance.delete()
                        continue
                        
                    kpi_data_copy = dict(kpi_data)
                    kpi_data_copy.pop('DELETE', None)
                    kpi_data_copy.pop('id', None)
                    kpi_data_copy.pop('position', None)

                    if kpi_instance and kpi_instance.pk:
                        for k, v in kpi_data_copy.items():
                            setattr(kpi_instance, k, v)
                        kpi_instance.full_clean()
                        kpi_instance.save()
                    else:
                        position_kpi = self.position_kpi_model(position=position, **kpi_data_copy)
                        position_kpi.full_clean()
                        position_kpi.save()

            return position

        except ValidationError as e:
            if hasattr(e, 'message_dict'):
                messages = [f"{k}: {', '.join(v)}" for k, v in e.message_dict.items()]
                raise ServiceError(f"Datos inválidos: {'; '.join(messages)}")
            raise ServiceError(f"Datos inválidos: {', '.join(e.messages)}")
        except IntegrityError:
            raise ServiceError("Ya existe una posición con esos datos únicos (ID duplicado).")
        except Exception as e:
            raise ServiceError(f"Error al actualizar la posición: {str(e)}")

    def read_position(self, *, pk: str) -> Optional[Position]:
        position = self.read_positions().prefetch_related('kpis').filter(pk=pk).first()
        if position:
            return position

        if self.position_model.objects.filter(pk=pk).exists():
            raise PermissionsError(f'No tienes permiso para acceder a la posición con ID "{pk}".')

        raise PositionNotFound(f'No se encontró ninguna posición con el ID "{pk}".')

    def read_position_employees(self, position: Position, active: bool | None = True) -> QuerySet:
        '''returns a list of associated employees, they can be filtered by status'''
        today = timezone.now().date()
        employees_service = EmployeesService(user=self.user)
        base_qs = employees_service.read_employees().filter(position=position)
        is_active_filter = Q(hire_date__lte=today) & (
                Q(termination_date__isnull=True) | Q(termination_date__gte=today)
        )
        if active is True:
            return base_qs.filter(is_active_filter)
        elif active is False:
            return base_qs.exclude(is_active_filter)
        return base_qs

    def read_position_skills(self, position: Position) -> QuerySet:
        return self.position_skill_model.objects.select_related('skill').filter(position=position)

@dataclass
class PositionsStats:
    '''dedicated only to give general stats about positions'''
    position_service: PositionsService

    @property
    def _base_qs(self) -> QuerySet:
        return self.position_service.read_positions()

    def stats(self, *, qs: QuerySet) -> dict:
        base_qs = qs if qs else self._base_qs
        return base_qs.aggregate(
            positions_count=Count('pk', distinct=True),
            skills_count=Count('position_skills__skill', distinct=True),
            position_profiles_count=Count('profile_completed', distinct=True, filter=Q(profile_completed=True)),
            assigned_employees_count=Sum('associated_active_employees_count'),
        )

@dataclass
class SkillsService(PositionsService):
    '''dedicated to retrieve information abvout the skill associated to positions'''
    skill_model: type = Skill

    def read_skills(self) -> QuerySet:
        '''
        return a qs with the skills associated.
        if the user is full access, the queryset will include all existing skills
        no matter if that skill has associated position with active employees or not, but
        if the user is no full access, is only be allowed to view
        positions where there are active employees which the main user has acess to.

        '''

        if self._is_full_access:
             return self.skill_model.objects.prefetch_related(
                'position_requirements',
            ).distinct().order_by('id')

        allowed_positions = self.read_positions()
        # base filter to know which employees im associated to
        today = timezone.now().date()
        is_active_emp = Q(
            position__employees__hire_date__lte=today,
        ) & (
            Q(position__employees__termination_date__isnull=True) |
            Q(position__employees__termination_date__gte=today)
        )
        allowed_employees = EmployeesService(user=self.user).read_employees()
        filtered_reqs = self.position_skill_model.objects.filter(
            position__in=allowed_positions,
            position__employees__in=allowed_employees
        ).filter(is_active_emp).distinct().select_related('position')
        base_qs = self.skill_model.objects.filter(
            position_requirements__in=filtered_reqs
        ).prefetch_related(
            Prefetch('position_requirements', queryset=filtered_reqs)
        ).distinct().order_by('id')
        return base_qs

    def read_skill(self, pk : int) -> Optional[Skill]:
        return self.read_skills().filter(pk=pk).first()

    def create_skill(self, skill_data: dict) -> Skill:
        if not self._is_full_access:
            raise PermissionsError('No tienes permisos suficientes para crear habilidades / competencias.')
        
        try:
            with transaction.atomic():
                new_skill = self.skill_model(**skill_data)
                new_skill.full_clean()
                new_skill.save()
            return new_skill
        except ValidationError as e:
            if hasattr(e, 'message_dict'):
                messages = [f"{k}: {', '.join(v)}" for k, v in e.message_dict.items()]
                raise ServiceError(f"Datos inválidos: {'; '.join(messages)}")
            raise ServiceError(f"Datos inválidos: {', '.join(e.messages)}")
        except IntegrityError:
            raise ServiceError("Ya existe una habilidad con ese nombre.")
        except Exception as e:
            raise ServiceError(f"Error al crear la habilidad: {str(e)}")

    def update_skill(self, skill: Skill, skill_data: dict) -> Skill:
        if not self._is_full_access:
            raise PermissionsError('No tienes permisos suficientes para actualizar habilidades / competencias.')

        try:
            with transaction.atomic():
                for key, value in skill_data.items():
                    if key != 'id':
                        setattr(skill, key, value)
                skill.full_clean()
                skill.save()
            return skill
        except ValidationError as e:
            if hasattr(e, 'message_dict'):
                messages = [f"{k}: {', '.join(v)}" for k, v in e.message_dict.items()]
                raise ServiceError(f"Datos inválidos: {'; '.join(messages)}")
            raise ServiceError(f"Datos inválidos: {', '.join(e.messages)}")
        except IntegrityError:
            raise ServiceError("Ya existe una habilidad con ese nombre.")
        except Exception as e:
            raise ServiceError(f"Error al actualizar la habilidad: {str(e)}")











