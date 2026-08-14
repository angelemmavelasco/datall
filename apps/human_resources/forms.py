from django import forms
from django.forms import inlineformset_factory
from apps.human_resources.models import Department, Skill, Position, PositionSkill, PositionKPI
from apps.human_resources.models import MonitoringForm, MonitoringFormSchedule, MonitoringFormQuestion, MonitoringFormField

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

class MonitoringSubmissionForm(forms.Form):
    def __init__(self, *args, questions=None, **kwargs):
        super().__init__(*args, **kwargs)
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
                    self.fields[field_name] = forms.FileField(required=False, widget=forms.ClearableFileInput(attrs=file_attrs))
