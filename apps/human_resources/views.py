from datetime import date

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages
from .services.departments import DepartmentsService, DepartmentsStats, ServiceError, PermissionsError, DepartmentNotFound
from .forms import DepartmentForm

'''departments'''
@login_required
def department_list_view(request):
    '''list of registered department and general kpis'''
    template = 'human_resources/departments/department_list.html'
    service = DepartmentsService(user=request.user)
    stats_service = DepartmentsStats(departments_service=service)

    departments = service.read_departments()
    kpis = stats_service.stats(qs=departments)
    context = {
        'departments': departments,
        'kpis': kpis,
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
    pass

@login_required
def position_detail_view(request, pk: str):
    '''position and profile details'''
    pass

@login_required
def position_create_view(request):
    pass

@login_required
def position_update_view(request, pk: str):
    pass

'''position skills'''
@login_required
def position_skill_list_view(request):
    '''this view is only available at position list view, and only full access can access to that'''
    pass

@login_required
def position_skill_detail_view(request, pk: int):
    pass

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