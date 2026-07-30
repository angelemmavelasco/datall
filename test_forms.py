import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from apps.core.models import User
from apps.human_resources.services.monitoring import MonitoringService

user = User.objects.first()
ms = MonitoringService(user=user)

own_forms = ms.read_forms(own_forms=True)
print("OWN FORMS:")
for f in own_forms:
    print(f.name, f.assigned_employees_count, getattr(f, 'target_levels_display', ''), getattr(f, 'target_positions_display', ''))

sub_forms = ms.read_forms(own_forms=False)
print("SUB FORMS:")
for f in sub_forms:
    print(f.name, f.assigned_employees_count, getattr(f, 'target_levels_display', ''), getattr(f, 'target_positions_display', ''))
