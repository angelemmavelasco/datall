from django import forms
from .models import TaxSystem

class TaxSystemForm(forms.ModelForm):
    class Meta:
        model = TaxSystem
        fields = '__all__'
