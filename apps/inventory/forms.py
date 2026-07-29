from django import forms
from .models import Product, ProductVariant

TARGET_SPECIES_CHOICES = [
    ('caninos', 'Caninos'),
    ('felinos', 'Felinos'),
    ('bovinos', 'Bovinos'),
    ('porcinos', 'Porcinos'),
    ('equinos', 'Equinos'),
    ('aves', 'Aves'),
    ('ovinos_caprinos', 'Ovinos / Caprinos'),
    ('peces_acuacultura', 'Peces / Acuacultura'),
]

ADMINISTRATION_ROUTE_CHOICES = [
    ('', '--- Seleccionar ---'),
    ('Oral', 'Oral'),
    ('Intramuscular', 'Intramuscular'),
    ('Subcutánea', 'Subcutánea'),
    ('Intravenosa', 'Intravenosa'),
    ('Tópica', 'Tópica'),
    ('Oftálmica / Otológica', 'Oftálmica / Otológica'),
    ('Intramamaria', 'Intramamaria'),
    ('Inmersión / Baño', 'Inmersión / Baño'),
]


class ProductAdminForm(forms.ModelForm):
    target_species = forms.MultipleChoiceField(
        choices=TARGET_SPECIES_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label='Especies destino',
        help_text='Selecciona las especies animales a las que va dirigido el producto.'
    )
    administration_route = forms.ChoiceField(
        choices=ADMINISTRATION_ROUTE_CHOICES,
        required=False,
        label='Vía de administración',
        help_text='Vía de administración principal.'
    )
    sagarpa_register = forms.CharField(
        required=False,
        label='Registro SAGARPA / SENASICA',
        help_text='Ej. Q-0123-456'
    )
    requires_prescription = forms.BooleanField(
        required=False,
        label='Requiere receta médica veterinaria',
        help_text='Marcar si el producto requiere receta médica.'
    )
    withdrawal_period_days = forms.IntegerField(
        required=False,
        min_value=0,
        label='Días de retiro',
        help_text='Tiempo de espera en días antes del consumo de carne o leche.'
    )
    storage_conditions = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'style': 'width: 80%;'}),
        label='Condiciones de almacenamiento',
        help_text='Ej. Conservar en lugar fresco entre 2°C y 8°C.'
    )

    class Meta:
        model = Product
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'properties' in self.fields:
            self.fields['properties'].widget = forms.HiddenInput()

        if self.instance and self.instance.pk and isinstance(self.instance.properties, dict):
            props = self.instance.properties
            self.fields['target_species'].initial = props.get('target_species', [])
            self.fields['administration_route'].initial = props.get('administration_route', '')
            self.fields['sagarpa_register'].initial = props.get('sagarpa_register', '')
            self.fields['requires_prescription'].initial = props.get('requires_prescription', False)
            self.fields['withdrawal_period_days'].initial = props.get('withdrawal_period_days', None)
            self.fields['storage_conditions'].initial = props.get('storage_conditions', '')

    def save(self, commit=True):
        instance = super().save(commit=False)
        props = instance.properties or {}

        if self.cleaned_data.get('target_species'):
            props['target_species'] = self.cleaned_data['target_species']
        else:
            props.pop('target_species', None)

        if self.cleaned_data.get('administration_route'):
            props['administration_route'] = self.cleaned_data['administration_route']
        else:
            props.pop('administration_route', None)

        if self.cleaned_data.get('sagarpa_register'):
            props['sagarpa_register'] = self.cleaned_data['sagarpa_register']
        else:
            props.pop('sagarpa_register', None)

        if self.cleaned_data.get('requires_prescription') is not None:
            props['requires_prescription'] = bool(self.cleaned_data['requires_prescription'])

        if self.cleaned_data.get('withdrawal_period_days') is not None:
            props['withdrawal_period_days'] = self.cleaned_data['withdrawal_period_days']
        else:
            props.pop('withdrawal_period_days', None)

        if self.cleaned_data.get('storage_conditions'):
            props['storage_conditions'] = self.cleaned_data['storage_conditions']
        else:
            props.pop('storage_conditions', None)

        instance.properties = props
        if commit:
            instance.save()
        return instance
