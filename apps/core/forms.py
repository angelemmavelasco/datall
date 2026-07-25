from apps.core.models import User
from django.forms import ModelForm

class UserForm(ModelForm):
    class Meta:
        model = User
        fields = '__all__'
        exclude = ('password', 'user_permissions', 'last_login', 'date_joined')

    def __init__(self, *args, requesting_user=None, is_full_access=False, **kwargs):
        super().__init__(*args, **kwargs)

        if not requesting_user:
            return

        is_superuser = getattr(requesting_user, 'is_superuser', False)
        if not is_superuser:
            self.fields.pop('is_superuser', None)

        if not is_full_access and not is_superuser:
            disallowed_fields = ['is_staff', 'is_active', 'groups', 'username',]
            for field_name in disallowed_fields:
                self.fields.pop(field_name, None)
        
