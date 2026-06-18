import logging
from datetime import datetime, date, time
from django.utils import timezone
from django.db.models import Q
from apps.core.models import DataHistory, SystemModule

logger = logging.getLogger(__name__)
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
            if isinstance(start_date, str):
                try:
                    start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
                except ValueError:
                    pass
            if isinstance(start_date, date) and not isinstance(start_date, datetime):
                start_date = timezone.make_aware(datetime.combine(start_date, time.min))
            if isinstance(start_date, datetime):
                queryset = queryset.filter(created_at__gte=start_date)

        if end_date:
            if isinstance(end_date, str):
                try:
                    end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
                except ValueError:
                    pass
            if isinstance(end_date, date) and not isinstance(end_date, datetime):
                end_date = timezone.make_aware(datetime.combine(end_date, time.max))
            if isinstance(end_date, datetime):
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

    def log_action(
        self,
        request,
        action: str,
        result: str = DataHistory.Result.SUCCESS,
        content_type=None,
        object_id: str = None,
        description: str = None,
        changes: dict = None
    ):
        """
        Helper method to log an action automatically mapping the current SystemModule 
        based on the request's view_name.
        """
        if not request or not hasattr(request, 'user') or not request.user.is_authenticated:
            return None

        # Resolve the current module from url_name
        view_name = request.resolver_match.view_name if request.resolver_match else None
        module = None
        if view_name:
            module = SystemModule.objects.filter(url_name=view_name).first()

        try:
            return self.model.objects.create(
                module=module,
                action=action,
                result=result,
                content_type=content_type,
                object_id=object_id,
                created_by=request.user,
                description=description,
                changes=changes
            )
        except Exception as e:
            logger.error(f"Error logging data history action: {e}")
            return None
