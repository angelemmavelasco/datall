from apps.core.models import User
from django import forms
from django.contrib.auth.password_validation import validate_password

class UserForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput(), required=False, label="Contraseña")

    class Meta:
        model = User
        fields = '__all__'
        exclude = ('user_permissions', 'last_login', 'date_joined')
        widgets = {
            'groups': forms.CheckboxSelectMultiple(),
            'birth_date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
        }

    def clean_password(self):
        password = self.cleaned_data.get('password')
        if password:
            validate_password(password)
        return password

    def __init__(self, *args, requesting_user=None, is_full_access=False, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk:
            self.fields.pop('password', None)
        else:
            if 'password' in self.fields:
                self.fields['password'].required = True

        if not requesting_user:
            return

        is_superuser = getattr(requesting_user, 'is_superuser', False)
        if not is_superuser:
            self.fields.pop('is_superuser', None)

        if not is_full_access and not is_superuser:
            disallowed_fields = ['is_staff', 'is_active', 'groups', 'username']
            for field_name in disallowed_fields:
                self.fields.pop(field_name, None)
        
