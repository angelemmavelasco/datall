from apps.core.models import User
from django.forms import ModelForm

class UserForm(ModelForm):
    class Meta:
        model = User
        fields = '__all__'
        exclude = ('user_permissions',)
