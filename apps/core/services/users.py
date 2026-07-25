from django.contrib.auth import get_user_model
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from django.db.models import QuerySet



if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser as UserModel
else:
    UserModel = object

User = get_user_model()

@dataclass
class UsersService:
    '''
    The main service used to read, create, update and delete users.
    This service handles the business logic of the users module.
    '''
    user: 'UserModel'
    _is_full_access: bool = field(init=False)

    def __post_init__(self) -> bool:
        self._is_full_access = self._checkout_full_access

    @property
    def _checkout_full_access(self) -> bool:
        '''
        validates if user has total access (or is superuser) or limited access.
        '''
        return None 
        