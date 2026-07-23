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

    def __post_init__(self):
        self._is_full_access = self._checkout_full_access()

    def _checkout_full_access(self) -> bool:
        '''
        validates if user has total access (or is superuser) or limited access.
        '''
        if not self.user or not self.user.is_authenticated:
            return False
        if getattr(self.user, 'is_superuser', False):
            return True
        return self.user.groups.filter(name='total').exists()

    def read_users(self) -> QuerySet:
        """
        returns a queryset which the main user has access to
        """
        if not self.user or not self.user.is_authenticated:
            return User.objects.none()

        if self._is_full_access:
            return User.objects.all()

        return User.objects.filter(pk=self.user.pk)

    def read_user(self, user_id: int):
        """
        returns a user if the main user has access to it
        """
        return self.read_users().filter(pk=user_id).first()

    def create_user(self, **kwargs):
        """
        creates a user if the main user has total access
        """
        if not self.user or not self.user.is_authenticated:
            return None
        if not self._is_full_access:
            return None
        password = kwargs.pop('password', None)
        new_user = User(**kwargs)
        if password:
            new_user.set_password(password)
        new_user.save()
        return new_user
    
    def delete_user(self, user_id: int):
        """
        deletes a user if the main user has total access (its soft deleted)
        """
        if not self.user or not self.user.is_authenticated:
            return False
        if not self._is_full_access:
            return False
        user = self.read_user(user_id)
        if user:
            user.is_active = False
            user.save()
            return True
        return False

    
        
        

    