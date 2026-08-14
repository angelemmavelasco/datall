from datetime import date

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages

from .services.positions import PositionsStats, PositionsService, SkillsService, PositionNotFound, ServiceError, PermissionsError
from .services.departments import DepartmentsService, DepartmentsStats, ServiceError, PermissionsError, DepartmentNotFound
from .services.monitoring import MonitoringFormsService, MonitoringSubmissionService, FormNotFound
from .forms import (
    DepartmentForm,
    PositionForm,
    PositionSkillFormSet,
    PositionKPIFormSet,
    SkillForm,
    MonitoringFormForm,
    MonitoringFormScheduleForm,
    MonitoringFormQuestionFormSet,
    MonitoringFormFieldForm
)
from .filters import DepartmentFilter, PositionFilter, MonitoringFormFilter, MonitoringFormFieldFilter, MonitoringSubmissionFilter

'''departments'''
@login_required
def department_list_view(request):
    '''list of registered department and general kpis'''
    template = 'human_resources/departments/department_list.html'
    service = DepartmentsService(user=request.user)
    stats_service = DepartmentsStats(departments_service=service)

    available_actions = None
    if service.has_full_access:
        available_actions = 'human_resources/departments/partials/department_list__actions.html'

    departments = service.read_departments()
    
    department_filter = DepartmentFilter(request.GET, queryset=departments)
    departments = department_filter.qs
    
    kpis = stats_service.stats(qs=departments)
    context = {
        'departments': departments,
        'kpis': kpis,
        'available_actions': available_actions,
        'filter': department_filter,
    }
    return render(request, template, context)

@login_required
def department_detail_view(request, pk: str):
    '''details of a selected department'''
    template = 'human_resources/departments/department_detail.html'
    department_service = DepartmentsService(user=request.user)

    department = department_service.read_department(pk=pk)
    # stats breakdown
    positions = department_service.read_department_positions(department)
    active_employees = department_service.read_department_employees(department, active=True)
    inactive_employees = department_service.read_department_employees(department, active=False)

    available_actions = None
    if department_service.has_full_access:
        available_actions = 'human_resources/departments/partials/department_detail__actions.html'

    context = {
        'department': department,
        'positions': positions,
        'active_employees': active_employees,
        'inactive_employees': inactive_employees,
        'available_actions': available_actions,
    }
    return render(request, template, context)

@login_required
def department_create_view(request):
    template = 'human_resources/departments/department_form.html'
    service = DepartmentsService(user=request.user)
    
    if not service.has_full_access:
        messages.error(request, 'No tienes permisos para crear departamentos.')
        return redirect('human_resources:department_list_view')

    if request.method == 'POST':
        form = DepartmentForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                new_department = service.create_department(**form.cleaned_data)
                messages.success(request, f'Departamento {new_department.name} creado correctamente.')
                next_url = request.GET.get('next') or request.POST.get('next')
                if next_url:
                    return redirect(next_url)
                return redirect('human_resources:department_detail_view', new_department.pk)

            except PermissionsError as e:
                messages.error(request, str(e))
                return redirect('human_resources:department_list_view')

            except ServiceError as e:
                messages.error(request, str(e))

            except Exception as e:
                messages.error(request, f"Ocurrió un error inesperado al crear: {str(e)}")
        else:
            messages.error(request, 'Por favor revisa los errores en el formulario.')
    else:
        form = DepartmentForm()

    context = {
        'form': form,
        'can_update_access': service.has_full_access
    }
    return render(request, template, context)

