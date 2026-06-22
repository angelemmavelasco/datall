from django.shortcuts import render, redirect,get_object_or_404
from django.urls import reverse
from urllib.parse import urlencode
from django.http import JsonResponse

from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.contrib.auth import get_user_model

from apps.human_resources.services.employees import employees_crud
from apps.core.models import (
    Position, Warehouse, Employee, 
    PayrollType, Periodicity, TaxSystem,
    SystemModule, RouteCommissionSetup, CommissionProfile,
    SaleTarget, CommissionSettlement
    )
from apps.core.utils import get_allowed_routes_for_user

from apps.human_resources.services.comissions.comissions import Comissions, CommissionExceptions, CommissionsReport

User = get_user_model()

@login_required
def employees(request):
    TEMPLATE = 'human_resources/employees/employees.html'
    employees_service = employees_crud.EmployeesCRUD()
    
    search_query = request.GET.get('q', '').strip()
    
    users_qs = employees_service.get_employees(search_query=search_query)
    
    current_filters = {
        'q': search_query,
    }
    
    context = {
        'users': users_qs,
        'current_filters': current_filters,
    }
    
    return render(request, TEMPLATE, context)

@login_required
def employee(request, user_id: int = None):
    TEMPLATE = 'human_resources/employees/employee.html'
    employees_service = employees_crud.EmployeesCRUD()
    
    context = {}
    
    user_obj = employees_service.get_user_with_employee_history(user_id=user_id)
    
    if not user_obj:
        messages.error(request, 'El empleado no existe.')
        return redirect('human_resources:employees')
        
    context['user'] = user_obj
    context['employee_history'] = user_obj.employees.all()
    
    return render(request, TEMPLATE, context)

@login_required
def employee_create(request):
    TEMPLATE = 'human_resources/employees/employee_create.html'
    employees_service = employees_crud.EmployeesCRUD()
    
    # Data for select options
    all_users = User.objects.all().order_by('first_name', 'last_name')
    all_positions = Position.objects.all().order_by('name')
    all_warehouses = Warehouse.objects.all().order_by('name')
    all_managers = Employee.objects.filter(termination_date__isnull=True).select_related('user').order_by('user__first_name')
    all_payroll_types = PayrollType.objects.all()
    all_periodicities = Periodicity.objects.all()
    all_tax_systems = TaxSystem.objects.all()
    
    context = {
        'all_users': all_users,
        'all_positions': all_positions,
        'all_warehouses': all_warehouses,
        'all_managers': all_managers,
        'all_payroll_types': all_payroll_types,
        'all_periodicities': all_periodicities,
        'all_tax_systems': all_tax_systems,
    }
    
    if request.method == 'POST':
        raw_data = request.POST.dict()
        
        new_employee = employees_service.process_employee_create(raw_data=raw_data)
        
        if new_employee:
            messages.success(request, 'Posición asignada con éxito al empleado.')
            return redirect('human_resources:employee', user_id=new_employee.user_id)
        else:
            messages.error(request, 'Error al crear: Verifica que los campos obligatorios estén completos.')
            context['employee_data'] = raw_data
            return render(request, TEMPLATE, context)
            
    return render(request, TEMPLATE, context)

@login_required
def org_chart(request):
    TEMPLATE = 'human_resources/org_chart/org_chart.html'
    
    return render(request, TEMPLATE)

