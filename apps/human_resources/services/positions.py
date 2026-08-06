from dataclasses import dataclass
from typing import ClassVar, Optional

from apps.human_resources.models import Position
from apps.core.services.users import UsersService
from apps.human_resources.services.employees import EmployeesService
from django.db.models import QuerySet


class ServiceError(Exception):
    pass

class PositionNotFound(ServiceError):
    pass

class PermissionsError(ServiceError):
    pass

@dataclass
class PositionsService(UsersService):
    position_model: type = Position
    ACCESS_CONTEXTS: ClassVar[tuple[str, ...]] = (
        'acceso_total_usuarios',
        'acceso_total_posiciones',
        'recursos_humanos',
    )

    def read_positions(self) -> QuerySet:
        if self._is_full_access:
            base_qs = self.position_model.objects.all()
        else:
            employees_service = EmployeesService(user=self.user)
            accessible_employees = employees_service.read_employees()

            base_qs = self.position_model.objects.filter(
                employees__in=accessible_employees
            ).distinct()

        return base_qs

    def read_position(self, *, pk: str) -> Optional[Position]:
        position = self.read_positions().filter(pk=pk).first()
        if position:
            return position

        if self.position_model.objects.filter(pk=pk).exists():
            raise PermissionsError(f'No tienes permiso para acceder a la posición con ID "{pk}".')

        raise PositionNotFound(f'No se encontró ninguna posición con el ID "{pk}".')
