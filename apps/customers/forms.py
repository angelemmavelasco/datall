from django import forms
from django.forms import inlineformset_factory

from apps.mapser.models import CustomerGeoProfile
from .models import (
    Customer,
    CustomerAssignment,
    CustomerClassMargin,
    CustomerNote,
    CustomerNoteCategoryChoices,
    CustomerContact,
)


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


class CustomerGeoProfileForm(forms.ModelForm):
    """
    form for creating and updating customer geographic profile
    """

    class Meta:
        model = CustomerGeoProfile
        fields = [
            'street_address',
            'neighborhood',
            'municipality',
            'state',
            'zip_code',
            'latitude',
            'longitude',
            'is_verified',
        ]
        widgets = {
            'street_address': forms.TextInput(attrs={
                'placeholder': 'Calle, número exterior e interior',
            }),
            'neighborhood': forms.TextInput(attrs={
                'placeholder': 'Colonia o asentamiento',
            }),
            'municipality': forms.TextInput(attrs={
                'placeholder': 'Municipio o alcaldía',
            }),
            'state': forms.TextInput(attrs={
                'placeholder': 'Entidad federativa / Estado',
            }),
            'zip_code': forms.TextInput(attrs={
                'placeholder': 'Código Postal',
                'maxlength': '10',
            }),
            'latitude': forms.NumberInput(attrs={
                'step': 'any',
                'placeholder': 'Ej. 19.432608',
            }),
            'longitude': forms.NumberInput(attrs={
                'step': 'any',
                'placeholder': 'Ej. -99.133209',
            }),
            'is_verified': forms.CheckboxInput(),
        }

    def clean_zip_code(self):
        zip_code = self.cleaned_data.get('zip_code')
        if zip_code:
            return zip_code.strip()
        return ''

    def clean_latitude(self):
        lat = self.cleaned_data.get('latitude')
        if lat is not None:
            from decimal import Decimal
            return round(Decimal(str(lat)), 9)
        return lat

    def clean_longitude(self):
        lng = self.cleaned_data.get('longitude')
        if lng is not None:
            from decimal import Decimal
            return round(Decimal(str(lng)), 9)
        return lng

    def clean(self):
        cleaned_data = super().clean()
        lat = cleaned_data.get('latitude')
        lng = cleaned_data.get('longitude')

        if lat is not None and lng is None:
            self.add_error('longitude', 'Si indicas la latitud, también debes proporcionar la longitud.')
        elif lng is not None and lat is None:
            self.add_error('latitude', 'Si indicas la longitud, también debes proporcionar la latitud.')

        if lat is not None and not (-90 <= lat <= 90):
            self.add_error('latitude', 'La latitud debe estar entre -90 y 90 grados.')

        if lng is not None and not (-180 <= lng <= 180):
            self.add_error('longitude', 'La longitud debe estar entre -180 y 180 grados.')

        return cleaned_data


class CustomerNoteForm(forms.ModelForm):
    class Meta:
        model = CustomerNote
        fields = ['category', 'content', 'is_pinned']
        labels = {
            'category': 'Categoría',
            'content': 'Contenido',
            'is_pinned': 'Fijar nota',
        }
        widgets = {
            'category': forms.Select(),
            'content': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Escribe aquí la nota o detalle relevante...',
            }),
            'is_pinned': forms.CheckboxInput(),
        }

    def clean_content(self):
        content = self.cleaned_data.get('content')
        if content:
            return content.strip()
        return content


class CustomerContactForm(forms.ModelForm):
    class Meta:
        model = CustomerContact
        fields = ['name', 'role', 'phone', 'mobile', 'email', 'is_primary', 'notes']
        labels = {
            'name': 'Nombre del contacto',
            'role': 'Función / Cargo',
            'phone': 'Teléfono directo / oficina',
            'mobile': 'Celular / WhatsApp',
            'email': 'Correo electrónico',
            'is_primary': 'Contacto principal',
            'notes': 'Notas o especificaciones',
        }
        widgets = {
            'name': forms.TextInput(attrs={
                'placeholder': 'Ej. Lic. Carlos Mendoza',
                'class': 'w-full bg-container border border-border rounded p-1 text-xs text-title focus:outline-none focus:border-strong',
            }),
            'role': forms.Select(attrs={
                'class': 'w-full bg-container border border-border rounded p-1 text-xs text-title focus:outline-none focus:border-strong',
            }),
            'phone': forms.TextInput(attrs={
                'placeholder': 'Ej. 55 1234 5678 ext 102',
                'class': 'w-full bg-container border border-border rounded p-1 text-xs text-title focus:outline-none focus:border-strong',
            }),
            'mobile': forms.TextInput(attrs={
                'placeholder': 'Ej. 55 9876 5432',
                'class': 'w-full bg-container border border-border rounded p-1 text-xs text-title focus:outline-none focus:border-strong',
            }),
            'email': forms.EmailInput(attrs={
                'placeholder': 'carlos.mendoza@empresa.com',
                'class': 'w-full bg-container border border-border rounded p-1 text-xs text-title focus:outline-none focus:border-strong',
            }),
            'is_primary': forms.CheckboxInput(attrs={
                'class': 'rounded border-border',
            }),
            'notes': forms.TextInput(attrs={
                'placeholder': 'Ej. Horario de atención: 9:00 a 14:00 hrs',
                'class': 'w-full bg-container border border-border rounded p-1 text-xs text-title focus:outline-none focus:border-strong',
            }),
        }

    def clean_name(self):
        name = self.cleaned_data.get('name')
        if name:
            return name.strip().title()
        return name

    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        if phone:
            return phone.strip()
        return None

    def clean_mobile(self):
        mobile = self.cleaned_data.get('mobile')
        if mobile:
            return mobile.strip()
        return None

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email:
            return email.strip().lower()
        return None

    def clean_notes(self):
        notes = self.cleaned_data.get('notes')
        if notes:
            return notes.strip()
        return None



