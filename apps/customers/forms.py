from django import forms
from django.forms import inlineformset_factory

from .models import Customer, CustomerAssignment, CustomerClassMargin


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = [
            'id',
            'name',
            'customer_type',
            'registration_date',
            'credit_limit',
            'credit_days',
            'opinion_leader',
        ]
        widgets = {
            'registration_date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
            'credit_limit': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'credit_days': forms.NumberInput(attrs={'min': '0'}),
        }

    def clean_id(self):
        customer_id = self.cleaned_data.get('id')
        if customer_id:
            return customer_id.strip().upper()
        return customer_id


CustomerAssignmentFormSet = inlineformset_factory(
    Customer,
    CustomerAssignment,
    fields=['route', 'start_date', 'end_date', 'notes'],
    widgets={
        'start_date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
        'end_date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
        'notes': forms.Textarea(attrs={'rows': 1}),
    },
    extra=1,
    can_delete=True,
)


CustomerClassMarginFormSet = inlineformset_factory(
    Customer,
    CustomerClassMargin,
    fields=['product_class', 'min_margin_percentage'],
    widgets={
        'min_margin_percentage': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'placeholder': '0.00'}),
    },
    extra=1,
    can_delete=True,
)
