from django import forms
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class UserForm(forms.ModelForm):
    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput()
    )

    class Meta:
        model = User
        exclude = ['date_joined', 'last_login', 'user_permissions']
        widgets = {
            'groups': forms.CheckboxSelectMultiple()
        }