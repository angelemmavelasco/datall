from apps.core.models import MenuSection, SystemModule, Reference, Novelty
from django.db.models import Prefetch
from django.utils import timezone
from datetime import timedelta


def module_permissions(request):
    if not request.user.is_authenticated:
        return {}

    user = request.user

    if user.is_superuser:
        sections = MenuSection.objects.filter(
            modules__isnull=False
        ).distinct().prefetch_related('modules')
        
        return {
            'sections': sections
        }

    user_groups = user.groups.all()

    allowed_modules = SystemModule.objects.filter(
        allowed_groups__in=user_groups
    ).distinct()

    sections = MenuSection.objects.filter(
        modules__in=allowed_modules
    ).distinct().prefetch_related(Prefetch('modules', allowed_modules))


    return {
        'sections': sections
    }

def last_update(request):
    try:
        last_data_update = Reference.objects.filter(
            field_context='last_data_update',
            key="last_update",
        ).first()
    except:
        last_data_update = None
    return {
        'last_data_update': last_data_update
    }


def recent_novelties(request):
    one_week_ago = timezone.now() - timedelta(days=7)
    
    # Obtenemos todas las novedades creadas en los últimos 7 días
    recent = list(Novelty.objects.filter(
        is_active=True,
        created_at__gte=one_week_ago
    ).order_by('-created_at'))
    
    has_novelties = len(recent) > 0

    return {
        'recent_novelties': recent,
        'has_novelties': has_novelties
    }
        

