from django.contrib.auth import get_user_model
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional
from django.db.models import QuerySet, Count, Q
from django.db import transaction
from collections import defaultdict

#exceptions
class ServiceError(Exception):
    pass

class UserNotFoundError(ServiceError):
    pass

class UserPermissionError(ServiceError):
    pass

class UserAuthenticationError(ServiceError):
    pass


if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser as UserModel
else:
    UserModel = object

@dataclass
class UsersService:
    '''
    The main service used to read, create, update and delete users.
    This service handles the business logic of the users module.
    '''
    user: 'UserModel'
    User: type['UserModel'] = get_user_model()
    _is_full_access: bool = field(init=False)

    def __post_init__(self) -> bool:
        self._validate_access()
        self._is_full_access = self._checkout_full_access

        
    def _validate_access(self) -> None:
        '''
        validates if the user was provided, exists and is authenticated.
        '''
        if not self.user:
            raise UserNotFoundError('No se ha proporcionado un usuario válido.')
        if not self.user.is_authenticated:
            raise UserAuthenticationError('El usuario proporcionado no está autenticado.')
        if not getattr(self.user, 'is_active', True):
            raise UserPermissionError('El usuario se encuentra inactivo.')

    @property
    def _checkout_full_access(self) -> bool:
        '''
        validates if user has total access (or is superuser) or limited access.
        '''
        if getattr(self.user, 'is_superuser', False):
            return True
        return self.user.groups.filter(name__in=['total', 'acceso total', 'admin', 'global', 'acceso global']).exists()

    def read_users(self) -> QuerySet:
        '''
        returns a qs which the main user has access to.
        '''
        if self._is_full_access:
            return self.User.objects.prefetch_related('groups', 'human_resources_employees').all()
        else:
            return self.User.objects.prefetch_related('groups', 'human_resources_employees').filter(pk=self.user.pk)
    
    def read_user(self, *, pk: int) -> Optional['UserModel']:
        '''
        return a single object depending on the user's permissions.
        only allowed users and groups can access to any pk user. Otherwise only return self.user.
        '''
        return self.read_users().filter(pk=pk).first()
    
    def create_user(self, **data) -> 'UserModel':
        '''
        create a new user based on provided data.
        '''
        if not self._is_full_access:
            raise UserPermissionError('El usuario no tiene permisos para crear usuarios.')
        password = data.pop('password', None)
        groups = data.pop('groups', [])
        if data.get('photo') is False:
            data['photo'] = None
        with transaction.atomic():
            new_user = self.User(**data)
            if password:
                new_user.set_password(password)
            else:
                new_user.set_unusable_password()
            new_user.save()
            if groups:
                new_user.groups.set(groups)
        return new_user
    
    def update_user(self, *, pk:int, **new_data) -> 'UserModel':
        '''
        update a user based on the provided data.

        - for users who are full access or superusers can update any user (except by the password and superuser status).
        - for regular users, they can view and modified all their info (except by roles, groups, and username)
        '''
        user_to_update = self.read_user(pk=pk)
        if user_to_update is None:
            raise UserNotFoundError(f'No se encontro el usuario con id {pk}.')

        if getattr(self.user, 'is_superuser', False):
            disallowed = ['password', 'id', 'pk', 'user_permissions']
        elif self._is_full_access:
            disallowed = ['is_superuser', 'is_staff', 'password', 'id', 'pk']
        else:
            disallowed = [
                'id', 'pk', 'password', 'is_superuser', 'is_staff', 
                'is_active', 'groups', 'user_permissions', 'username', 
                'last_login', 'date_joined'
            ]

        for key in disallowed: #remove disallowed fields to prevent errors
            new_data.pop(key, None)
        groups = new_data.pop('groups', None)

        if new_data.get('photo') is False:
            new_data['photo'] = None

        with transaction.atomic():
            for attr, value in new_data.items(): #update simple attrs
                setattr(user_to_update, attr, value)
            user_to_update.save()
            if groups is not None: #update groups if were allowed
                user_to_update.groups.set(groups)
        return user_to_update

@dataclass
class UsersKPIsService:
    '''
    dedicated to read generals stats and information about users.
    '''
    users_service: UsersService

    @property
    def _base_qs(self) -> QuerySet:
        '''
        reuse class service base logic (UsersService) to bring allowed users and calculate over them
        '''
        return self.users_service.read_users()

    def stats(self, qs=None) -> dict:
        '''
        returns dictionary with general users stats, all in a single call to database.

        returns
        -------
            dict: dictionary with general users stats, including: registered users, active users, inactive users and employeed users.
        '''
        base_qs = qs if qs is not None else self._base_qs
        return base_qs.aggregate(
            registered_users=Count('pk', distinct=True),
            active_users=Count('pk', filter=Q(is_active=True), distinct=True),
            inactive_users=Count('pk', filter=Q(is_active=False), distinct=True),
            employeed_users=Count('human_resources_employees__user__pk', filter=(Q(human_resources_employees__termination_date__isnull=True)&Q(is_active=True)), distinct=True),
        )

        




