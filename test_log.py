import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.core.models import DataHistory
from django.contrib.auth import get_user_model
from django.forms.models import model_to_dict
from apps.data_admin.services.data_history.data_history_crud import DataHistoryCrud

User = get_user_model()
user = User.objects.first()
new_state = model_to_dict(user)

try:
    print("New state:", new_state)
    import json
    json.dumps(new_state)
    print("JSON serialization OK")
except Exception as e:
    print("JSON Error:", e)

