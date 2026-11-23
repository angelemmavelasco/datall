from dataclasses import dataclass, field
from collections import defaultdict
from typing import TYPE_CHECKING, ClassVar
from apps.core.models import ActivityLog
from apps.core.services.users import UsersService
from django.db.models import QuerySet, Avg, Count
from django.db.models.functions import TruncHour
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
        qs = self.activity_model.objects.select_related(
            'user',
            'submodule__module',
            'content_type',
        ).prefetch_related(
            'content_object',
        ).order_by('-created_at', '-id')

        if not self._is_full_access:
            qs = qs.filter(user=self.user)

        return qs


    def heatmap_calendar(self, *, qs: QuerySet) -> dict:
        tz = timezone.get_current_timezone()
        occurrences = (
            qs.prefetch_related(None)
            .order_by()
            .annotate(hour_bucket=TruncHour('created_at', tzinfo=tz))
            .values('hour_bucket')
            .annotate(requests_count=Count('id'))
            .values_list('hour_bucket', 'requests_count')
            .order_by('hour_bucket')
        )

        heatmap = {}
        for hour_bucket, requests_count in occurrences:
            if hour_bucket is None:
                continue
            local_dt = timezone.localtime(hour_bucket, tz) if timezone.is_aware(hour_bucket) else hour_bucket
            day_key = local_dt.strftime('%Y-%m-%d')
            hour_key = local_dt.strftime('%H:00')
            heatmap.setdefault(day_key, {})[hour_key] = requests_count

        return heatmap

    
    def stats(self, *, qs: QuerySet) -> dict:
        stats = defaultdict(float)

        stats = qs.aggregate(
            avg_performance_ms=Avg('duration_ms'),
            requests_count=Count('id'),
            unique_views=Count('view_name', distinct=True),
            unique_users=Count('user', distinct=True)

        )

        stats['top_5_views'] = None

        return stats

