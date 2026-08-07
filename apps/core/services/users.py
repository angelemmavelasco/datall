from django.contrib.auth import get_user_model
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional, ClassVar

from django.core.exceptions import ValidationError
from django.db.models import QuerySet, Count, Q
from django.db import transaction, IntegrityError
from collections import defaultdict
from apps.core.models import Reference

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
    class UserType(AbstractBaseUser, PermissionsMixin):
        pass

#exceptions
class ServiceError(Exception):
    pass

class UserNotFoundError(ServiceError):
    pass

class UserPermissionError(ServiceError):
    pass

class UserAuthenticationError(ServiceError):
    pass


@dataclass
class UsersService:
    '''
    Allows to get the info about the user and takes the business logic about permissions and auths
    '''
    user: 'UserType'
    user_model: type = field(default_factory=get_user_model)
    _is_full_access: bool = field(init=False)
    ACCESS_CONTEXTS: ClassVar[tuple[str, ...]] = ('acceso_total_usuarios',)

    def __post_init__(self):
        self._validate_access()
        self._is_full_access = self._evaluate_full_access()

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

    def _get_full_access_groups(self) -> list[str]:
        """
        Recovers a list with the names of the groups who have full acess to the users info.
        """
        return list(Reference.objects.filter(context__in=self.ACCESS_CONTEXTS).values_list('value', flat=True))

    def _evaluate_full_access(self) -> bool:
        """
        Evaluates if the user belongs to the full access groups, is superuser/staff or both.
        """
        if getattr(self.user, 'is_superuser', False) or getattr(self.user, 'is_staff', False):
            return True

        full_access_groups = self._get_full_access_groups()

        if not full_access_groups:
            return False

        return self.user.groups.filter(name__in=full_access_groups).exists()

    @property
    def has_full_access(self) -> bool:
        """
        Returns the cached full access evaluation to avoid redundant database queries.
        """
        return self._is_full_access

    def read_users(self) -> QuerySet:
        '''
        Returns a qs which the main user has access to, including the associated employees to them.
        '''
        if self._is_full_access:
            return self.user_model.objects.prefetch_related('groups', 'employees').all()
        else:
            return self.user_model.objects.prefetch_related('groups', 'employees').filter(pk=self.user.pk)

    def read_user(self, *, pk: int) -> Optional['UserType']:
        '''
        Return a single object depending on the user's permissions.
        only allowed users and groups can access to any pk user. Otherwise only return self.user.
        '''
        if self.user.pk == pk:
            return self.user

        target_user = self.read_users().filter(pk=pk).first()
        if target_user:
            return target_user

        user_exists = self.user_model.objects.filter(pk=pk).exists()
        if not user_exists:
            raise UserNotFoundError(f"El usuario con id {pk} no existe.")

        raise UserPermissionError(f"No tienes permiso para acceder al usuario con ID {pk}.")

    def create_user(self, **data) -> 'UserType':
        '''
        Create a new user based on provided data.
        Only allowed users (full access or superusers) can do it.
        '''
        if not self._is_full_access:
            raise UserPermissionError('No tienes permisos suficientes para crear usuarios.')

        password = data.pop('password', None)
        groups = data.pop('groups', [])

        if data.get('photo') is False:
            data['photo'] = None

        try:
            with transaction.atomic():
                new_user = self.user_model(**data)

                if password:
                    new_user.set_password(password)
                else:
                    new_user.set_unusable_password()

                new_user.full_clean()
                new_user.save()

                if groups:
                    new_user.groups.set(groups)

            return new_user

        except ValidationError as e:
            raise ServiceError(f"Datos inválidos: {', '.join(e.messages)}")
        except IntegrityError:
            raise ServiceError("Ya existe un usuario con esos datos únicos (ej. nombre de usuario o correo).")
        except Exception as e:
            raise ServiceError(f"Error al crear el usuario: {str(e)}")

    def update_user(self, *, pk: int, **new_data) -> 'UserType':
        '''
        update a user based on the provided data.

        - for users who are full access or superusers can update any user (except by the password and superuser status).
        - for regular users, they can view and modified all their info (except by roles, groups, and username)
        '''
        user_to_update = self.read_user(pk=pk)
        is_self = (self.user.pk == user_to_update.pk)
        if getattr(self.user, 'is_superuser', False):
            disallowed = {'id', 'pk', 'user_permissions'}
        elif self._is_full_access:
            disallowed = {'is_superuser', 'is_staff', 'id', 'pk'}
        else:
            disallowed = {
                'id', 'pk', 'is_superuser', 'is_staff',
                'is_active', 'groups', 'user_permissions', 'username',
                'last_login', 'date_joined'
            }

        if not is_self:
            disallowed.add('password')

        for key in disallowed:
            new_data.pop(key, None)

        groups = new_data.pop('groups', None)
        password = new_data.pop('password', None)

        if new_data.get('photo') is False:
            new_data['photo'] = None

        try:
            with transaction.atomic():
                for attr, value in new_data.items():
                    setattr(user_to_update, attr, value)

                if password:
                    user_to_update.set_password(password)

                user_to_update.full_clean()
                user_to_update.save()

                if groups is not None:
                    user_to_update.groups.set(groups)

            return user_to_update

        except ValidationError as e:
            raise ServiceError(f"Datos inválidos: {', '.join(e.messages)}")
        except IntegrityError:
            raise ServiceError("Ya existe un usuario con esos datos únicos.")
        except Exception as e:
            raise ServiceError(f"Error al actualizar: {str(e)}")

@dataclass
class UsersKPIsService:
    '''
    Dedicated to read generals stats and information about users.
    '''
    users_service: UsersService

    @property
    def _base_qs(self) -> QuerySet:
        '''
        Reuse class service base logic (UsersService) to bring allowed users and calculate over them
        '''
        return self.users_service.read_users()

    def stats(self, qs=None) -> dict:
        '''
        Returns dictionary with general users stats, all in a single call to database.

        returns
        -------
            dict: dictionary with general users stats, including: registered users, active users, inactive users and employeed users.
        '''
        base_qs = qs if qs is not None else self._base_qs
        return base_qs.aggregate(
            registered_users=Count('pk', distinct=True),
            active_users=Count('pk', filter=Q(is_active=True), distinct=True),
            inactive_users=Count('pk', filter=Q(is_active=False), distinct=True),
            employeed_users=Count('employees__user__pk', filter=(Q(employees__termination_date__isnull=True)&Q(is_active=True)), distinct=True),
        )