@login_required
def get_org_chart_data(request):
    employees_service = employees_crud.EmployeesCRUD()
    search_query = request.GET.get('q', '').strip()
    
    employees = employees_service.get_org_chart_employees(search_query=search_query)

    nodes = {}
    roots = []

    for emp in employees:
        emp_name = f"{emp.user.first_name} {emp.user.last_name}" if emp.user else "Sin asignar"
        position_name = emp.position.name if emp.position else "Sin posición"
        
        
        user_regions = list(emp.managed_regions.all())
        managed_region = user_regions[0] if user_regions else None

        if not emp.warehouse and not managed_region:
            location_display = "Corporativo"
        elif managed_region and not emp.warehouse:
            location_display = managed_region.name
        elif emp.warehouse and not managed_region:
            location_display = emp.warehouse.name
        else:
            location_display = f"{managed_region.name} | {emp.warehouse.name}"
        
        nodes[str(emp.id)] = {
            'name': emp_name.title(),
            'position': position_name.title(),
            'location': location_display.title(),
            'children': []
        }
    
    for emp in employees:
        emp_id_str = str(emp.id)
        if emp.manager_id:
            manager_id_str = str(emp.manager_id)
            if manager_id_str in nodes:
                nodes[manager_id_str]['children'].append(nodes[emp_id_str])
        else:
            roots.append(nodes[emp_id_str])

    chart_data = roots[0] if len(roots) == 1 else {'name': 'Organización', 'children': roots}
    
    return JsonResponse(chart_data)






@login_required
def commissions(request):
    user = request.user
    template = 'human_resources/payroll/commissions.html'
    module = SystemModule.objects.filter(url_name='human_resources:commissions').first()
    allowed_routes = get_allowed_routes_for_user(user).order_by('id')

    filters = {
        'q': request.GET.get('q', '').strip(),
        'status': request.GET.get('status', ''),
        'min_classes': request.GET.get('min_classes', '')
    }

    comissions_service = Comissions(allowed_routes=allowed_routes)
    profiles_data = comissions_service.commissions_read(filters)
    
    context = {
        'routes': allowed_routes,
        'profiles_data': profiles_data,
        'filters': filters, 
    }
    
    return render(request, template, context)


@login_required
def commission_profile_detail(request, cp_id: int):
    user = request.user
    template = 'human_resources/payroll/commission_profile_detail.html'
    allowed_routes = get_allowed_routes_for_user(user).order_by('id')
    profile = get_object_or_404(CommissionProfile, id=cp_id)
    
    if request.method == 'POST':
        profile_data = {
            'name': request.POST.get('name'),
            'description': request.POST.get('description', ''),
            'is_active': request.POST.get('is_active') == 'on'
        }

        #extract tiers
        scopes = request.POST.getlist('min_global_scope_pct[]')
        classes = request.POST.getlist('min_completed_classes[]')
        multipliers = request.POST.getlist('bonus_multiplier_pct[]')
        extras = request.POST.getlist('extra_flat_bonus[]')

        tiers_data = []
        for s, c, m, e in zip(scopes, classes, multipliers, extras):
            if s and m: 
                tiers_data.append({
                    'min_global_scope_pct': s,
                    'min_completed_classes': c,
                    'bonus_multiplier_pct': m,
                    'extra_flat_bonus': e or 0
                })

        #extract configurations
        configs_data = []
        i = 0
        while f'start_date_{i}' in request.POST:
            routes = request.POST.getlist(f'route_ids_{i}')
            if routes:
                configs_data.append({
                    'start_date': request.POST.get(f'start_date_{i}'),
                    'end_date': request.POST.get(f'end_date_{i}'),
                    'bonus_type': request.POST.get(f'bonus_type_{i}'),
                    'base_bonus_amount': request.POST.get(f'base_bonus_amount_{i}'),
                    'routes': routes
                })
            i += 1

        #security
        allowed_route_ids = set(allowed_routes.values_list('id', flat=True))
        all_submitted_routes = [r_id for config in configs_data for r_id in config['routes']]
        invalid_routes = [r_id for r_id in all_submitted_routes if r_id not in allowed_route_ids]
        
        if invalid_routes:
            messages.error(request, 'Error de seguridad: Intentaste asignar rutas sobre las cuales no tienes permiso.')
            return redirect('human_resources:commission_profile_detail', cp_id=profile.id)

        #service
        service = Comissions()
        try:
            service.commission_profile_update(profile.id, profile_data, tiers_data, configs_data)
            messages.success(request, 'El perfil de comisiones se actualizó correctamente.')
            return redirect('human_resources:commission_profile_detail', cp_id=profile.id)
        except ValueError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f'Ocurrió un error inesperado: {str(e)}')

    #group existing configurations to inject them into the template
    grouped_configs = {}
    for setup in profile.routecommissionsetup_set.all():
        key = (setup.start_date, setup.end_date, setup.bonus_type, setup.get_bonus_type_display(), setup.base_bonus_amount)
        if key not in grouped_configs:
            grouped_configs[key] = []
        grouped_configs[key].append(setup.route_id)
        
    configs_list = [
        {
            'start_date': k[0],
            'end_date': k[1],
            'bonus_type': k[2],
            'bonus_type_display': k[3],
            'base_bonus_amount': k[4],
            'route_ids': v
        } for k, v in grouped_configs.items()
    ]

    context = {
        'profile': profile,
        'routes': allowed_routes,
        'commission_types': RouteCommissionSetup.BONUS_CHOICES,
        'configs_list': configs_list,
    }
    
    return render(request, template, context)


