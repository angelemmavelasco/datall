from django.contrib import admin
from .models import (
    Department,
    Position,
    PositionKPI,
    Skill,
    PositionSkill,
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