@login_required
def department_update_view(request, pk: str):
    template = 'human_resources/departments/department_form.html'
    department_service = DepartmentsService(user=request.user)

    if not department_service.has_full_access:
        messages.error(request, 'No tienes permisos para actualizar departamentos.')
        return redirect('human_resources:department_list_view')

    try:
        department_instance = department_service.read_department(pk=pk)
    except DepartmentNotFound:
        messages.error(request, "El departamento solicitado no existe.")
        return redirect('human_resources:department_list_view')
    except PermissionsError:
        messages.error(request, "No tienes permisos para actualizar este departamento.")
        return redirect('human_resources:department_list_view')
    except ServiceError as e:
        messages.error(request, str(e))
        return redirect('human_resources:department_list_view')

    if request.method == 'POST':
        form = DepartmentForm(request.POST, request.FILES, instance=department_instance)
        if form.is_valid():
            try:
                updated_department = department_service.update_department(pk=pk, **form.cleaned_data)
                messages.success(request, "Departamento actualizado correctamente.")
                return redirect('human_resources:department_detail_view', updated_department.pk)
            except (PermissionsError, DepartmentNotFound) as e:
                messages.error(request, str(e))
                return redirect('human_resources:department_list_view')
            except ServiceError as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, str(e))
        else:
            messages.error(request, 'Por favor revisa los errores en el formulario.')
    else:
        form = DepartmentForm(instance=department_instance)

    context = {
        'form': form,
        'updating': department_instance
    }

    return render(request, template, context)

'''positions'''
@login_required
def position_list_view(request):
    '''general list of the registered positions'''
    template = 'human_resources/positions/position_list.html'
    position_service = PositionsService(user=request.user)
    kpis_service = PositionsStats(position_service=position_service)

    available_actions = None
    if position_service.has_full_access:
        available_actions = 'human_resources/positions/partials/position_list__actions.html'

    positions = position_service.read_positions()
    
    position_filter = PositionFilter(request.GET, queryset=positions)
    positions = position_filter.qs
    
    kpis = kpis_service.stats(qs=positions)

    context = {
        'available_actions': available_actions,
        'positions': positions,
        'kpis': kpis,
        'filter': position_filter,
    }
    return render(request, template, context)

@login_required
def position_detail_view(request, pk: str):
    '''position and profile details'''
    template = 'human_resources/positions/position_detail.html'
    position_service = PositionsService(user=request.user)

    available_actions = None
    if position_service.has_full_access:
        available_actions = 'human_resources/positions/partials/position_detail__actions.html'

    position = position_service.read_position(pk=pk)
    active_employees = position_service.read_position_employees(position)
    skills = position_service.read_position_skills(position)
    context = {
        'position': position,
        'available_actions': available_actions,
        'active_employees': active_employees,
        'skills': skills,
    }
    return render(request, template, context)

@login_required
def position_create_view(request):
    template = 'human_resources/positions/position_form.html'
    service = PositionsService(user=request.user)
    
    if not service.has_full_access:
        messages.error(request, 'No tienes permisos para crear posiciones.')
        return redirect('human_resources:position_list_view')

    if request.method == 'POST':
        form = PositionForm(request.POST, request.FILES)
        skills_formset = PositionSkillFormSet(request.POST, request.FILES, prefix='skills')
        kpis_formset = PositionKPIFormSet(request.POST, request.FILES, prefix='kpis')
        
        if form.is_valid() and skills_formset.is_valid() and kpis_formset.is_valid():
            try:
                skills_data = [f.cleaned_data for f in skills_formset if f.cleaned_data]
                kpis_data = [f.cleaned_data for f in kpis_formset if f.cleaned_data]

                new_position = service.create_position(
                    position_data=form.cleaned_data,
                    skills_data=skills_data,
                    kpis_data=kpis_data
                )
                messages.success(request, f'Posición {new_position.name} creada correctamente.')
                return redirect('human_resources:position_detail_view', new_position.pk)

            except PermissionsError as e:
                messages.error(request, str(e))
                return redirect('human_resources:position_list_view')

            except ServiceError as e:
                messages.error(request, str(e))

            except Exception as e:
                messages.error(request, f"Ocurrió un error inesperado al crear: {str(e)}")
        else:
            messages.error(request, 'Por favor revisa los errores en el formulario.')
    else:
        form = PositionForm()
        skills_formset = PositionSkillFormSet(prefix='skills')
        kpis_formset = PositionKPIFormSet(prefix='kpis')

    context = {
        'form': form,
        'skills_formset': skills_formset,
        'kpis_formset': kpis_formset,
        'can_update_access': service.has_full_access
    }
    return render(request, template, context)

