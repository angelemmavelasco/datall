from django.conf import settings
from typing import List

from django.contrib.auth import get_user_model
from django.db.models import Q

class UsersCRUD:

    def __init__(self):
        self.model = get_user_model()



    def get_users(
            self, *,
            groups: List[int] = None,
            is_active: bool = None,
            gender: List[str] =None,
            city:str=None,
            state:str=None,
            search_query:str=None, **kwargs
    ):
        """
        Retrieves users based on multiple flexible filtering criteria.

        :param groups: List of Group IDs
        :param is_active: Boolean status
        :param gender: String ('f', 'm', 'nb', 'o')
        :param city: String for partial match lookup
        :param state: String for partial match lookup
        :param search_query: Global string to search across names, username, email, and phone
        :param kwargs: Fallback for any other exact match filters (e.g., tax_id, country)
        :return: QuerySet of Users
        """

        queryset = self.model.objects.prefetch_related('groups').all()

        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)

        if groups is not None:
            queryset = queryset.filter(groups__in=groups)

        if gender is not None:
            queryset = queryset.filter(gender__in=gender)

        if city:
            queryset = queryset.filter(city__icontains=city)

        if state:
            queryset = queryset.filter(state__icontains=state)

        if search_query:
            search_query = search_query.strip()
            queryset = queryset.filter(
                Q(username__icontains=search_query) |
                Q(first_name__icontains=search_query) |
                Q(last_name__icontains=search_query) |
                Q(second_last_name__icontains=search_query) |
                Q(email__icontains=search_query) |
                Q(phone__icontains=search_query)
            )


        #for extra dynamic filter if given
        if kwargs:
            queryset = queryset.filter(**kwargs)

        return queryset.distinct()

    def get_user(self, *, user_id: int = None):
        """
        Retrieves a single user instance by their primary key (ID),
        pre-fetching their associated role to optimize performance.

        :param user_id: The integer primary key of the user.
        :return: The User instance if found, or None if the ID does not exist or is not provided.
        """

        if user_id is None:
             return None

        return self.model.objects.prefetch_related('groups').filter(id=user_id).first()

    def process_user_update(self, user_id: int, raw_data: dict, selected_groups: list = None, files_data: dict = None):
        """
        Process the raw data from a dict and update the user's attributes.

        :param user_id:
        :param raw_data:
        :return bool:
        """
        if not user_id or not raw_data:
            return False

        #remove csrf token
        raw_data.pop('csrfmiddlewaretoken', None)

        #username is required
        username = raw_data.get('username')
        if not username or str(username).strip() == "":
            return False

        cleaned_data = {}
        fields_to_null = ['birth_date']

        for key, value in raw_data.items():
            if key in ('groups', 'roles', 'role_id'):
                continue
            
            if value == "":
                if key in fields_to_null:
                    cleaned_data[key] = None
                else:
                    cleaned_data[key] = ""
            elif key == 'is_active':
                cleaned_data[key] = (value == 'True')
            else:
                cleaned_data[key] = value

        if files_data and 'photo' in files_data:
            cleaned_data['photo'] = files_data['photo']

        return self.update_user(user_id=user_id, selected_groups=selected_groups, **cleaned_data)

    def update_user(
            self, *,
            user_id: int = None,
            selected_groups: list = None,
            **kwargs
    ):
        """
        Updates an existing user's attributes dynamically.

        :param user_id: The integer primary key of the user to update.
        :param kwargs: Keyword arguments representing the fields and their new values.
        :return: The updated User instance, or None if the user was not found or user_id is missing.
        """

        if user_id is None or not kwargs:
            return None

        user = self.model.objects.filter(id=user_id).first()
        if not user:
            return None

        for key, value in kwargs.items():
            if hasattr(user, key):
                setattr(user, key, value)

        user.save()

        if selected_groups is not None:
            user.groups.set(selected_groups)

        return user


    def delete_user(self, *, user_id: int = None):
        """
        Deactivates a user by setting is_active to False (Soft Delete).
        Preserves database integrity and historical data for audits.

        :param user_id: The integer primary key of the user to deactivate.
        :return: The deactivated User instance, or None if not found.
        """

        if user_id is None:
            return None

        user = self.model.objects.filter(id=user_id).first()
        if not user:
            return None

        user.is_active = False
        user.save()

        return user

    def process_user_create(self, raw_data: dict, selected_groups: list = None):
        """
        Process the raw data from a dict and create a new user.
        Returns the created user or False if validation fails.

        :param raw_data: The dictionary containing user data to process.
        """
        if not raw_data:
            return False

        raw_data.pop('csrfmiddlewaretoken', None)

        username = raw_data.get('username')
        password = raw_data.pop('password', None)  # Extract password

        if not username or str(username).strip() == "" or not password:
            return False

        #prevent crash if username already exists
        if self.model.objects.filter(username=username).exists():
            return False

        cleaned_data = {}
        fields_to_null = ['birth_date']

        for key, value in raw_data.items():
            if key in ('groups', 'roles', 'role_id'):
                continue

            if value == "":
                if key in fields_to_null:
                    cleaned_data[key] = None
                else:
                    cleaned_data[key] = ""
            elif key == 'is_active':
                cleaned_data[key] = (value == 'True')
            else:
                cleaned_data[key] = value

        #create user
        new_user = self.model(**cleaned_data)

        #encrypt password using Django's native function
        new_user.set_password(password)

        #save user
        new_user.save()

        if selected_groups is not None:
            new_user.groups.set(selected_groups)

        return new_user
