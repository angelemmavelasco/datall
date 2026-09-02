from django import forms
from django.contrib.auth.password_validation import validate_password
from apps.core.models import User

class UserForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        required=False,
        label="Contraseña",
        help_text="Deja en blanco si no deseas cambiarla."
    )

    class Meta:
        model = User
        fields = '__all__'
        exclude = ('password', 'user_permissions', 'last_login', 'date_joined')
        widgets = {
            'groups': forms.CheckboxSelectMultiple(),
            'birth_date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
        }

    def __init__(self, *args, requesting_user=None, is_full_access=False, **kwargs):
        super().__init__(*args, **kwargs)

        is_editing = bool(self.instance and self.instance.pk)
        is_editing_self = is_editing and (requesting_user and self.instance.pk == requesting_user.pk)

        if is_editing:
            if not is_editing_self:
                self.fields.pop('password', None)
        else:
            if 'password' in self.fields:
                self.fields['password'].required = True

        if not requesting_user:
            return

        is_superuser = getattr(requesting_user, 'is_superuser', False)

        if not is_superuser:
            self.fields.pop('is_superuser', None)
            self.fields.pop('is_staff', None)

        if not is_full_access and not is_superuser:
            disallowed_fields = ['is_active', 'groups', 'username',]
            for field_name in disallowed_fields:
                self.fields.pop(field_name, None)

    def clean_password(self):
        if 'password' not in self.fields:
            return None

        password = self.cleaned_data.get('password')
        if password:
            validate_password(password, user=self.instance)
            return password
        return None

    def clean(self):
        cleaned_data = super().clean()
        if self.instance and self.instance.pk:
            if not cleaned_data.get('password'):
                cleaned_data.pop('password', None)
        return cleaned_data