from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar
from apps.core.models import ActivityLog
from apps.core.services.users import UsersService
from django.db.models import QuerySet
from django.utils import timezone

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
    class UserType(AbstractBaseUser, PermissionsMixin):
        pass

# exceptions
class ServiceError(Exception):
    pass

class LogNotFound(ServiceError):
    pass
    

@dataclass
class ActivityLogsService(UsersService):
    user: 'UserType'
    activity_model: type = ActivityLog
    _is_full_access: bool =  field(init=False)
    ACCESS_CONTEXTS: ClassVar[tuple[str, ...]] = (
            'acceso_total_actividad',
            'acceso_total',
        )

    def __post_init__(self):
        self._is_full_access = self._evaluate_full_access()

    def get(self) -> QuerySet:
        today = timezone.now().date()
        
        if self._is_full_access:
            return self.activity_model.objects.all()[:100]

        return self.activity_model.objects.filter(user=self.user)[:100]
        