@login_required
def position_update_view(request, pk: str):
    template = 'human_resources/positions/position_form.html'
    service = PositionsService(user=request.user)
    
    if not service.has_full_access:
        messages.error(request, 'No tienes permisos para actualizar posiciones.')
        return redirect('human_resources:position_list_view')

    try:
        position = service.read_position(pk=pk)
    except PositionNotFound:
        messages.error(request, 'Posición no encontrada.')
        return redirect('human_resources:position_list_view')

    if request.method == 'POST':
        form = PositionForm(request.POST, request.FILES, instance=position)
        skills_formset = PositionSkillFormSet(request.POST, request.FILES, instance=position, prefix='skills')
        kpis_formset = PositionKPIFormSet(request.POST, request.FILES, instance=position, prefix='kpis')
        
        if form.is_valid() and skills_formset.is_valid() and kpis_formset.is_valid():
            try:
                skills_data = [f.cleaned_data for f in skills_formset if f.cleaned_data]
                kpis_data = [f.cleaned_data for f in kpis_formset if f.cleaned_data]

                updated_position = service.update_position(
                    position=position,
                    position_data=form.cleaned_data,
                    skills_data=skills_data,
                    kpis_data=kpis_data
                )
                messages.success(request, f'Posición {updated_position.name} actualizada correctamente.')
                return redirect('human_resources:position_detail_view', updated_position.pk)

            except PermissionsError as e:
                messages.error(request, str(e))
                return redirect('human_resources:position_list_view')

            except ServiceError as e:
                messages.error(request, str(e))

            except Exception as e:
                messages.error(request, f"Ocurrió un error inesperado al actualizar: {str(e)}")
        else:
            messages.error(request, 'Por favor revisa los errores en el formulario.')
    else:
        form = PositionForm(instance=position)
        skills_formset = PositionSkillFormSet(instance=position, prefix='skills')
        kpis_formset = PositionKPIFormSet(instance=position, prefix='kpis')

    context = {
        'form': form,
        'skills_formset': skills_formset,
        'kpis_formset': kpis_formset,
        'can_update_access': service.has_full_access,
        'updating': True,
        'position': position
    }
    return render(request, template, context)

'''position skills'''
@login_required
def position_skill_list_view(request):
    '''this view is only available at position list view, and only full access can access to that'''
    template = 'human_resources/skills/skill_list.html'
    skill_service = SkillsService(user=request.user)

    available_actions = None
    if skill_service.has_full_access:
        available_actions = 'human_resources/skills/partials/skill_list__actions.html'

    skills = skill_service.read_skills()
    
    from .filters import SkillFilter
    skill_filter = SkillFilter(request.GET, queryset=skills, request=request)
    skills = skill_filter.qs

    available_actions = None
    if skill_service.has_full_access:
        available_actions = 'human_resources/skills/partials/skill_list__actions.html'

    context = {
        'skills': skills,
        'filter': skill_filter,
        'available_actions': available_actions,
    }

    return render(request, template, context)

@login_required
def position_skill_detail_view(request, pk: int):
    template = 'human_resources/skills/skill_detail.html'
    skill_service = SkillsService(user=request.user)
    skill = skill_service.read_skill(pk=pk)

    available_actions = None
    if skill_service.has_full_access:
        available_actions = 'human_resources/skills/partials/skill_detail__actions.html'

    context = {
        'skill': skill,
        'available_actions': available_actions,
    }
    return render(request, template, context)

