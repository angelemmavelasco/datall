from decimal import Decimal
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
            'weight',
            'pieces_per_box',
            'boxes_per_pallet',
            'is_active',
        ]
        widgets = {
            'cost': forms.NumberInput(attrs={'step': '0.0001', 'min': '0'}),
            'price': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
            'weight': forms.NumberInput(attrs={'step': '0.0001', 'min': '0'}),
            'pieces_per_box': forms.NumberInput(attrs={'step': '1', 'min': '1'}),
            'boxes_per_pallet': forms.NumberInput(attrs={'step': '1', 'min': '1'}),
        }

    def clean_id(self):
        product_id = self.cleaned_data.get('id')
        if product_id:
            return product_id.strip().upper()
        return product_id

    def clean_weight(self):
        weight = self.cleaned_data.get('weight')
        if weight is None:
            return Decimal('0.0000')
        return weight

    def clean_pieces_per_box(self):
        pieces = self.cleaned_data.get('pieces_per_box')
        if not pieces or pieces < 1:
            return 1
        return pieces

    def clean_boxes_per_pallet(self):
        boxes = self.cleaned_data.get('boxes_per_pallet')
        if not boxes or boxes < 1:
            return 1
        return boxes


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
