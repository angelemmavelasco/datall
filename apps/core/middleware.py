import time
import logging
from django.conf import settings
from apps.core.models import ActivityLog, Submodule

logger = logging.getLogger(__name__)


class ActivityTrackingMiddleware:
    """
    middleware which gets user activity, which includes:
    - view and urls visited (view_name, path, http method).
    - system submodule associated.
    - filters and get parameters applied (without sensitive data).
    - technical metrics (response code, response time in ms, ip, user agent).
    - inferred action type (VIEW, FILTER, EXPORT, IMPORT, CREATE, UPDATE, DELETE, LOGIN, LOGOUT).
    """

    EXCLUDED_PREFIXES = (
        '/static/',
        '/media/',
        '/favicon.ico',
        '/__debug__/',
        '/admin/jsi18n/',
    )

    SENSITIVE_PARAMS = {
        'password',
        'csrfmiddlewaretoken',
        'token',
        'secret',
        'auth',
        'session_key',
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        for prefix in self.EXCLUDED_PREFIXES:
            if path.startswith(prefix):
                return self.get_response(request)

        start_time = time.perf_counter()
        response = self.get_response(request)
        duration_ms = int((time.perf_counter() - start_time) * 1000)

        if hasattr(request, 'user') and request.user.is_authenticated:
            self._log_activity(request, response, duration_ms)

        return response

    def _log_activity(self, request, response, duration_ms: int):
        try:
            resolver_match = getattr(request, 'resolver_match', None)
            view_name = resolver_match.view_name if resolver_match else ''
            path = request.path
            http_method = request.method
            params = {}
            if request.GET:
                for k, v in request.GET.lists():
                    if k.lower() not in self.SENSITIVE_PARAMS:
                        params[k] = v[0] if len(v) == 1 else v
            action = self._infer_action(request, view_name, params)
            status_code = response.status_code
            if status_code < 400:
                result = ActivityLog.Result.SUCCESS
            elif 400 <= status_code < 500:
                result = ActivityLog.Result.WARNING
            else:
                result = ActivityLog.Result.ERROR

            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip_address = x_forwarded_for.split(',')[0].strip()
            else:
                ip_address = request.META.get('REMOTE_ADDR')

            user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]

            submodule = None
            if view_name:
                submodule = Submodule.objects.filter(url_name=view_name).first()

            ActivityLog.objects.create(
                user=request.user,
                path=path,
                view_name=view_name,
                http_method=http_method,
                submodule=submodule,
                action=action,
                result=result,
                status_code=status_code,
                params=params,
                ip_address=ip_address,
                user_agent=user_agent,
                duration_ms=duration_ms,
            )
        except Exception as e:
            logger.warning(f"Error al registrar ActivityLog: {e}")

    def _infer_action(self, request, view_name: str, params: dict) -> str:
        path_lower = request.path.lower()
        view_lower = view_name.lower() if view_name else ''
        method = request.method.upper()

        if 'export' in path_lower or 'export' in view_lower:
            return ActivityLog.Action.EXPORT
        if 'import' in path_lower or 'upload' in path_lower or 'import' in view_lower:
            return ActivityLog.Action.IMPORT
        if 'login' in path_lower or 'login' in view_lower:
            return ActivityLog.Action.LOGIN
        if 'logout' in path_lower or 'logout' in view_lower:
            return ActivityLog.Action.LOGOUT
        if method == 'POST':
            if 'delete' in path_lower or 'delete' in view_lower:
                return ActivityLog.Action.DELETE
            if any(term in path_lower or term in view_lower for term in ('create', 'add', 'new')):
                return ActivityLog.Action.CREATE
            return ActivityLog.Action.UPDATE
        if method == 'DELETE':
            return ActivityLog.Action.DELETE
        if method == 'GET' and params:
            return ActivityLog.Action.FILTER
        return ActivityLog.Action.VIEW
