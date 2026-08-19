from django import forms
from django.forms import inlineformset_factory
from apps.human_resources.models import Department, Skill, Position, PositionSkill, PositionKPI, BusinessUnit, Employee
from apps.human_resources.models import MonitoringForm, MonitoringFormSchedule, MonitoringFormQuestion, MonitoringFormField
from django.core.files.storage import default_storage
import uuid
import os

class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = [
            'id', 'user', 'position', 'manager', 'business_unit',
            'hire_date', 'termination_date', 'contract_type',
            'contract_doc', 'tax_doc', 'tax_regime', 'tax_id',
            'payment_form', 'payroll_payment_amount', 'payroll_frequency'
        ]
        widgets = {
            'hire_date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
            'termination_date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
        }

class BusinessUnitForm(forms.ModelForm):
    class Meta:
        model = BusinessUnit
        fields = ['id', 'name', 'business_unit_type', 'parent', 'manager']

class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = '__all__'

class SkillForm(forms.ModelForm):
    class Meta:
        model = Skill
        fields = '__all__'

class PositionForm(forms.ModelForm):
    class Meta:
        model = Position
        fields = ['id', 'name', 'department', 'description', 'hierarchy_level']

PositionSkillFormSet = inlineformset_factory(
    Position, PositionSkill,
    fields=['skill', 'requirement_level', 'skill_level', 'notes'],
    extra=1,
    can_delete=True
)

PositionKPIFormSet = inlineformset_factory(
    Position, PositionKPI,
    fields=['name', 'description', 'unit', 'target_value', 'weight', 'frequency'],
    extra=1,
    can_delete=True
)

class MonitoringFormForm(forms.ModelForm):
    class Meta:
        model = MonitoringForm
        fields = ['id', 'name', 'version', 'periodicity', 'is_active']

class MonitoringFormScheduleForm(forms.ModelForm):
    class Meta:
        model = MonitoringFormSchedule
        fields = ['open_day', 'week_of_month', 'open_time', 'duration_hours']

class MonitoringFormQuestionForm(forms.ModelForm):
    class Meta:
        model = MonitoringFormQuestion
        fields = ['question', 'hierarchy_level', 'position', 'order', 'is_required']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'question' in self.fields:
            self.fields['question'].queryset = MonitoringFormField.objects.filter(is_active=True)

MonitoringFormQuestionFormSet = inlineformset_factory(
    MonitoringForm, MonitoringFormQuestion,
    form=MonitoringFormQuestionForm,
    extra=1,
    can_delete=True
)

class MonitoringFormFieldForm(forms.ModelForm):
    class Meta:
        model = MonitoringFormField
        fields = ['label', 'response_type', 'description', 'is_active']

class FileWrapper:
    def __init__(self, data_dict):
        self.data_dict = data_dict
        self.url = data_dict.get('answer', '')
        self.name = data_dict.get('display', '')
        self.file_type = data_dict.get('file_type', '')
        
    def __str__(self):
        return self.name

class MonitoringSubmissionForm(forms.Form):
    def __init__(self, *args, questions=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.questions = questions or []
        if questions:
            for q in questions:
                field_name = f'question_{q.id}'
                response_type = q.question.response_type
                is_required = q.is_required
                
                base_attrs = {
                    'class': 'w-full bg-page border border-border p-2 rounded focus:outline-none focus:ring-1 focus:ring-emerald-500 text-body'
                }
                
                if response_type == MonitoringFormField.ResponseTypeChoices.TEXT:
                    attrs = base_attrs.copy()
                    attrs['rows'] = 3
                    self.fields[field_name] = forms.CharField(required=is_required, widget=forms.Textarea(attrs=attrs))
                elif response_type == MonitoringFormField.ResponseTypeChoices.NUMBER:
                    self.fields[field_name] = forms.FloatField(required=is_required, widget=forms.NumberInput(attrs=base_attrs))
                elif response_type == MonitoringFormField.ResponseTypeChoices.PERCENTAGE:
                    attrs = base_attrs.copy()
                    attrs['step'] = '0.01'
                    self.fields[field_name] = forms.FloatField(required=is_required, widget=forms.NumberInput(attrs=attrs))
                elif response_type == MonitoringFormField.ResponseTypeChoices.SCALE_1_5:
                    attrs = base_attrs.copy()
                    attrs.update({'min': 1, 'max': 5})
                    self.fields[field_name] = forms.IntegerField(required=is_required, min_value=1, max_value=5, widget=forms.NumberInput(attrs=attrs))
                elif response_type == MonitoringFormField.ResponseTypeChoices.BOOLEAN:
                    checkbox_attrs = {
                        'class': 'w-4 h-4 text-emerald-500 bg-page border-border rounded focus:ring-emerald-500'
                    }
                    self.fields[field_name] = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs=checkbox_attrs))
                elif response_type == MonitoringFormField.ResponseTypeChoices.FILE:
                    file_attrs = {
                        'class': 'w-full text-body file:bg-container file:border-0 file:text-emerald-500 file:font-medium file:cursor-pointer file:py-1 file:px-3 file:rounded'
                    }
                    self.fields[field_name] = forms.FileField(required=is_required, widget=forms.ClearableFileInput(attrs=file_attrs))

    def clean(self):
        cleaned_data = super().clean()
        if not hasattr(self, 'questions'):
            return cleaned_data
        for q in self.questions:
            field_name = f'question_{q.id}'
            if q.question.response_type == MonitoringFormField.ResponseTypeChoices.FILE:
                file_obj = cleaned_data.get(field_name)
                if file_obj is False:
                    cleaned_data[field_name] = ''
                elif file_obj and hasattr(file_obj, 'read'):
                    ext = os.path.splitext(file_obj.name)[1]
                    filename = f"monitoring_submissions/{uuid.uuid4()}{ext}"
                    path = default_storage.save(filename, file_obj)
                    url = default_storage.url(path)
                    
                    cleaned_data[field_name] = {
                        "answer": url,
                        "display": file_obj.name,
                        "file_type": getattr(file_obj, 'content_type', 'application/octet-stream')
                    }
                elif isinstance(file_obj, FileWrapper):
                    cleaned_data[field_name] = file_obj.data_dict
                elif not file_obj and field_name in self.initial:
                    initial_val = self.initial[field_name]
                    cleaned_data[field_name] = initial_val.data_dict if isinstance(initial_val, FileWrapper) else initial_val
        return cleaned_data
