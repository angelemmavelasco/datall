from apps.human_resources.models import Department, Position, Skill, PositionSkill, Employee
from django import forms
from django.forms import inlineformset_factory
from django.utils import timezone
import uuid

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
        widgets = {
            'hire_date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
            'termination_date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
        }

    def __init__(self, *args, requesting_user=None, is_full_access=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['id'].required = False

        if self.instance and self.instance.pk:
            self.fields['id'].disabled = True

        if not requesting_user:
            return

        is_superuser = getattr(requesting_user, 'is_superuser', False)
        if not is_full_access and not is_superuser:
            pass

    def clean_id(self):
        id_val = self.cleaned_data.get('id')
        if not id_val:
            while True:
                generated_id = str(uuid.uuid4())[-5:].lower()
                if not Employee.objects.filter(pk=generated_id).exists():
                    return generated_id
        return id_val.strip().lower()

    def clean(self):
        cleaned_data = super().clean()
        user = cleaned_data.get('user')
        position = cleaned_data.get('position')
        termination_date = cleaned_data.get('termination_date')
        
        today = timezone.now().date()
        is_active = termination_date is None or termination_date > today

        if user and position and is_active:
            qs = Employee.objects.filter(
                user=user,
                position=position,
                termination_date__isnull=True
            )
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)

            if qs.exists():
                user_name = f"{user.first_name.title()} {user.last_name.title()}" if hasattr(user, 'first_name') else str(user)
                pos_name = position.name.title() if hasattr(position, 'name') else str(position)
                msg = f'El colaborador {user_name} ya cuenta con una asignación activa en el puesto "{pos_name}".'
                self.add_error('user', msg)
                self.add_error('position', msg)

        return cleaned_data
