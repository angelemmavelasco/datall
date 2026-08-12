from django.contrib import admin
from .models import (
    Department,
    Position,
    PositionKPI,
    Skill,
    PositionSkill,
    MonitoringForm,
    MonitoringFormField,
    MonitoringFormQuestion,
    MonitoringFormSubmission,
    MonitoringFormAnswer,
    BusinessUnit,
    Employee,
)

class PositionKPIInline(admin.TabularInline):
    model = PositionKPI
    extra = 1
    fields = ('name', 'unit', 'target_value', 'weight', 'frequency')
    show_change_link = True

class PositionSkillInline(admin.TabularInline):
    model = PositionSkill
    extra = 1
    fields = ('skill', 'requirement_level', 'skill_level', 'notes')
    autocomplete_fields = ['skill']
    show_change_link = True

class MonitoringFormQuestionInline(admin.TabularInline):
    model = MonitoringFormQuestion
    extra = 1
    fields = ('question', 'hierarchy_level', 'position', 'order', 'is_required')
    autocomplete_fields = ['question', 'position']
    show_change_link = True

class MonitoringFormAnswerInline(admin.TabularInline):
    model = MonitoringFormAnswer
    extra = 0
    fields = ('question', 'value')
    autocomplete_fields = ['question']
    show_change_link = True


# --- ModelAdmins ---

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'description')
    search_fields = ('id', 'name')
    ordering = ('id',)

@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'department', 'hierarchy_level')
    list_filter = ('department', 'hierarchy_level')
    search_fields = ('id', 'name', 'department__name')
    ordering = ('department', 'name')
    inlines = [PositionKPIInline, PositionSkillInline]

@admin.register(PositionKPI)
class PositionKPIAdmin(admin.ModelAdmin):
    list_display = ('name', 'position', 'unit', 'target_value', 'weight', 'frequency')
    list_filter = ('unit', 'frequency', 'position__department')
    search_fields = ('name', 'position__name')
    ordering = ('position', '-weight', 'name')

@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ('name', 'skill_type', 'description')
    list_filter = ('skill_type',)
    search_fields = ('name',)
    ordering = ('skill_type', 'name')

@admin.register(PositionSkill)
class PositionSkillAdmin(admin.ModelAdmin):
    list_display = ('position', 'skill', 'requirement_level', 'skill_level')
    list_filter = ('requirement_level', 'skill_level', 'skill__skill_type')
    search_fields = ('position__name', 'skill__name')
    autocomplete_fields = ['position', 'skill']

@admin.register(MonitoringForm)
class MonitoringFormAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'version', 'periodicity', 'is_active')
    list_filter = ('periodicity', 'is_active')
    search_fields = ('id', 'name')
    ordering = ('id',)
    inlines = [MonitoringFormQuestionInline]

@admin.register(MonitoringFormField)
class MonitoringFormFieldAdmin(admin.ModelAdmin):
    list_display = ('label', 'response_type', 'is_active')
    list_filter = ('response_type', 'is_active')
    search_fields = ('label', 'description')

@admin.register(MonitoringFormQuestion)
class MonitoringFormQuestionAdmin(admin.ModelAdmin):
    list_display = ('form', 'question', 'hierarchy_level', 'position', 'order', 'is_required')
    list_filter = ('form', 'hierarchy_level', 'is_required')
    search_fields = ('question__label', 'form__name', 'position__name')
    autocomplete_fields = ['form', 'question', 'position']
    ordering = ('form', 'order')

@admin.register(MonitoringFormSubmission)
class MonitoringFormSubmissionAdmin(admin.ModelAdmin):
    list_display = ('employee', 'form', 'period_identifier', 'submitted_at', 'status')
    list_filter = ('status', 'form', 'period_identifier')
    search_fields = ('employee__id', 'employee__user__first_name', 'employee__user__last_name', 'period_identifier')
    autocomplete_fields = ['employee', 'form']
    inlines = [MonitoringFormAnswerInline]
    ordering = ('-submitted_at',)

@admin.register(MonitoringFormAnswer)
class MonitoringFormAnswerAdmin(admin.ModelAdmin):
    list_display = ('submission', 'question', 'value')
    search_fields = ('submission__employee__user__first_name', 'submission__employee__user__last_name', 'question__question__label')
    autocomplete_fields = ['submission', 'question']

@admin.register(BusinessUnit)
class BusinessUnitAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'parent', 'manager')
    list_filter = ('parent',)
    search_fields = ('id', 'name', 'manager__user__first_name', 'manager__user__last_name')
    autocomplete_fields = ['parent', 'manager']

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'position', 'business_unit', 'manager', 'contract_type', 'payroll_frequency', 'hire_date')
    list_filter = ('contract_type', 'payroll_frequency', 'tax_regime', 'payment_form', 'business_unit', 'position__department')
    search_fields = ('id', 'user__username', 'user__first_name', 'user__last_name', 'tax_id')
    autocomplete_fields = ['user', 'position', 'manager', 'business_unit']
    ordering = ('id',)