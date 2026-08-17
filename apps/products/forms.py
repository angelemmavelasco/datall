from django import forms
from django.forms import inlineformset_factory

from .models import Product, ProductPropertyValue, Stock


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            'id',
            'name',
            'barcode',
            'product_class',
            'cost',
            'price',
            'unit_of_measure',
            'is_active',
        ]
        widgets = {
            'cost': forms.NumberInput(attrs={'step': '0.0001', 'min': '0'}),
            'price': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
        }

    def clean_id(self):
        product_id = self.cleaned_data.get('id')
        if product_id:
            return product_id.strip().upper()
        return product_id


ProductPropertyValueFormSet = inlineformset_factory(
    Product,
    ProductPropertyValue,
    fields=['property', 'value'],
    widgets={
        'value': forms.TextInput(attrs={'placeholder': 'Valor o especificación'}),
    },
    extra=1,
    can_delete=True,
)


StockFormSet = inlineformset_factory(
    Product,
    Stock,
    fields=['warehouse', 'lot_number', 'expiration_date', 'quantity'],
    widgets={
        'expiration_date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
        'quantity': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
    },
    extra=1,
    can_delete=True,
)