@login_required
def commission_profile_create(request):
    user = request.user
    template = 'human_resources/payroll/commission_profile_create.html'
    allowed_routes = get_allowed_routes_for_user(user).order_by('id')
    
    if request.method == 'POST':
        #general info
        profile_data = {
            'name': request.POST.get('name'),
            'description': request.POST.get('description', ''),
            'is_active': request.POST.get('is_active') == 'on'
        }

        #tiers extraction
        scopes = request.POST.getlist('min_global_scope_pct[]')
        classes = request.POST.getlist('min_completed_classes[]')
        multipliers = request.POST.getlist('bonus_multiplier_pct[]')
        extras = request.POST.getlist('extra_flat_bonus[]')

        tiers_data = []
        for s, c, m, e in zip(scopes, classes, multipliers, extras):
            if s and m: # Ignorar vacíos
                tiers_data.append({
                    'min_global_scope_pct': s,
                    'min_completed_classes': c,
                    'bonus_multiplier_pct': m,
                    'extra_flat_bonus': e or 0
                })

        #multiple config extration
        configs_data = []
        i = 0
        while f'start_date_{i}' in request.POST:
            routes = request.POST.getlist(f'route_ids_{i}')
            if routes:
                configs_data.append({
                    'start_date': request.POST.get(f'start_date_{i}'),
                    'end_date': request.POST.get(f'end_date_{i}'),
                    'bonus_type': request.POST.get(f'bonus_type_{i}'),
                    'base_bonus_amount': request.POST.get(f'base_bonus_amount_{i}'),
                    'routes': routes
                })
            i += 1

        #allowed routes validation
        allowed_route_ids = set(allowed_routes.values_list('id', flat=True))
        all_submitted_routes = [r_id for config in configs_data for r_id in config['routes']]
        invalid_routes = [r_id for r_id in all_submitted_routes if r_id not in allowed_route_ids]
        
        if invalid_routes:
            messages.error(request, 'Error de seguridad: Intentaste asignar rutas sobre las cuales no tienes permiso.')
            return redirect('human_resources:commission_profile_create')

        service = Comissions()
        try:
            service.commission_profile_create(profile_data, tiers_data, configs_data)
            messages.success(request, 'El perfil de comisiones y sus asignaciones se guardaron correctamente.')
            return redirect('human_resources:commissions') 
        except ValueError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f'Ocurrió un error inesperado: {str(e)}')

    context = {
        'routes': allowed_routes,
        'commission_types': RouteCommissionSetup.BONUS_CHOICES,
    }
    
    return render(request, template, context)
    
    

