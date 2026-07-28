from django.contrib.auth import get_user_model
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional
from django.db.models import QuerySet, Count, Q
from django.db.models.functions import Lower
from django.db import transaction
from django.utils import timezone

from apps.human_resources.models import Position, Skill, PositionSkill

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
class PositionsService:
    '''
    The main service used to read, create, update positions and skills.
    This service handles the business logic of the positions module.
    '''
    user: 'UserModel'
    PositionModel: type[Position] = Position
    SkillModel: type[Skill] = Skill
    _is_full_access: bool = field(init=False)

    def __post_init__(self) -> bool:
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

    def read_positions(self) -> QuerySet:
        '''
        returns a qs which the main user has access to.
        regular users can view only positions which they are associated to, while full access users can view all.
        '''
        today = timezone.now().date()
        base_qs = self.PositionModel.objects.annotate(
            active_employees_count=Count(
                'human_resources_employees',
                distinct=True,
                filter=(
                    Q(human_resources_employees__termination_date__isnull=True) |
                    Q(human_resources_employees__termination_date__gt=today)
                )
            ),
            inactive_employees_count=Count(
                'human_resources_employees',
                distinct=True,
                filter=(
                    Q(human_resources_employees__termination_date__isnull=False) &
                    Q(human_resources_employees__termination_date__lte=today)
                )
            ),
        ).select_related('department').prefetch_related(
            'human_resources_position_skills__skill', 
            'human_resources_employees'
        ).order_by('hierarchy_level', Lower('department__name'), Lower('name'))
        
        if self._is_full_access:
            return base_qs.all()
        return base_qs.filter(human_resources_employees__user=self.user).distinct()

    
    def read_position(self, *, pk: str) -> Optional[Position]:
        '''
        return a single object.
        '''
        return self.read_positions().filter(pk=pk).first()
    
    def create_position(self, position_data: dict, skills_data: list) -> Position:
        '''
        create a new position based on provided data, handling form and formset data.
        '''
        if not self._is_full_access:
            raise PositionPermissionError('El usuario no tiene permisos para crear puestos.')
        
        with transaction.atomic():
            new_position = self.PositionModel.objects.create(**position_data)
            
            for skill_data in skills_data:
                # inlineformset adds empty dicts for empty extra forms
                if not skill_data:
                    continue
                    
                if not skill_data.get('DELETE', False):
                    skill = skill_data.get('skill')
                    if skill:
                        PositionSkill.objects.create(
                            position=new_position,
                            skill=skill,
                            requirement_level=skill_data.get('requirement_level', 'required'),
                            skill_level=skill_data.get('skill_level', 'basic'),
                            notes=skill_data.get('notes', '')
                        )
            
        return new_position
    
    def update_position(self, *, pk: str, position_data: dict, skills_data: list) -> Position:
        '''
        update a position based on the provided data.
        '''
        position_to_update = self.read_position(pk=pk)
        if position_to_update is None:
            raise PositionNotFoundError(f'No se encontró el puesto con id {pk}.')

        if not self._is_full_access:
            raise PositionPermissionError('El usuario no tiene permisos para actualizar puestos.')

        position_data.pop('id', None)

        with transaction.atomic():
            for attr, value in position_data.items():
                setattr(position_to_update, attr, value)
            position_to_update.save()
            
            for skill_data in skills_data:
                if not skill_data:
                    continue
                    
                skill_instance = skill_data.get('id')
                if skill_data.get('DELETE', False):
                    if skill_instance:
                        skill_instance.delete()
                else:
                    skill = skill_data.get('skill')
                    if skill:
                        if skill_instance:
                            skill_instance.skill = skill
                            skill_instance.requirement_level = skill_data.get('requirement_level', 'required')
                            skill_instance.skill_level = skill_data.get('skill_level', 'basic')
                            skill_instance.notes = skill_data.get('notes', '')
                            skill_instance.save()
                        else:
                            PositionSkill.objects.create(
                                position=position_to_update,
                                skill=skill,
                                requirement_level=skill_data.get('requirement_level', 'required'),
                                skill_level=skill_data.get('skill_level', 'basic'),
                                notes=skill_data.get('notes', '')
                            )
            
        return position_to_update

    def create_skill(self, **data) -> Skill:
        '''
        create a new skill
        '''
        if not self._is_full_access:
            raise PositionPermissionError('El usuario no tiene permisos para crear habilidades.')
        
        with transaction.atomic():
            new_skill = self.SkillModel(**data)
            new_skill.save()
            
        return new_skill

    def read_skills(self) -> QuerySet:
        '''
        returns a qs of skills.
        regular users can view only skills related to the positions they are associated with, while full access users can view all.
        '''
        today = timezone.now().date()
        base_qs = self.SkillModel.objects.annotate(
            assigned_positions_count=Count('position_requirements__position', distinct=True),
            active_employees_count=Count(
                'position_requirements__position__human_resources_employees',
                distinct=True,
                filter=(
                    Q(position_requirements__position__human_resources_employees__termination_date__isnull=True) |
                    Q(position_requirements__position__human_resources_employees__termination_date__gt=today)
                )
            ),
            inactive_employees_count=Count(
                'position_requirements__position__human_resources_employees',
                distinct=True,
                filter=(
                    Q(position_requirements__position__human_resources_employees__termination_date__isnull=False) &
                    Q(position_requirements__position__human_resources_employees__termination_date__lte=today)
                )
            )
        )
        
        if self._is_full_access:
            return base_qs.order_by('name')
            
        return base_qs.filter(
            position_requirements__position__human_resources_employees__user=self.user
        ).distinct().order_by('name')

    def read_skill(self, *, pk: str) -> Optional[Skill]:
        '''
        return a single skill.
        '''
        return self.read_skills().filter(pk=pk).first()

    def update_skill(self, *, pk: str, data: dict) -> Skill:
        '''
        update a skill based on the provided data.
        '''
        if not self._is_full_access:
            raise PositionPermissionError('El usuario no tiene permisos para actualizar habilidades.')

        skill_to_update = self.read_skills().filter(pk=pk).first()
        if skill_to_update is None:
            raise PositionNotFoundError(f'No se encontró la habilidad con id {pk}.')

        data.pop('id', None)

        with transaction.atomic():
            for attr, value in data.items():
                setattr(skill_to_update, attr, value)
            skill_to_update.save()
            
        return skill_to_update

    def delete_skill(self, *, pk: str) -> None:
        '''
        delete a skill.
        '''
        if not self._is_full_access:
            raise PositionPermissionError('El usuario no tiene permisos para eliminar habilidades.')

        skill_to_delete = self.read_skills().filter(pk=pk).first()
        if skill_to_delete is None:
            raise PositionNotFoundError(f'No se encontró la habilidad con id {pk}.')

        with transaction.atomic():
            skill_to_delete.delete()


@dataclass
class PositionsKPIsService:
    '''
    dedicated to read generals stats and information about positions.
    '''
    positions_service: PositionsService

    @property
    def _base_qs(self) -> QuerySet:
        '''
        reuse class service base logic to bring allowed positions and calculate over them
        '''
        return self.positions_service.read_positions()

    @property
    def stats(self) -> dict:
        '''
        returns dictionary with general positions stats, including: registered positions, registered skills, and active/inactive employees.
        '''
        today = timezone.now().date()
        return self._base_qs.aggregate(
            registered_positions=Count('pk', distinct=True),
            registered_skills=Count('human_resources_position_skills__skill', distinct=True),
            active_collaborators=Count(
                'human_resources_employees',
                distinct=True,
                filter=(
                    Q(human_resources_employees__termination_date__isnull=True)|
                    Q(human_resources_employees__termination_date__gt=today)
                )
            ),
            inactive_collaborators=Count(
                'human_resources_employees',
                distinct=True,
                filter=(
                    Q(
                        human_resources_employees__termination_date__isnull=False
                    )&
                    Q(
                        human_resources_employees__termination_date__lte=today
                    )
                ),
            )
        )
