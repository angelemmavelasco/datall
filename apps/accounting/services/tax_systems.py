from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from django.db.models import QuerySet
from django.contrib.auth import get_user_model
from apps.accounting.models import TaxSystem

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser as UserModel
else:
    UserModel = object

User = get_user_model()

@dataclass
class TaxSystemsService:
    """
    Service used to read, create, update and delete tax systems.
    Handles business logic and permission checking at the group/user level.
    """
    user: 'UserModel'
    _can_add: bool = field(init=False)
    _can_change: bool = field(init=False)
    _can_delete: bool = field(init=False)

    def __post_init__(self):
        if self.user and self.user.is_authenticated:
            self._can_add = self.user.has_perm('accounting.add_taxsystem')
            self._can_change = self.user.has_perm('accounting.change_taxsystem')
            self._can_delete = self.user.has_perm('accounting.delete_taxsystem')
        else:
            self._can_add = False
            self._can_change = False
            self._can_delete = False

    def read_tax_systems(self) -> QuerySet:
        """
        returns all tax systems. All user with no exception can view them
        """
        if not self.user or not self.user.is_authenticated:
            return TaxSystem.objects.none()
        
        return TaxSystem.objects.all()

    def read_tax_system(self, tax_system_id: str):
        """
        returns a tax system by id
        """
        return self.read_tax_systems().filter(pk=tax_system_id).first()

    def create_tax_system(self, **kwargs):
        """
        creates a tax system only if the user has the permission
        """
        if not self._can_add:
            return None
        new_tax_system = TaxSystem(**kwargs)
        new_tax_system.save()
        return new_tax_system
    
    def update_tax_system(self, tax_system_id: str, **kwargs):
        """
        updates a tax system only if the user has the permission
        """
        if not self._can_change:
            return None
        tax_system_to_update = self.read_tax_system(tax_system_id)
        if not tax_system_to_update:
            return None
            
        for key, value in kwargs.items():
            setattr(tax_system_to_update, key, value)
            
        tax_system_to_update.save()
        return tax_system_to_update
    
    def delete_tax_system(self, tax_system_id: str):
        """
        deletes a tax system only if the user has the permission
        """
        if not self._can_delete:
            return False
        tax_system = self.read_tax_system(tax_system_id)
        if tax_system:
            tax_system.delete()
            return True
        return False
