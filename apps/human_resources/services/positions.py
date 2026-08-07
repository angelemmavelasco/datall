from dataclasses import dataclass
from typing import ClassVar, Optional
from django.utils import timezone

from apps.human_resources.models import Position, PositionSkill
from apps.core.services.users import UsersService
from apps.human_resources.services.employees import EmployeesService
from django.db.models import QuerySet, Count, Q, When, Value, Case, Sum


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











