from django.db.models import Q, Prefetch
from .models import Module, Submodule


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
        'modules': modules
    }
