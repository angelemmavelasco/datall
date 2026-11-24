from dataclasses import dataclass, field
from collections import defaultdict
from typing import TYPE_CHECKING, ClassVar
from apps.core.models import ActivityLog
from apps.core.services.users import UsersService
from django.db.models import QuerySet, Avg, Count, Sum
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
    HEATMAP_HOURS: ClassVar[tuple[str, ...]] = tuple(f'{h:02d}:00' for h in range(24))

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
            if day_key not in heatmap:
                heatmap[day_key] = dict.fromkeys(self.HEATMAP_HOURS, 0)
            heatmap[day_key][hour_key] = requests_count

        return heatmap

    def heatmap_hours(self, *, qs: QuerySet) -> dict:
        tz = timezone.get_current_timezone()
        occurrences = (
            qs.prefetch_related(None)
            .order_by()
            .annotate(hour_bucket=TruncHour('created_at', tzinfo=tz))
            .values('hour_bucket')
            .annotate(
                requests_count=Count('id'),
                unique_users=Count('user', distinct=True),
            )
            .values_list('hour_bucket', 'requests_count', 'unique_users')
            .order_by('hour_bucket')
        )

        totals_by_hour = {
            hour: {'requests_count': 0, 'users_sum': 0, 'active_days': 0}
            for hour in self.HEATMAP_HOURS
        }
        for hour_bucket, requests_count, unique_users in occurrences:
            if hour_bucket is None or requests_count <= 0:
                continue
            local_dt = timezone.localtime(hour_bucket, tz) if timezone.is_aware(hour_bucket) else hour_bucket
            hour_key = local_dt.strftime('%H:00')
            bucket = totals_by_hour[hour_key]
            bucket['requests_count'] += requests_count
            bucket['users_sum'] += unique_users
            bucket['active_days'] += 1

        hourly_data = {}
        for hour_key, metrics in totals_by_hour.items():
            active_days = metrics['active_days']
            avg_users = round(metrics['users_sum'] / active_days, 2) if active_days > 0 else 0.0
            hourly_data[hour_key] = {
                'requests_count': metrics['requests_count'],
                'avg_users': avg_users,
                'active_days': active_days,
            }

        return hourly_data

    
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

    def most_visited_views(self, *, qs: QuerySet) -> dict:
        rows = (
            qs.prefetch_related(None)
            .order_by()
            .values(
                'view_name',
                'http_method',
                'user_id',
                'user__username',
                'user__first_name',
                'user__last_name',
            )
            .annotate(
                requests=Count('id'),
                duration_sum=Sum('duration_ms'),
                duration_count=Count('duration_ms'),
            )
            .values_list(
                'view_name',
                'http_method',
                'user_id',
                'user__username',
                'user__first_name',
                'user__last_name',
                'requests',
                'duration_sum',
                'duration_count',
            )
        )

        grouped = {}
        for (
            view_name,
            http_method,
            user_id,
            username,
            first_name,
            last_name,
            requests_count,
            duration_sum,
            duration_count,
        ) in rows:
            method_key = (http_method or 'GET').upper()
            view_label = view_name or '(Sin vista)'
            key = f'{method_key} {view_label}'

            if key not in grouped:
                grouped[key] = {
                    'view_name': view_name or '',
                    'http_method': method_key,
                    'requests': 0,
                    'unique_users': 0,
                    'avg_duration_ms': 0.0,
                    'users': [],
                    '_duration_sum': 0,
                    '_duration_count': 0,
                }

            dur_sum = duration_sum or 0
            dur_cnt = duration_count or 0
            user_avg_ms = round(dur_sum / dur_cnt, 2) if dur_cnt > 0 else 0.0

            if user_id is None:
                display_username = 'Anónimo'
                full_name = 'Anónimo'
            else:
                display_username = username or ''
                full_name = f'{first_name or ""} {last_name or ""}'.strip() or display_username
                grouped[key]['unique_users'] += 1

            grouped[key]['requests'] += requests_count
            grouped[key]['_duration_sum'] += dur_sum
            grouped[key]['_duration_count'] += dur_cnt
            grouped[key]['users'].append({
                'user_id': user_id,
                'username': display_username,
                'full_name': full_name,
                'requests': requests_count,
                'avg_duration_ms': user_avg_ms,
            })

        for entry in grouped.values():
            dur_cnt = entry.pop('_duration_count')
            dur_sum = entry.pop('_duration_sum')
            entry['avg_duration_ms'] = round(dur_sum / dur_cnt, 2) if dur_cnt > 0 else 0.0
            entry['users'].sort(
                key=lambda u: (u['requests'], u['avg_duration_ms']),
                reverse=True,
            )

        sorted_items = sorted(
            grouped.items(),
            key=lambda item: (
                item[1]['requests'],
                item[1]['unique_users'],
                item[1]['avg_duration_ms'],
            ),
            reverse=True,
        )

        return dict(sorted_items)

