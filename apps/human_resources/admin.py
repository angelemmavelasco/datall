from django.contrib import admin
from .models import (
    Department, Position, Employee, Skill, PositionSkill, BusinessUnit,
    MonitoringForm, MonitoringFormField, MonitoringFormQuestion,
    MonitoringFormSubmission, MonitoringFormAnswer
)

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'description')
    search_fields = ('id', 'name', 'description')

class PositionSkillInline(admin.TabularInline):
    model = PositionSkill
    extra = 1

@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'department', 'hierarchy_level')
    search_fields = ('id', 'name', 'description')
    list_filter = ('department', 'hierarchy_level')
    inlines = [PositionSkillInline]

@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ('name', 'skill_type', 'description')
    search_fields = ('name', 'description')
    list_filter = ('skill_type',)

@admin.register(PositionSkill)
class PositionSkillAdmin(admin.ModelAdmin):
    list_display = ('position', 'skill', 'requirement_level', 'skill_level')
    search_fields = ('position__name', 'skill__name')
    list_filter = ('requirement_level', 'skill_level')

@admin.register(BusinessUnit)
class BusinessUnitAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'parent', 'manager')
    search_fields = ('id', 'name', 'manager__user__first_name', 'manager__user__last_name')
    list_filter = ('parent',)

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'position', 'manager', 'business_unit', 'hire_date', 'termination_date', 'contract_type')
    search_fields = ('id', 'user__username', 'user__first_name', 'user__last_name', 'position__name')
    list_filter = ('contract_type', 'position__department', 'business_unit', 'payroll_frequency')

class MonitoringFormQuestionInline(admin.TabularInline):
    model = MonitoringFormQuestion
    extra = 1

@admin.register(MonitoringForm)
class MonitoringFormAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'version', 'periodicity', 'is_active')
    list_filter = ('periodicity', 'is_active')
    search_fields = ('id', 'name')
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

class MonitoringFormAnswerInline(admin.TabularInline):
    model = MonitoringFormAnswer
    extra = 0
    readonly_fields = ('question', 'value')

@admin.register(MonitoringFormSubmission)
class MonitoringFormSubmissionAdmin(admin.ModelAdmin):
    list_display = ('id', 'employee', 'form', 'period_identifier', 'status', 'submitted_at')
    list_filter = ('form', 'status', 'period_identifier')
    search_fields = ('employee__user__first_name', 'employee__user__last_name', 'period_identifier')
    inlines = [MonitoringFormAnswerInline]

@admin.register(MonitoringFormAnswer)
class MonitoringFormAnswerAdmin(admin.ModelAdmin):
    list_display = ('submission', 'question', 'value')
    search_fields = ('submission__employee__user__first_name', 'question__question__label')
