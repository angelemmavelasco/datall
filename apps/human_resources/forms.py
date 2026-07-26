from apps.human_resources.models import Department
from django import forms

class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = '__all__'

    def __init__(self, *args, requesting_user=None, is_full_access=False, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk:
            self.fields['id'].disabled = True

        if not requesting_user:
            return

        is_superuser = getattr(requesting_user, 'is_superuser', False)
        if not is_full_access and not is_superuser:
            pass
