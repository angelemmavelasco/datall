from django import forms
from apps.human_resources.models import Department

class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = '__all__'
