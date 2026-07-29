from django.contrib import admin
from .models import Department, Position, Employee, Skill, PositionSkill, BusinessUnit

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
