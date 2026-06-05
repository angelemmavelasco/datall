from django.contrib.auth.models import Group
from django.contrib.auth import get_user_model
from django.db.models import Q
from apps.core.models import SystemModule

User = get_user_model()

class GroupsCRUD:

    def __init__(self):
        self.model = Group
        self.module_model = SystemModule
        self.user_model = User

    def get_groups(self, *, search_query: str = None):
        """
        Retrieves groups based on filtering criteria.
        """
        queryset = self.model.objects.all().prefetch_related('accessible_modules')

        if search_query:
            search_query = search_query.strip()
            queryset = queryset.filter(
                Q(name__icontains=search_query)
            )

        return queryset.distinct()

    def get_group(self, *, group_id: int = None):
        """
        Retrieves a single group instance by ID.
        """
        if group_id is None:
            return None

        return self.model.objects.filter(id=group_id).prefetch_related('accessible_modules').first()

    def get_users_in_group(self, *, group_id: int = None):
        """
        Retrieves users that belong to a specific group.
        """
        if group_id is None:
            return self.user_model.objects.none()

        return self.user_model.objects.filter(groups__id=group_id)

    def process_group_create(self, raw_data: dict, selected_modules: list = None):
        """
        Process the raw data to create a new group and assign modules.
        """
        if not raw_data:
            return False

        name = raw_data.get('name')
        if not name or str(name).strip() == "":
            return False

        name = name.strip()

        if self.model.objects.filter(name__iexact=name).exists():
            return False

        new_group = self.model.objects.create(name=name)

        if selected_modules:
            # selected_modules should be a list of SystemModule IDs
            modules = self.module_model.objects.filter(id__in=selected_modules)
            for module in modules:
                module.allowed_groups.add(new_group)

        return new_group

    def process_group_update(self, group_id: int, raw_data: dict, selected_modules: list = None):
        """
        Process raw data to update a group and its modules.
        """
        if not group_id or not raw_data:
            return False

        name = raw_data.get('name')
        if not name or str(name).strip() == "":
            return False

        name = name.strip()

        group = self.model.objects.filter(id=group_id).first()
        if not group:
            return False

        # check if new name exists in another group
        if self.model.objects.filter(name__iexact=name).exclude(id=group_id).exists():
            return False

        group.name = name
        group.save()

        # Update accessible modules
        # First, remove this group from all modules
        current_modules = self.module_model.objects.filter(allowed_groups=group)
        for mod in current_modules:
            mod.allowed_groups.remove(group)

        # Then, add it to the newly selected ones
        if selected_modules:
            modules = self.module_model.objects.filter(id__in=selected_modules)
            for module in modules:
                module.allowed_groups.add(group)

        return group

    def delete_group(self, *, group_id: int = None):
        """
        Deletes a group.
        """
        if group_id is None:
            return None

        group = self.model.objects.filter(id=group_id).first()
        if not group:
            return None

        group.delete()
        return True