@login_required
def commission_exceptions(request):
    user = request.user
    template = 'human_resources/payroll/commission_exceptions.html'
    module = SystemModule.objects.filter(url_name='human_resources:commissions').first()
    
    allowed_routes = get_allowed_routes_for_user(user).order_by('id')

    filters = {
        'q_route': request.GET.get('q_route', '').strip(),
        'q_employee': request.GET.get('q_employee', '').strip(),
        'start_date': request.GET.get('start_date', ''),
        'end_date': request.GET.get('end_date', ''),
        'min_pct': request.GET.get('min_pct', ''),
        'max_pct': request.GET.get('max_pct', ''),
        'min_amount': request.GET.get('min_amount', ''),
        'max_amount': request.GET.get('max_amount', '')
    }

    service = CommissionExceptions(allowed_routes=allowed_routes)
    exceptions = service.get_data(**filters)

    context = {
        'routes': allowed_routes,
        'exceptions': exceptions,
        'filters': filters,
    }
    
    return render(request, template, context)

@login_required
def commission_exception_create(request):
    user = request.user
    template = 'human_resources/payroll/commission_exception_create.html'
    allowed_routes = get_allowed_routes_for_user(user).order_by('id')

    if request.method == 'POST':
        route_ids = request.POST.getlist('route_ids')
        
        guaranteed_bonus = request.POST.get('guaranteed_flat_bonus')
        guaranteed_bonus = float(guaranteed_bonus) if guaranteed_bonus else None
        
        tolerance = request.POST.get('scope_tolerance_pct')
        tolerance = float(tolerance) if tolerance else 0.0

        exception_data = {
            'start_date': request.POST.get('start_date'),
            'end_date': request.POST.get('end_date'),
            'scope_tolerance_pct': tolerance,
            'guaranteed_flat_bonus': guaranteed_bonus,
            'notes': request.POST.get('notes', '').strip(),
        }

        service = CommissionExceptions(allowed_routes=allowed_routes)
        created_count = service.create_multiple(route_ids, exception_data)
        messages.success(request, f'Se registraron correctamente {created_count} excepciones.')
        return redirect('human_resources:commission_exceptions')

    context = {
        'routes': allowed_routes,
    }
    
    return render(request, template, context)
    
@login_required
def commission_exception_detail(request, ce_id):
    user = request.user
    template = 'human_resources/payroll/commission_exception_detail.html'
    allowed_routes = get_allowed_routes_for_user(user).order_by('id')

    service = CommissionExceptions(allowed_routes=allowed_routes)

    try:
        exception = service.get_data().get(id=ce_id)
    except RouteCommissionException.DoesNotExist:
        messages.error(request, "La excepción no existe o no tienes permisos para verla.")
        return redirect('human_resources:commission_exceptions')

    if request.method == 'POST':
        guaranteed_bonus = request.POST.get('guaranteed_flat_bonus')
        guaranteed_bonus = float(guaranteed_bonus) if guaranteed_bonus else None
        
        tolerance = request.POST.get('scope_tolerance_pct')
        tolerance = float(tolerance) if tolerance else 0.0

        update_data = {
            'start_date': request.POST.get('start_date'),
            'end_date': request.POST.get('end_date'),
            'scope_tolerance_pct': tolerance,
            'guaranteed_flat_bonus': guaranteed_bonus,
            'notes': request.POST.get('notes', '').strip(),
        }

        try:
            service.update(ce_id, **update_data)
            messages.success(request, 'Excepción actualizada correctamente.')
            return redirect('human_resources:commission_exception_detail', ce_id=ce_id)
        except Exception as e:
            messages.error(request, f'Error al actualizar: {str(e)}')

    context = {
        'exception': exception,
    }

    return render(request, template, context)
    






@login_required
def commissions_report(request):
    user = request.user
    template = 'human_resources/payroll/commissions_report.html'
    allowed_routes = get_allowed_routes_for_user(user).order_by('id')
    service = CommissionsReport(allowed_routes=allowed_routes)

    filters = {
        'month': request.GET.get('month', str(datetime.now().month)),
        'year': request.GET.get('year', str(datetime.now().year)),
        'status': request.GET.getlist('status'),
        'query_text': request.GET.get('query_text', ''),
    }

    available_years = SaleTarget.objects.values_list('period__year', flat=True).distinct().order_by('-period__year')
    commissions_data = service.get_data(**filters)


    context = {
        'routes': allowed_routes,
        'commissions': commissions_data,
        'filters': filters,
        'available_years': available_years,
    }
    
    return render(request, template, context)

