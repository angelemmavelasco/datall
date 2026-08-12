from datetime import date

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages

from .services.positions import PositionsStats, PositionsService, SkillsService
from .services.departments import DepartmentsService, DepartmentsStats, ServiceError, PermissionsError, DepartmentNotFound
from .forms import DepartmentForm, PositionForm, PositionSkillFormSet, PositionKPIFormSet
from .filters import DepartmentFilter, PositionFilter

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
    pass

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

    available_actions = None
    if skill_service.has_full_access:
        available_actions = 'human_resources/skills/partials/skill_list__actions.html'

    context = {
        'skills': skills,
        'available_actions': available_actions,
    }

    return render(request, template, context)

@login_required
def position_skill_detail_view(request, pk: int):
    template = 'human_resources/skills/skill_detail.html'
    skill_service = SkillsService(user=request.user)
    skill = skill_service.read_skill(pk=pk)
    context = {
        'skill': skill,
    }
    return render(request, template, context)

@login_required
def position_skill_create_view(request):
    pass

@login_required
def position_skill_update_view(request, pk: int):
    pass

'''monitoring forms'''
@login_required
def monitoring_form_list_view(request):
    '''list of the available form to send a performance report (owned and others)'''
    pass

@login_required
def monitoring_form_detail_view(request, pk: str):
    pass

@login_required
def monitoring_form_create_view(request):
    pass

@login_required
def monitoring_form_update_view(request, pk: str):
    pass

'''monitoring form fields'''
@login_required
def monitoring_form_field_list_view(request):
    '''list of a catalog of fields and wuestion that can be used in monitoring forms'''
    pass

@login_required
def monitoring_form_field_detail_view(request, pk: int):
    pass

@login_required
def monitoring_form_field_create_view(request):
    pass

@login_required
def monitoring_form_field_update_view(request, pk: int):
    pass

'''monitoring form submissions'''
@login_required
def monitoring_form_submission_view(request):
    '''submissions made by the employees'''
    pass

@login_required
def monitoring_form_submission_detail_view(request, pk: int):
    pass

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