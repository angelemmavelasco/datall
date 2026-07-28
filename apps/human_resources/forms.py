from apps.human_resources.models import Department, Position, Skill, PositionSkill, Employee
from django import forms
from django.forms import inlineformset_factory

class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = '__all__'

    def __init__(self, *args, requesting_user=None, is_full_access=False, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk:
            self.fields['id'].disabled = True

        if not requesting_user:
            return

        is_superuser = getattr(requesting_user, 'is_superuser', False)
        if not is_full_access and not is_superuser:
            pass

class PositionForm(forms.ModelForm):
    class Meta:
        model = Position
        fields = '__all__'

    def __init__(self, *args, requesting_user=None, is_full_access=False, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk:
            self.fields['id'].disabled = True

        if not requesting_user:
            return

        is_superuser = getattr(requesting_user, 'is_superuser', False)
        if not is_full_access and not is_superuser:
            pass


class PositionSkillForm(forms.ModelForm):
    class Meta:
        model = PositionSkill
        fields = ['skill', 'requirement_level', 'skill_level', 'notes']


PositionSkillFormSet = inlineformset_factory(
    Position,
    PositionSkill,
    form=PositionSkillForm,
    fields=['skill', 'requirement_level', 'skill_level', 'notes'],
    extra=1,
    can_delete=True
)

class SkillForm(forms.ModelForm):
    class Meta:
        model = Skill
        fields = '__all__'

class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = '__all__'

    def __init__(self, *args, requesting_user=None, is_full_access=False, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk:
            self.fields['id'].disabled = True

        if not requesting_user:
            return

        is_superuser = getattr(requesting_user, 'is_superuser', False)
        if not is_full_access and not is_superuser:
            pass