@login_required
@require_POST
def commissions_action(request):
    user = request.user
    allowed_routes = get_allowed_routes_for_user(user).order_by('id')
    service = CommissionsReport(allowed_routes=allowed_routes)

    action = request.POST.get('action')
    selected_routes = request.POST.getlist('selected_routes')
    month = request.POST.get('action_month')
    year = request.POST.get('action_year')

    base_url = reverse('human_resources:commissions_report')

    if not month or not year:
        messages.error(request, 'Faltan parámetros de fecha para realizar la acción.')
        return redirect(base_url)

    if action == 'recalculate':
        existing_settlements = CommissionSettlement.objects.filter(
            route__in=allowed_routes,
            period_start__year=int(year),
            period_start__month=int(month)
        ).values_list('route_id', flat=True)
        
        missing_routes = set(allowed_routes.values_list('id', flat=True)) - set(existing_settlements)
        routes_to_process = list(missing_routes.union(set(selected_routes)))

        if not routes_to_process:
            messages.warning(request, 'Todas las rutas del periodo ya están calculadas. Selecciona alguna en la tabla si deseas recalcularla.')
        else:
            try:
                count = service.create_multiple(routes_to_process, month, year)
                if count > 0:
                    messages.success(request, f'Se procesaron {count} cálculos correctamente.')
                else:
                    messages.info(request, 'No se realizó ningún cálculo. Revisa que las rutas tengan perfil configurado o no estén cerradas.')
            except Exception as e:
                messages.error(request, f'Error durante el cálculo: {str(e)}')

    elif action == 'close':
        if not selected_routes:
            messages.error(request, 'Debes seleccionar al menos una ruta en la tabla para cerrar su cálculo.')
        else:
            try:
                count = service.close_settlements(selected_routes, month, year)
                
                if count > 0:
                    messages.success(request, f'{count} cálculos de comisiones cerrados. Ya no podrán ser recalculados.')
                else:
                    messages.info(request, 'No se cerró ningún cálculo (es probable que las rutas seleccionadas ya tuvieran cálculos cerrados o no tengan en este periodo).')
            except Exception as e:
                messages.error(request, f'Error al cerrar los cálculos: {str(e)}')

    elif action == 'export_data':
        if not selected_routes:
            messages.error(request, 'Debes seleccionar al menos una ruta en la tabla para descargar los datos.')
        else:
            response = service.export_report_data(selected_routes, month, year)
            if response:
                return response
            messages.info(request, 'No se encontraron datos para descargar con la selección actual.')

    elif action == 'send_draft':
        if not selected_routes:
            messages.error(request, 'Selecciona al menos una ruta para compartir los borradores.')
        else:
            count = service.send_commission_report(selected_routes, month, year, report_type='draft')
            if count > 0:
                messages.success(request, f'Se envió el correo con {count} borradores exitosamente.')
            else:
                messages.info(request, 'Ninguna de las rutas seleccionadas está en estado Borrador.')

    elif action == 'send_closed':
        if not selected_routes:
            messages.error(request, 'Selecciona al menos una ruta para compartir los reportes cerrados.')
        else:
            count = service.send_commission_report(selected_routes, month, year, report_type='closed')
            if count > 0:
                messages.success(request, f'Se envió el correo con {count} cálculos cerrados exitosamente.')
            else:
                messages.info(request, 'Ninguna de las rutas seleccionadas está en estado Cerrado.')

    query_string = urlencode({'month': month, 'year': year})
    redirect_url = f"{base_url}?{query_string}"
    
    return redirect(redirect_url)