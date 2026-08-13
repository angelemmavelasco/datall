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
    MonitoringFormSchedule,
    MonitoringPeriod,
)
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta, datetime
from django.utils.timezone import make_aware
from apps.core.models import PeriodicityChoices

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


class MonitoringFormScheduleInline(admin.StackedInline):
    model = MonitoringFormSchedule
    extra = 0
    can_delete = False

class MonitoringPeriodInline(admin.TabularInline):
    model = MonitoringPeriod
    extra = 0
    fields = ('identifier', 'start_date', 'end_date', 'is_active')

import calendar

def get_target_date_for_month(base_date, open_day, week_of_month):
    if week_of_month == 'every':
        days_ahead = open_day - base_date.weekday()
        if days_ahead < 0:
            days_ahead += 7
        return base_date + timedelta(days=days_ahead)
        
    year, month = base_date.year, base_date.month
    cal = calendar.monthcalendar(year, month)
    
    matching_days = [week[open_day] for week in cal if week[open_day] != 0]
    
    if week_of_month == 'first':
        day = matching_days[0]
    elif week_of_month == 'second':
        day = matching_days[1] if len(matching_days) > 1 else matching_days[-1]
    elif week_of_month == 'third':
        day = matching_days[2] if len(matching_days) > 2 else matching_days[-1]
    elif week_of_month == 'fourth':
        day = matching_days[3] if len(matching_days) > 3 else matching_days[-1]
    else: # 'last'
        day = matching_days[-1]
        
    return base_date.replace(day=day)

@admin.action(description="Generar siguientes 4 periodos (Schedules)")
def generate_next_periods(modeladmin, request, queryset):
    for form in queryset:
        if not hasattr(form, 'schedule'):
            messages.warning(request, f"El formulario {form.name} no tiene programación (schedule).")
            continue
            
        schedule = form.schedule
        delta = PeriodicityChoices(form.periodicity).get_relativedelta()
        
        last_period = form.periods.order_by('-start_date').first()
        if last_period:
            base_date = last_period.start_date.date()
            if 'm' in str(form.periodicity):
                anchor_date = (base_date + delta).replace(day=15)
            else:
                anchor_date = base_date + delta
            current_anchor = anchor_date
        else:
            today = timezone.now().date()
            if 'm' in str(form.periodicity):
                current_anchor = today.replace(day=15)
            else:
                current_anchor = today
        
        periods_created = 0

        for i in range(4):
            adjusted_date = get_target_date_for_month(current_anchor, schedule.open_day, schedule.week_of_month)
            
            start_dt = make_aware(datetime.combine(adjusted_date, schedule.open_time))
            end_dt = start_dt + timedelta(hours=schedule.duration_hours)
            
            if 'w' in str(form.periodicity) or 'd' in str(form.periodicity):
                year, week, _ = adjusted_date.isocalendar()
                identifier = f"{year}-W{week:02d}"
            else:
                identifier = f"{adjusted_date.year}-{adjusted_date.month:02d}"
                
            period, created = MonitoringPeriod.objects.get_or_create(
                form=form,
                identifier=identifier,
                defaults={
                    'start_date': start_dt,
                    'end_date': end_dt,
                    'is_active': True
                }
            )
            
            if created:
                periods_created += 1
                
            current_anchor += delta

        messages.success(request, f"Se generaron {periods_created} nuevos periodos para {form.name}.")


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
    inlines = [MonitoringFormScheduleInline, MonitoringPeriodInline, MonitoringFormQuestionInline]
    actions = [generate_next_periods]

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
    list_display = ('employee', 'form', 'period', 'submitted_at', 'status')
    list_filter = ('status', 'form', 'period__identifier')
    search_fields = ('employee__id', 'employee__user__first_name', 'employee__user__last_name', 'period__identifier')
    autocomplete_fields = ['employee', 'form', 'period']
    inlines = [MonitoringFormAnswerInline]
    ordering = ('-submitted_at',)

@admin.register(MonitoringPeriod)
class MonitoringPeriodAdmin(admin.ModelAdmin):
    list_display = ('identifier', 'form', 'start_date', 'end_date', 'is_active')
    list_filter = ('is_active', 'form')
    search_fields = ('identifier', 'form__name')
    ordering = ('-start_date',)

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