@login_required
def position_skill_create_view(request):
    template = 'human_resources/skills/skill_form.html'
    service = SkillsService(user=request.user)
    
    if not service.has_full_access:
        messages.error(request, 'No tienes permisos para crear habilidades.')
        return redirect('human_resources:position_skill_list_view')

    if request.method == 'POST':
        form = SkillForm(request.POST)
        if form.is_valid():
            try:
                new_skill = service.create_skill(skill_data=form.cleaned_data)
                messages.success(request, f'Habilidad "{new_skill.name}" creada correctamente.')
                
                next_url = request.GET.get('next') or request.POST.get('next')
                if next_url:
                    return redirect(next_url)
                return redirect('human_resources:position_skill_list_view')

            except PermissionsError as e:
                messages.error(request, str(e))
                return redirect('human_resources:position_skill_list_view')

            except ServiceError as e:
                messages.error(request, str(e))

            except Exception as e:
                messages.error(request, f"Ocurrió un error inesperado al crear: {str(e)}")
        else:
            messages.error(request, 'Por favor revisa los errores en el formulario.')
    else:
        form = SkillForm()

    context = {
        'form': form,
        'can_update_access': service.has_full_access,
        'updating': False
    }
    return render(request, template, context)

@login_required
def position_skill_update_view(request, pk: int):
    template = 'human_resources/skills/skill_form.html'
    service = SkillsService(user=request.user)
    
    if not service.has_full_access:
        messages.error(request, 'No tienes permisos para actualizar habilidades.')
        return redirect('human_resources:position_skill_list_view')

    skill = service.read_skill(pk=pk)
    if not skill:
        messages.error(request, 'Habilidad no encontrada.')
        return redirect('human_resources:position_skill_list_view')

    if request.method == 'POST':
        form = SkillForm(request.POST, instance=skill)
        
        if form.is_valid():
            try:
                updated_skill = service.update_skill(
                    skill=skill,
                    skill_data=form.cleaned_data
                )
                messages.success(request, f'Habilidad "{updated_skill.name}" actualizada correctamente.')
                
                next_url = request.GET.get('next') or request.POST.get('next')
                if next_url:
                    return redirect(next_url)
                return redirect('human_resources:position_skill_detail_view', updated_skill.pk)

            except PermissionsError as e:
                messages.error(request, str(e))
                return redirect('human_resources:position_skill_list_view')

            except ServiceError as e:
                messages.error(request, str(e))

            except Exception as e:
                messages.error(request, f"Ocurrió un error inesperado al actualizar: {str(e)}")
        else:
            messages.error(request, 'Por favor revisa los errores en el formulario.')
    else:
        form = SkillForm(instance=skill)

    context = {
        'form': form,
        'can_update_access': service.has_full_access,
        'updating': True,
        'skill': skill
    }
    return render(request, template, context)

'''monitoring forms'''
@login_required
def monitoring_form_list_view(request):
    '''list of the available form to send a performance report (owned and others)'''
    template = 'human_resources/monitoring_forms/monitoring_form_list.html'
    monitoring_service = MonitoringFormsService(user=request.user)
    
    forms = monitoring_service.read_forms()
    
    form_filter = MonitoringFormFilter(request.GET, queryset=forms, request=request)
    forms = form_filter.qs

    available_actions = None
    if monitoring_service.has_full_access:
        available_actions = 'human_resources/monitoring_forms/partials/monitoring_form_list__actions.html'
    
    context = {
        'forms': forms,
        'filter': form_filter,
        'has_full_access': monitoring_service.has_full_access,
        'available_actions': available_actions,
    }
    return render(request, template, context)

@login_required
def monitoring_form_detail_view(request, pk: str):
    template = 'human_resources/monitoring_forms/monitoring_form_detail.html'
    service = MonitoringFormsService(user=request.user)
    
    try:
        form = service.read_form(pk=pk)
    except FormNotFound:
        messages.error(request, 'Formulario no encontrado.')
        return redirect('human_resources:monitoring_form_list_view')
    except PermissionsError as e:
        messages.error(request, str(e))
        return redirect('human_resources:monitoring_form_list_view')

    available_actions = None
    if service.has_full_access:
        available_actions = 'human_resources/monitoring_forms/partials/monitoring_form_detail__actions.html'
        
    context = {
        'monitoring_form': form,
        'has_full_access': service.has_full_access,
        'questions': service.read_questions(form),
        'available_actions': available_actions,
    }
    return render(request, template, context)

