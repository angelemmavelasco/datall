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
    CustomerAgreement,
    CommercialBenefit,
    EvaluationModeChoices,
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


class CustomerAgreementCreateForm(forms.ModelForm):
    doc_id = forms.CharField(
        max_length=50,
        required=False,
        label='Folio de convenio',
        widget=forms.TextInput(attrs={
            'placeholder': 'Ej. CONV-2026-001 (dejar vacío para autogenerar)',
            'class': 'w-full bg-page border border-border rounded p-1 text-xs text-title focus:outline-none focus:border-strong font-mono',
        })
    )
    start_date = forms.CharField(
        label='Mes de inicio',
        widget=forms.TextInput(attrs={
            'type': 'month',
            'class': 'w-full bg-page border border-border rounded focus:outline-none focus:border-strong focus:ring-strong p-1 font-mono text-xs text-title',
            'placeholder': 'AAAA-MM',
        })
    )
    end_date = forms.CharField(
        label='Mes de fin',
        widget=forms.TextInput(attrs={
            'type': 'month',
            'class': 'w-full bg-page border border-border rounded focus:outline-none focus:border-strong focus:ring-strong p-1 font-mono text-xs text-title',
            'placeholder': 'AAAA-MM',
        })
    )

    class Meta:
        model = CustomerAgreement
        fields = [
            'customer',
            'benefit',
            'agreement_type',
            'evaluation_mode',
            'start_date',
            'end_date',
            'global_target_amount',
            'target_frequency',
            'penalty_amount',
            'growth_value',
            'growth_frequency',
            'doc_id',
            'related_doc',
            'margin_warning_accepted',
            'signed',
            'benefit_already_provided',
        ]
        widgets = {
            'customer': forms.Select(attrs={
                'class': 'w-full bg-page border border-border rounded p-1 text-xs text-title focus:outline-none focus:border-strong',
            }),
            'benefit': forms.Select(attrs={
                'class': 'w-full bg-page border border-border rounded p-1 text-xs text-title focus:outline-none focus:border-strong',
            }),
            'agreement_type': forms.Select(attrs={
                'class': 'w-full bg-page border border-border rounded p-1 text-xs text-title focus:outline-none focus:border-strong',
            }),
            'evaluation_mode': forms.Select(attrs={
                'class': 'w-full bg-page border border-border rounded p-1 text-xs text-title focus:outline-none focus:border-strong',
            }),
            'global_target_amount': forms.NumberInput(attrs={
                'step': '0.01',
                'min': '0',
                'placeholder': '0.00',
                'class': 'w-full bg-page border border-border rounded p-1 text-xs text-title focus:outline-none focus:border-strong font-mono',
            }),
            'target_frequency': forms.Select(attrs={
                'class': 'w-full bg-page border border-border rounded p-1 text-xs text-title focus:outline-none focus:border-strong',
            }),
            'penalty_amount': forms.NumberInput(attrs={
                'step': '0.01',
                'min': '0',
                'placeholder': '0.00',
                'class': 'w-full bg-page border border-border rounded p-1 text-xs text-title focus:outline-none focus:border-strong font-mono',
            }),
            'growth_value': forms.NumberInput(attrs={
                'step': '0.01',
                'min': '0',
                'placeholder': '0.00',
                'class': 'w-full bg-page border border-border rounded p-1 text-xs text-title focus:outline-none focus:border-strong font-mono',
            }),
            'growth_frequency': forms.Select(attrs={
                'class': 'w-full bg-page border border-border rounded p-1 text-xs text-title focus:outline-none focus:border-strong',
            }),
            'related_doc': forms.FileInput(attrs={
                'class': 'w-full bg-page border border-border rounded p-1 text-xs text-title',
            }),
            'margin_warning_accepted': forms.CheckboxInput(attrs={
                'class': 'rounded border-border text-primary focus:ring-primary',
            }),
            'signed': forms.CheckboxInput(attrs={
                'class': 'rounded border-border text-primary focus:ring-primary',
            }),
            'benefit_already_provided': forms.CheckboxInput(attrs={
                'class': 'rounded border-border text-primary focus:ring-primary',
            }),
        }

    def __init__(self, *args, **kwargs):
        allowed_customers = kwargs.pop('allowed_customers', None)
        super().__init__(*args, **kwargs)
        self.fields['benefit'].queryset = CommercialBenefit.objects.filter(is_active=True).order_by('name')
        if allowed_customers is not None:
            self.fields['customer'].queryset = allowed_customers
        self.fields['growth_frequency'].required = False
        self.fields['growth_value'].required = False
        self.fields['related_doc'].required = False
        self.fields['penalty_amount'].required = False
        self.fields['signed'].required = False
        self.fields['benefit_already_provided'].required = False
        self.fields['evaluation_mode'].required = False
        self.fields['evaluation_mode'].initial = EvaluationModeChoices.PERIODIC

        if self.instance and self.instance.pk:
            if self.instance.start_date:
                self.initial['start_date'] = self.instance.start_date.strftime('%Y-%m')
            if self.instance.end_date:
                self.initial['end_date'] = self.instance.end_date.strftime('%Y-%m')

    def clean_evaluation_mode(self):
        mode = self.cleaned_data.get('evaluation_mode')
        if not mode:
            mode = EvaluationModeChoices.PERIODIC
        return mode

    def clean_doc_id(self):
        doc_id = self.cleaned_data.get('doc_id')
        if doc_id:
            doc_id = doc_id.strip().upper()
            if CustomerAgreement.objects.filter(doc_id__iexact=doc_id).exists():
                raise forms.ValidationError(f"El folio de convenio '{doc_id}' ya existe.")
            return doc_id
        return None

    def clean_start_date(self):
        from .services.customer_agreements import parse_month_input
        val = self.cleaned_data.get('start_date')
        if not val:
            raise forms.ValidationError("Este campo es obligatorio.")
        d = parse_month_input(val, is_end=False)
        if not d:
            raise forms.ValidationError("Mes inválido. Utilice formato MM/AAAA.")
        return d

    def clean_end_date(self):
        from .services.customer_agreements import parse_month_input
        val = self.cleaned_data.get('end_date')
        if not val:
            raise forms.ValidationError("Este campo es obligatorio.")
        d = parse_month_input(val, is_end=True)
        if not d:
            raise forms.ValidationError("Mes inválido. Utilice formato MM/AAAA.")
        return d

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        if start_date and end_date and end_date < start_date:
            self.add_error('end_date', 'El mes de fin no puede ser anterior al mes de inicio.')
        return cleaned_data


class CustomerAgreementDocumentForm(forms.ModelForm):
    class Meta:
        model = CustomerAgreement
        fields = ['signed', 'benefit_already_provided', 'related_doc']
        labels = {
            'signed': 'Convenio firmado por el cliente',
            'benefit_already_provided': 'Beneficio comercial entregado',
            'related_doc': 'Documento o contrato escaneado',
        }
        widgets = {
            'signed': forms.CheckboxInput(attrs={
                'class': 'rounded border-border text-primary focus:ring-primary w-4 h-4',
            }),
            'benefit_already_provided': forms.CheckboxInput(attrs={
                'class': 'rounded border-border text-primary focus:ring-primary w-4 h-4',
            }),
            'related_doc': forms.FileInput(attrs={
                'class': 'w-full bg-page border border-border rounded p-1 text-xs text-secondary file:mr-2 file:py-0.5 file:px-2 file:rounded file:border-0 file:text-xs file:bg-container file:text-title hover:file:bg-hover cursor-pointer',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['related_doc'].required = False
        self.fields['signed'].required = False
        self.fields['benefit_already_provided'].required = False



