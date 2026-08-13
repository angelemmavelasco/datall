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
