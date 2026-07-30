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

class MonitoringFormForm(forms.ModelForm):
    class Meta:
        from apps.human_resources.models import MonitoringForm
        model = MonitoringForm
        fields = ['id', 'name', 'version', 'periodicity', 'is_active']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['id'].required = False
        if self.instance and self.instance.pk:
            self.fields['id'].disabled = True

    def clean_id(self):
        id_val = self.cleaned_data.get('id')
        if not id_val:
            while True:
                generated_id = str(uuid.uuid4())[-5:].upper()
                from apps.human_resources.models import MonitoringForm
                if not MonitoringForm.objects.filter(pk=generated_id).exists():
                    return generated_id
        return id_val.strip().upper()

class MonitoringFormQuestionForm(forms.ModelForm):
    class Meta:
        from apps.human_resources.models import MonitoringFormQuestion
        model = MonitoringFormQuestion
        fields = ['question', 'order', 'hierarchy_level', 'position']

    def clean(self):
        cleaned_data = super().clean()
        hierarchy_level = cleaned_data.get('hierarchy_level')
        position = cleaned_data.get('position')
        return cleaned_data

from apps.human_resources.models import MonitoringForm, MonitoringFormQuestion
MonitoringFormQuestionFormSet = inlineformset_factory(
    MonitoringForm,
    MonitoringFormQuestion,
    form=MonitoringFormQuestionForm,
    fields=['question', 'order', 'hierarchy_level', 'position'],
    extra=1,
    can_delete=True
)

class MonitoringSubmissionForm(forms.Form):
    def __init__(self, *args, **kwargs):
        self.monitoring_form = kwargs.pop('monitoring_form', None)
        self.employee = kwargs.pop('employee', None)
        super().__init__(*args, **kwargs)

        if self.monitoring_form and self.employee:
            emp_pos = self.employee.position
            emp_level = emp_pos.hierarchy_level if emp_pos else None

            questions = self.monitoring_form.human_resources_form_questions.filter(
                question__is_active=True
            ).select_related('question').order_by('order')

            self.hierarchy_fields = []
            self.position_fields = []

            for mq in questions:
                # Validar si aplica al empleado
                is_applicable = False
                if mq.hierarchy_level and mq.hierarchy_level == emp_level:
                    is_applicable = True
                elif mq.position_id and mq.position_id == emp_pos.id:
                    is_applicable = True
                elif not mq.hierarchy_level and not mq.position_id:
                    is_applicable = True

                if not is_applicable:
                    continue

                q = mq.question
                field_name = f'question_{mq.id}'
                
                # Tipo de respuesta
                if q.response_type == 'boolean':
                    field = forms.BooleanField(label=q.label, required=False)
                elif q.response_type == 'scale_1_5':
                    field = forms.ChoiceField(
                        label=q.label,
                        choices=[(i, str(i)) for i in range(1, 6)],
                        required=True
                    )
                elif q.response_type == 'percentage':
                    field = forms.IntegerField(
                        label=q.label, 
                        min_value=0, 
                        max_value=100,
                        required=True
                    )
                elif q.response_type == 'number':
                    field = forms.FloatField(label=q.label, required=True)
                elif q.response_type == 'file':
                    field = forms.FileField(label=q.label, required=True)
                else:
                    field = forms.CharField(label=q.label, widget=forms.Textarea(attrs={'rows': 2}), required=True)

                self.fields[field_name] = field
                
                if mq.position_id:
                    self.position_fields.append(field_name)
                else:
                    self.hierarchy_fields.append(field_name)
