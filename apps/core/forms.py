from django.forms import ModelForm, CheckboxSelectMultiple
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class UserForm(ModelForm):
    class Meta:
        model = User
        exclude = ['date_joined', 'last_login', 'user_permissions']
        widgets = {
            'groups': CheckboxSelectMultiple()
        }