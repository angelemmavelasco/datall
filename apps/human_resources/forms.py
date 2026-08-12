from django import forms
from django.forms import inlineformset_factory
from apps.human_resources.models import Department, Skill, Position, PositionSkill, PositionKPI

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
