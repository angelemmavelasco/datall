from django.db.models import Q
from apps.core.models import DataHistory

class DataHistoryCrud:

    def __init__(self):
        self.model = DataHistory

    def get_histories(
            self, *,
            modules: list = None,
            actions: list = None,
            results: list = None,
            users: list = None,
            start_date: str = None,
            end_date: str = None,
            search_query: str = None,
            **kwargs
    ):
        """
        Retrieves data history logs based on filtering criteria.
        """
        queryset = self.model.objects.select_related('module', 'created_by', 'content_type').all()

        if modules is not None:
            queryset = queryset.filter(module__id__in=modules)

        if actions is not None:
            queryset = queryset.filter(action__in=actions)

        if results is not None:
            queryset = queryset.filter(result__in=results)

        if users is not None:
            queryset = queryset.filter(created_by__id__in=users)

        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)

        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)

        if search_query:
            search_query = search_query.strip()
            queryset = queryset.filter(
                Q(description__icontains=search_query) |
                Q(object_id__icontains=search_query) |
                Q(action__icontains=search_query) |
                Q(result__icontains=search_query)
            )

        if kwargs:
            queryset = queryset.filter(**kwargs)

        return queryset.order_by('-created_at').distinct()

    def get_history(self, *, history_id: int = None):
        """
        Retrieves a single data history instance by ID.
        """
        if history_id is None:
            return None

        return self.model.objects.filter(id=history_id).select_related('module', 'created_by', 'content_type').first()

    def process_history_create(self, raw_data: dict):
        """
        Process the raw data to create a new data history log.
        """
        if not raw_data:
            return False

        # basic required fields
        action = raw_data.get('action')
        if not action or str(action).strip() == "":
            return False

        # Pop unnecessary fields if any
        raw_data.pop('csrfmiddlewaretoken', None)

        cleaned_data = {}
        for key, value in raw_data.items():
            if value == "":
                cleaned_data[key] = None
            else:
                cleaned_data[key] = value

        new_history = self.model.objects.create(**cleaned_data)
        return new_history

    def process_history_update(self, history_id: int, raw_data: dict):
        """
        Process raw data to update a data history log.
        """
        if not history_id or not raw_data:
            return False

        history = self.model.objects.filter(id=history_id).first()
        if not history:
            return False

        raw_data.pop('csrfmiddlewaretoken', None)

        for key, value in raw_data.items():
            if hasattr(history, key) and key not in ['id', 'created_at']:
                val = None if value == "" else value
                setattr(history, key, val)

        history.save()
        return history

    def delete_history(self, *, history_id: int = None):
        """
        Deletes a data history log.
        """
        if history_id is None:
            return None

        history = self.model.objects.filter(id=history_id).first()
        if not history:
            return None

        history.delete()
        return True