@login_required
def monitoring_form_create_view(request):
    template = 'human_resources/monitoring_forms/monitoring_form_form.html'
    service = MonitoringFormsService(user=request.user)
    
    if not service.has_full_access:
        messages.error(request, 'No tienes permisos para crear reportes de desempeño.')
        return redirect('human_resources:monitoring_form_list_view')

    if request.method == 'POST':
        form = MonitoringFormForm(request.POST)
        schedule_form = MonitoringFormScheduleForm(request.POST, prefix='schedule')
        questions_formset = MonitoringFormQuestionFormSet(request.POST, prefix='questions')
        
        if form.is_valid() and schedule_form.is_valid() and questions_formset.is_valid():
            try:
                questions_data = [f.cleaned_data for f in questions_formset if f.cleaned_data]

                new_form = service.create_form(
                    form_data=form.cleaned_data,
                    schedule_data=schedule_form.cleaned_data,
                    questions_data=questions_data
                )
                messages.success(request, f'Formulario {new_form.name} creado correctamente.')
                return redirect('human_resources:monitoring_form_detail_view', new_form.pk)

            except PermissionsError as e:
                messages.error(request, str(e))
                return redirect('human_resources:monitoring_form_list_view')

            except ServiceError as e:
                messages.error(request, str(e))

            except Exception as e:
                messages.error(request, f"Ocurrió un error inesperado al crear: {str(e)}")
        else:
            messages.error(request, 'Por favor revisa los errores en el formulario.')
    else:
        form = MonitoringFormForm()
        schedule_form = MonitoringFormScheduleForm(prefix='schedule')
        questions_formset = MonitoringFormQuestionFormSet(prefix='questions')

    context = {
        'form': form,
        'schedule_form': schedule_form,
        'questions_formset': questions_formset,
        'can_update_access': service.has_full_access
    }
    return render(request, template, context)

@login_required
def monitoring_form_update_view(request, pk: str):
    template = 'human_resources/monitoring_forms/monitoring_form_form.html'
    service = MonitoringFormsService(user=request.user)
    
    if not service.has_full_access:
        messages.error(request, 'No tienes permisos para actualizar reportes de desempeño.')
        return redirect('human_resources:monitoring_form_list_view')

    try:
        monitoring_form = service.read_form(pk=pk)
    except FormNotFound:
        messages.error(request, 'Formulario no encontrado.')
        return redirect('human_resources:monitoring_form_list_view')
    except PermissionsError as e:
        messages.error(request, str(e))
        return redirect('human_resources:monitoring_form_list_view')

    if request.method == 'POST':
        form = MonitoringFormForm(request.POST, instance=monitoring_form)
        schedule_form = MonitoringFormScheduleForm(
            request.POST, 
            instance=getattr(monitoring_form, 'schedule', None), 
            prefix='schedule'
        )
        questions_formset = MonitoringFormQuestionFormSet(
            request.POST, 
            instance=monitoring_form, 
            prefix='questions'
        )
        
        if form.is_valid() and schedule_form.is_valid() and questions_formset.is_valid():
            try:
                questions_data = [f.cleaned_data for f in questions_formset if f.cleaned_data]

                updated_form = service.update_form(
                    form=monitoring_form,
                    form_data=form.cleaned_data,
                    schedule_data=schedule_form.cleaned_data,
                    questions_data=questions_data
                )
                messages.success(request, f'Formulario {updated_form.name} actualizado correctamente.')
                return redirect('human_resources:monitoring_form_detail_view', updated_form.pk)

            except PermissionsError as e:
                messages.error(request, str(e))
                return redirect('human_resources:monitoring_form_list_view')

            except ServiceError as e:
                messages.error(request, str(e))

            except Exception as e:
                messages.error(request, f"Ocurrió un error inesperado al actualizar: {str(e)}")
        else:
            messages.error(request, 'Por favor revisa los errores en el formulario.')
    else:
        form = MonitoringFormForm(instance=monitoring_form)
        schedule_form = MonitoringFormScheduleForm(
            instance=getattr(monitoring_form, 'schedule', None), 
            prefix='schedule'
        )
        questions_formset = MonitoringFormQuestionFormSet(
            instance=monitoring_form, 
            prefix='questions'
        )

    context = {
        'form': form,
        'schedule_form': schedule_form,
        'questions_formset': questions_formset,
        'can_update_access': service.has_full_access,
        'updating': True,
        'monitoring_form': monitoring_form
    }
    return render(request, template, context)

