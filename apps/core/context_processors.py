from django.db.models import Q, Prefetch
from .models import Module, Submodule, GeneratedReport, Reference


def navigation_modules(request):
    """
    Context processor que retorna los módulos y submódulos a los que el usuario
    actual tiene permiso de acceso.
    """
    if not hasattr(request, 'user') or not request.user.is_authenticated:
        return {'modules': []}

    user = request.user

    if user.is_superuser:
        submodules_qs = Submodule.objects.filter(
            is_active=True,
            module__is_active=True
        ).order_by('order')
    else:
        user_groups = user.groups.all()
        submodules_qs = Submodule.objects.filter(
            is_active=True,
            module__is_active=True
        ).filter(
            Q(allowed_users=user) | Q(allowed_groups__in=user_groups)
        ).distinct().order_by('order')

    modules = Module.objects.filter(
        is_active=True,
        id__in=submodules_qs.values_list('module_id', flat=True)
    ).prefetch_related(
        Prefetch('submodules', queryset=submodules_qs)
    ).order_by('order').distinct()

    return {
        'modules': modules,
    }


def user_reports_indicators(request):
    """
    Context processor que retorna el estado de los reportes generados
    en segundo plano para el usuario actual (pendientes / sin ver).
    """
    if not hasattr(request, 'user') or not request.user.is_authenticated:
        return {'has_pending_reports': False, 'has_unseen_reports': False}

    user = request.user

    has_pending_reports = GeneratedReport.objects.filter(
        user=user,
        status=GeneratedReport.Status.PENDING
    ).exists()

    has_unseen_reports = GeneratedReport.objects.filter(
        user=user,
        status__in=[GeneratedReport.Status.COMPLETED, GeneratedReport.Status.FAILED],
        is_seen=False
    ).exists()

    return {
        'has_pending_reports': has_pending_reports,
        'has_unseen_reports': has_unseen_reports,
    }


def last_update_indicator(request):
    try:
        last_data_update = Reference.objects.filter(
            context='ultima_actualizacion_reportes',
            key='datetime'
        ).first()
    except Exception:
        last_data_update = None

    return {
        'last_data_update': last_data_update,
    }

