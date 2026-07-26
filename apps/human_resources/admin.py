from django.contrib import admin
from .models import Department, Position, Employee, Skill, PositionSkill

class PositionSkillInline(admin.TabularInline):
    model = PositionSkill
    extra = 1
    min_num = 1

@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'department')
    search_fields = ('id', 'name', 'description')
    list_filter = ('department',)
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

admin.site.register(Department)
admin.site.register(Employee)