'''monitoring form fields'''
@login_required
def monitoring_form_field_list_view(request):
    '''list of a catalog of fields and questions that can be used in monitoring forms'''
    template = 'human_resources/monitoring_form_fields/monitoring_form_field_list.html'
    monitoring_service = MonitoringFormsService(user=request.user)

    if not monitoring_service.has_full_access:
        messages.error(request, 'No tienes permisos para acceder al listado de campos y preguntas.')
        return redirect('human_resources:monitoring_form_list_view')
    
    try:
        fields = monitoring_service.read_fields()
    except PermissionsError as e:
        messages.error(request, str(e))
        return redirect('human_resources:monitoring_form_list_view')

    field_filter = MonitoringFormFieldFilter(request.GET, queryset=fields, request=request)
    fields = field_filter.qs

    available_actions = None
    if monitoring_service.has_full_access:
        available_actions = 'human_resources/monitoring_form_fields/partials/monitoring_form_field_list__actions.html'

    context = {
        'fields': fields,
        'filter': field_filter,
        'has_full_access': monitoring_service.has_full_access,
        'available_actions': available_actions,
    }
    return render(request, template, context)

@login_required
def monitoring_form_field_detail_view(request, pk: int):
    template = 'human_resources/monitoring_form_fields/monitoring_form_field_detail.html'
    service = MonitoringFormsService(user=request.user)

    if not service.has_full_access:
        messages.error(request, 'No tienes permisos para acceder al listado de campos y preguntas.')
        return render(request, settings.ACCESS_DENIED)

    try:
        field = service.read_field(pk=pk)
    except FormNotFound as e:
        messages.error(request, str(e))
        return redirect('human_resources:monitoring_form_field_list_view')
    except PermissionsError as e:
        messages.error(request, str(e))
        return redirect('human_resources:monitoring_form_field_list_view')

    form_questions = field.form_questions.select_related('form', 'position').all()

    context = {
        'field': field,
        'form_questions': form_questions,
        'has_full_access': service.has_full_access,
    }
    return render(request, template, context)

@login_required
def monitoring_form_field_create_view(request):
    template = 'human_resources/monitoring_form_fields/monitoring_form_field_form.html'
    service = MonitoringFormsService(user=request.user)

    if not service.has_full_access:
        messages.error(request, 'No tienes permisos para crear campos de reportes.')
        return render(request, settings.ACCESS_DENIED)

    if request.method == 'POST':
        form = MonitoringFormFieldForm(request.POST)
        if form.is_valid():
            try:
                new_field = service.create_field(form.cleaned_data)
                messages.success(request, f'Campo "{new_field.label}" creado exitosamente.')
                return redirect('human_resources:monitoring_form_field_detail_view', new_field.pk)
            except ServiceError as e:
                messages.error(request, str(e))
            except PermissionsError as e:
                messages.error(request, str(e))
                return redirect('human_resources:monitoring_form_field_list_view')
            except Exception as e:
                messages.error(request, f"Ocurrió un error inesperado al crear: {str(e)}")
        else:
            messages.error(request, 'Por favor revisa los errores en el formulario.')
    else:
        form = MonitoringFormFieldForm()

    context = {
        'form': form,
        'updating': False,
    }
    return render(request, template, context)

@login_required
def monitoring_form_field_update_view(request, pk: int):
    template = 'human_resources/monitoring_form_fields/monitoring_form_field_form.html'
    service = MonitoringFormsService(user=request.user)

    if not service.has_full_access:
        messages.error(request, 'No tienes permisos para actualizar campos de reportes.')
        return render(request, settings.ACCESS_DENIED)

    try:
        field = service.read_field(pk=pk)
    except FormNotFound as e:
        messages.error(request, str(e))
        return redirect('human_resources:monitoring_form_field_list_view')
    except PermissionsError as e:
        messages.error(request, str(e))
        return redirect('human_resources:monitoring_form_field_list_view')

    if request.method == 'POST':
        form = MonitoringFormFieldForm(request.POST, instance=field)
        if form.is_valid():
            try:
                updated_field = service.update_field(field, form.cleaned_data)
                messages.success(request, f'Campo "{updated_field.label}" actualizado exitosamente.')
                return redirect('human_resources:monitoring_form_field_detail_view', updated_field.pk)
            except ServiceError as e:
                messages.error(request, str(e))
            except PermissionsError as e:
                messages.error(request, str(e))
                return redirect('human_resources:monitoring_form_field_list_view')
            except Exception as e:
                messages.error(request, f"Ocurrió un error inesperado al actualizar: {str(e)}")
        else:
            messages.error(request, 'Por favor revisa los errores en el formulario.')
    else:
        form = MonitoringFormFieldForm(instance=field)

    context = {
        'form': form,
        'updating': True,
        'field': field,
    }
    return render(request, template, context)

'''monitoring form submissions'''
@login_required
def monitoring_form_submission_list_view(request):
    '''submissions made by the employees'''
    template = 'human_resources/monitoring_submissions/monitoring_submission_list.html'
    
    service = MonitoringSubmissionService(user=request.user)
    periods = service.read_periods()
    
    period_filter = MonitoringSubmissionFilter(request.GET, queryset=periods, request=request)
    filtered_periods = period_filter.qs
    
    expected_submissions = service.read_submissions(filtered_periods)
    employee_q = request.GET.getlist('employee')
    position_q = request.GET.getlist('position')
    department_q = request.GET.getlist('department')
    hierarchy_q = request.GET.getlist('hierarchy_level')
    status_q = request.GET.getlist('status')
    
    filtered_submissions = []
    for es in expected_submissions:
        if employee_q and str(es.employee.id) not in employee_q:
            continue
            
        if position_q and str(es.employee.position.id) not in position_q:
            continue
            
        if department_q and str(es.employee.position.department.id) not in department_q:
            continue
            
        if hierarchy_q and es.employee.position.hierarchy_level not in hierarchy_q:
            continue
                
        if status_q and es.status_code not in status_q:
            continue
            
        filtered_submissions.append(es)
        
    kpis = service.stats(filtered_submissions)

    available_actions = None
    if service.has_full_access:
        available_actions = 'human_resources/monitoring_submissions/partials/monitoring_submission_list__actions.html'
    
    context = {
        'expected_submissions': filtered_submissions,
        'kpis': kpis,
        'filter': period_filter,
        'available_actions': available_actions,
        'selected_statuses': status_q,
    }
    return render(request, template, context)

@login_required
def monitoring_form_submission_detail_view(request, pk: int):
    template = 'human_resources/monitoring_submissions/monitoring_submission_detail.html'
    service = MonitoringSubmissionService(user=request.user)
    
    employee_id = request.GET.get('employee')
    try:
        submission = service.read_submission(pk=pk, employee_id=employee_id)
    except Exception as e:
        messages.error(request, str(e))
        return redirect('human_resources:monitoring_form_submission_list_view')
        
    context = {
        'submission': submission,
    }
    return render(request, template, context)

@login_required
def monitoring_form_submission_create_view(request):
    pass

@login_required
def monitoring_form_submission_update_view(request, pk: int):
    pass

'''business units'''
@login_required
def business_unit_list_view(request):
    '''list of the registered business units (warehouses before)'''
    pass

@login_required
def business_unit_detail_view(request, pk: str):
    pass

@login_required
def business_unit_create_view(request):
    pass

@login_required
def business_unit_update_view(request, pk: str):
    pass

'''employees'''
@login_required
def employee_list_view(request):
    pass

@login_required
def employee_detail_view(request, pk: str):
    pass

@login_required
def employee_create_view(request):
    pass

@login_required
def employee_update_view(request, pk: str):
    pass