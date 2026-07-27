from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from urllib.parse import urlencode
from django.http import JsonResponse

from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from apps.human_resources.services.employees import employees_crud
from apps.data_admin.services.data_history.data_history_crud import ActivityLogger
from apps.core.models import (
    Position, Warehouse, Employee, 
    PayrollType, Periodicity, TaxSystem,
    SystemModule, RouteCommissionSetup, CommissionProfile,
    SaleTarget, CommissionSettlement, Reference
    )
from apps.core.utils import get_allowed_routes_for_user

from django.conf import settings
from apps.human_resources.services.comissions.comissions import Comissions, CommissionExceptions, CommissionsReport, RouteCommissionException
from apps.human_resources.services.departments import DepartmentsService, DepartmentsKPIsService, ServiceError
from apps.human_resources.services.positions import PositionsService, PositionsKPIsService
from apps.human_resources.filters import DepartmentFilter, PositionFilter, SkillFilter
from apps.human_resources.forms import DepartmentForm, PositionForm, SkillForm, PositionSkillFormSet
from django.core.paginator import Paginator
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
    
    module = SystemModule.objects.filter(url_name='human_resources:employees').first()
    ActivityLogger.log_read(
        user=request.user,
        module=module,
        description='visualización del directorio de colaboradores',
        metadata={'filters': current_filters if current_filters else {}}
    )
    
    return render(request, TEMPLATE, context)

@login_required
def employee(request, user_id: int = None):
    TEMPLATE = 'human_resources/employees/employee.html'
    employees_service = employees_crud.EmployeesCRUD()
    
    context = {}
    
    user_obj = employees_service.get_user_with_employee_history(user_id=user_id)
    
    if not user_obj:
        messages.error(request, 'El colaborador no existe.')
        return redirect('human_resources:employees')
        
    context['user'] = user_obj
    context['employee_history'] = user_obj.employees.all()
    
    module = SystemModule.objects.filter(url_name='human_resources:employees').first()
    ActivityLogger.log_read(
        user=request.user,
        module=module,
        obj=user_obj,
        description=f'visualización de perfil de colaborador: {user_obj.first_name} {user_obj.last_name}'
    )
    
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
            module = SystemModule.objects.filter(url_name='human_resources:employees').first()
            ActivityLogger.log_create(
                user=request.user,
                module=module,
                obj=new_employee,
                description=f'creación de registro de colaborador: {new_employee.user.first_name} {new_employee.user.last_name}'
            )
            messages.success(request, 'Posición asignada con éxito al colaborador.')
            return redirect('human_resources:employee', user_id=new_employee.user_id)
        else:
            messages.error(request, 'Error al crear: Verifica que los campos obligatorios estén completos.')
            context['employee_data'] = raw_data
            return render(request, TEMPLATE, context)
            
    module = SystemModule.objects.filter(url_name='human_resources:employees').first()
    ActivityLogger.log_read(
        user=request.user,
        module=module,
        description='visualización del formulario para crear colaborador'
    )
    
    return render(request, TEMPLATE, context)

@login_required
def org_chart(request):
    TEMPLATE = 'human_resources/org_chart/org_chart.html'
    
    module = SystemModule.objects.filter(url_name='human_resources:org_chart').first()
    ActivityLogger.log_read(
        user=request.user,
        module=module,
        description='visualización del organigrama de la empresa'
    )
    
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
    
    ActivityLogger.log_read(
        user=user,
        module=module,
        description='visualización del listado de esquemas de comisiones',
        metadata={'filters': filters}
    )
    
    return render(request, template, context)


@login_required
def commission_profile_detail(request, cp_id: int):
    module = SystemModule.objects.filter(url_name='human_resources:commissions').first()
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
            
            ActivityLogger.log_update(
                user=user,
                module=module,
                obj=profile,
                description=f'actualización de esquema de comisiones: {profile.name}'
            )
            
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
    
    ActivityLogger.log_read(
        user=user,
        module=module,
        obj=profile,
        description=f'visualización de detalle de esquema de comisiones: {profile.name}'
    )
    
    return render(request, template, context)


@login_required
def commission_profile_create(request):
    user = request.user
    template = 'human_resources/payroll/commission_profile_create.html'
    allowed_routes = get_allowed_routes_for_user(user).order_by('id')
    module = SystemModule.objects.filter(url_name='human_resources:commissions').first()
    
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
            profile = service.commission_profile_create(profile_data, tiers_data, configs_data)
            
            ActivityLogger.log_create(
                user=request.user,
                module=module,
                obj=profile,
                description=f'creación de esquema de comisiones: {profile.name}'
            )
            
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
    
    ActivityLogger.log_read(
        user=request.user,
        module=module,
        description='visualización del formulario para crear un esquema de comisiones'
    )
    
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
    
    ActivityLogger.log_read(
        user=user,
        module=module,
        description='visualización de excepciones de comisiones',
        metadata={'filters': filters}
    )
    
    return render(request, template, context)

@login_required
def commission_exception_create(request):
    user = request.user
    template = 'human_resources/payroll/commission_exception_create.html'
    allowed_routes = get_allowed_routes_for_user(user).order_by('id')
    module = SystemModule.objects.filter(url_name='human_resources:commissions').first()

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
        
        ActivityLogger.log_create(
            user=user,
            module=module,
            description=f'creación masiva de excepciones de comisiones ({created_count} asignaciones)',
            changes={'route_ids': route_ids, 'exception_data': exception_data}
        )
        
        messages.success(request, f'Se registraron correctamente {created_count} excepciones.')
        return redirect('human_resources:commission_exceptions')

    context = {
        'routes': allowed_routes,
    }
    
    ActivityLogger.log_read(
        user=user,
        module=module,
        description='visualización del formulario para crear excepciones de comisiones'
    )
    
    return render(request, template, context)
    
@login_required
def commission_exception_detail(request, ce_id):
    user = request.user
    template = 'human_resources/payroll/commission_exception_detail.html'
    allowed_routes = get_allowed_routes_for_user(user).order_by('id')
    module = SystemModule.objects.filter(url_name='human_resources:commissions').first()

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
            
            ActivityLogger.log_update(
                user=user,
                module=module,
                obj=exception,
                description=f'actualización de excepción de comisiones de ruta {exception.route_id}',
                changes=update_data
            )
            
            messages.success(request, 'Excepción actualizada correctamente.')
            return redirect('human_resources:commission_exception_detail', ce_id=ce_id)
        except Exception as e:
            messages.error(request, f'Error al actualizar: {str(e)}')

    context = {
        'exception': exception,
    }

    ActivityLogger.log_read(
        user=user,
        module=module,
        obj=exception,
        description=f'visualización de detalle de excepción de comisiones de ruta {exception.route_id}'
    )

    return render(request, template, context)
    






@login_required
def commissions_report(request):
    user = request.user
    template = 'human_resources/payroll/commissions_report.html'
    allowed_routes = get_allowed_routes_for_user(user).order_by('id')
    service = CommissionsReport(allowed_routes=allowed_routes)
    module = SystemModule.objects.filter(url_name='human_resources:commissions_report').first()

    filters = {
        'month': request.GET.get('month', str(datetime.now().month-1)),
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
    
    ActivityLogger.log_read(
        user=user,
        module=module,
        description='visualización del reporte de comisiones',
        metadata={'filters': filters}
    )
    
    return render(request, template, context)

@login_required
@require_POST
def commissions_action(request):
    user = request.user
    allowed_routes = get_allowed_routes_for_user(user).order_by('id')
    service = CommissionsReport(allowed_routes=allowed_routes)
    module = SystemModule.objects.filter(url_name='human_resources:commissions_report').first()
    custom_emails_raw = request.POST.get('custom_emails', '')
    emails = []
    invalid_emails = []
    
    if custom_emails_raw:
        for e in custom_emails_raw.split(','):
            e = e.strip()
            if e:
                try:
                    validate_email(e)
                    emails.append(e)
                except ValidationError:
                    invalid_emails.append(e)
                    
    # Eliminada la validación suelta de invalid_emails aquí para evitar superposición
    
    action = request.POST.get('action')
    selected_routes = request.POST.getlist('selected_routes')
    month = request.POST.get('action_month')
    year = request.POST.get('action_year')

    base_url = reverse('human_resources:commissions_report')

    if not month or not year:
        messages.error(request, 'Faltan parámetros de fecha para realizar la acción.')
        return redirect(base_url)

    if action in ['send_draft', 'send_closed']:
        if invalid_emails and not emails:
            messages.error(request, 'Debes proporcionar al menos un correo válido. Revisa el formato e intenta nuevamente.')
            query_string = urlencode({'month': month, 'year': year})
            return redirect(f"{base_url}?{query_string}")

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
                    ActivityLogger.log_create(
                        user=user,
                        module=module,
                        description=f'cálculo de comisiones del periodo {month}/{year} ({count} procesados)',
                        changes={'routes_processed': list(routes_to_process)}
                    )
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
                    ActivityLogger.log_update(
                        user=user,
                        module=module,
                        description=f'cierre de cálculos de comisiones del periodo {month}/{year} ({count} cerrados)',
                        changes={'routes_closed': selected_routes}
                    )
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
                ActivityLogger.log_download(
                    user=user,
                    module=module,
                    description=f'descarga de reporte de comisiones del periodo {month}/{year} ({len(selected_routes)} rutas)',
                    metadata={'routes_exported': selected_routes}
                )
                return response
            messages.info(request, 'No se encontraron datos para descargar con la selección actual.')

    elif action == 'send_draft':
        if not selected_routes:
            messages.error(request, 'Selecciona al menos una ruta para compartir los borradores.')
        else:
            count = service.send_commission_report(selected_routes, month, year, report_type='draft', emails=emails)
            if count > 0:
                ActivityLogger.log_download(
                    user=user,
                    module=module,
                    description=f'envío de reporte borrador de comisiones por correo electrónico del periodo {month}/{year} ({count} rutas enviadas a {", ".join(emails)})',
                    metadata={'routes_sent': selected_routes}
                )
                msg = f'Se envió el correo con {count} borradores exitosamente.'
                if invalid_emails:
                    msg += f' (Se omitieron los siguientes correos por formato inválido: {", ".join(invalid_emails)})'
                messages.success(request, msg)
            else:
                messages.info(request, 'Ninguna de las rutas seleccionadas está en estado Borrador.')

    elif action == 'send_closed':
        if not selected_routes:
            messages.error(request, 'Selecciona al menos una ruta para compartir los reportes cerrados.')
        else:
            count = service.send_commission_report(selected_routes, month, year, report_type='closed',emails=emails)
            if count > 0:
                ActivityLogger.log_download(
                    user=user,
                    module=module,
                    description=f'envío de reporte cerrado de comisiones por correo electrónico del periodo {month}/{year} ({count} rutas enviadas a {", ".join(emails)})',
                    metadata={'routes_sent': selected_routes}
                )
                msg = f'Se envió el correo con {count} cálculos cerrados exitosamente.'
                if invalid_emails:
                    msg += f' (Se omitieron los siguientes correos por formato inválido: {", ".join(invalid_emails)})'
                messages.success(request, msg)
            else:
                messages.info(request, 'Ninguna de las rutas seleccionadas está en estado Cerrado.')

    query_string = urlencode({'month': month, 'year': year})
    redirect_url = f"{base_url}?{query_string}"
    
    return redirect(redirect_url)



@login_required
def commission_report_detail(request, pk):
    user = request.user
    template = 'human_resources/payroll/commission_report_detail.html'
    allowed_routes = get_allowed_routes_for_user(user).order_by('id')
    service = CommissionsReport(allowed_routes=allowed_routes)
    module = SystemModule.objects.filter(url_name='human_resources:commissions_report').first()
    
    context = service.get_settlement_detail(pk)
    
    settlement = context.get('settlement')
    ActivityLogger.log_read(
        user=user,
        module=module,
        obj=settlement,
        description=f"visualización de detalle del reporte de comisiones de ruta {settlement.route_id} ({settlement.period_start.strftime('%m/%Y')})" if settlement else 'visualización de detalle del reporte de comisiones'
    )
    
    return render(request, template, context)

@login_required
def department_list(request):
    template = 'human_resources/departments/department_list.html'
    departments_service = DepartmentsService(user=request.user)
    departments_kpis_service = DepartmentsKPIsService(departments_service=departments_service)
    can_create = departments_service._checkout_full_access

    departments_qs = departments_service.read_departments().order_by('id')
    department_filter = DepartmentFilter(request.GET, queryset=departments_qs)
    departments_qs = department_filter.qs

    paginator = Paginator(departments_qs, 100)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    query_dict = request.GET.copy()
    if 'page' in query_dict: del query_dict['page']

    departments = page_obj.object_list

    kpis = departments_kpis_service.stats

    context = {
        'departments': departments,
        'kpis': kpis,
        'query_string': query_dict.urlencode(),
        'page_obj': page_obj,
        'can_create': can_create,
        'filter': department_filter
    }

    if request.htmx:
        return render(request, 'human_resources/departments/partials/department_list_rows.html', context)

    return render(request, template, context)


@login_required
def department_create_form(request):
    template = 'human_resources/departments/department_form.html'
    departments_service = DepartmentsService(user=request.user)
    creating = True

    if request.method == 'POST':
        form = DepartmentForm(
            request.POST, 
            request.FILES,
            requesting_user=request.user,
            is_full_access=departments_service._is_full_access
        )
        if form.is_valid():
            try:
                new_department = departments_service.create_department(**form.cleaned_data)
                messages.success(request, 'Departamento creado correctamente.')
                return redirect('human_resources:department_details', pk=new_department.id)
            except ServiceError as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, f"Ocurrió un error inesperado: {str(e)}")
        else:
            messages.error(request, 'Por favor revisa los errores en el formulario.')
    else:
        form = DepartmentForm(
            requesting_user=request.user,
            is_full_access=departments_service._is_full_access
        )

    context = {
        'form': form,
        'creating': creating
    }

    return render(request, template, context)


@login_required
def department_details(request, pk):
    template = 'human_resources/departments/department_details.html'
    departments_service = DepartmentsService(user=request.user)
    can_update_access = departments_service._checkout_full_access

    department_instance = departments_service.read_department(pk=pk)
    if not department_instance:
        messages.error(request, 'Departamento no encontrado o no tienes permisos para verlo.')
        return redirect('human_resources:department_list')

    context = {
        'department_instance': department_instance,
        'can_update_access': can_update_access
    }
    return render(request, template, context)


@login_required
def department_update_form(request, pk):
    template = 'human_resources/departments/department_form.html'
    departments_service = DepartmentsService(user=request.user)
    can_update_access = departments_service._checkout_full_access
    creating = False

    department_instance = departments_service.read_department(pk=pk)
    if not department_instance:
        messages.error(request, 'Departamento no encontrado o no tienes permisos para editarlo.')
        return redirect('human_resources:department_list')

    if request.method == 'POST':
        form = DepartmentForm(
            request.POST, 
            request.FILES,
            instance=department_instance,
            requesting_user=request.user,
            is_full_access=departments_service._is_full_access
        )
        if form.is_valid():
            try:
                updated_department = departments_service.update_department(pk=pk, **form.cleaned_data)
                messages.success(request, 'Departamento actualizado correctamente.')
                return redirect('human_resources:department_details', updated_department.pk)
            except ServiceError as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, f"Ocurrió un error inesperado: {str(e)}")
        else:
            messages.error(request, 'Por favor revisa los errores en el formulario.')
    else:
        form = DepartmentForm(
            instance=department_instance,
            requesting_user=request.user,
            is_full_access=departments_service._is_full_access
        )

    context = {
        'form': form,
        'creating': creating,
        'can_update_access': can_update_access
    }

    return render(request, template, context)

@login_required
def position_list_view(request):
    template = 'human_resources/positions/position_list.html'
    positions_service = PositionsService(user=request.user)
    positions_kpis_service = PositionsKPIsService(positions_service=positions_service)
    can_create = positions_service._checkout_full_access

    positions_qs = positions_service.read_positions()
    position_filter = PositionFilter(request.GET, queryset=positions_qs)
    positions_qs = position_filter.qs

    paginator = Paginator(positions_qs, 100)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    query_dict = request.GET.copy()
    if 'page' in query_dict: del query_dict['page']

    positions = page_obj.object_list

    kpis = positions_kpis_service.stats

    context = {
        'positions': positions,
        'kpis': kpis,
        'query_string': query_dict.urlencode(),
        'page_obj': page_obj,
        'can_create': can_create,
        'filter': position_filter
    }

    if request.htmx:
        return render(request, 'human_resources/positions/partials/position_list_rows.html', context)

    return render(request, template, context)

@login_required
def position_create_view(request):
    template = 'human_resources/positions/position_form.html'
    positions_service = PositionsService(user=request.user)
    creating = True

    if not positions_service._is_full_access:
        messages.error(request, 'No tienes permisos para crear puestos.')
        return render(request, settings.ACCESS_DENIED_TEMPLATE)

    if request.method == 'POST':
        form = PositionForm(
            request.POST, 
            request.FILES,
            requesting_user=request.user,
            is_full_access=positions_service._is_full_access
        )
        formset = PositionSkillFormSet(request.POST, request.FILES)

        if form.is_valid() and formset.is_valid():
            try:
                new_position = positions_service.create_position(
                    position_data=form.cleaned_data, 
                    skills_data=formset.cleaned_data
                )
                messages.success(request, 'Puesto creado correctamente.')
                return redirect('human_resources:position_detail_view', pk=new_position.id)
            except ServiceError as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, f"Ocurrió un error inesperado: {str(e)}")
        else:
            messages.error(request, 'Por favor revisa los errores en el formulario.')
    else:
        form = PositionForm(
            requesting_user=request.user,
            is_full_access=positions_service._is_full_access
        )
        formset = PositionSkillFormSet()

    context = {
        'form': form,
        'formset': formset,
        'creating': creating
    }

    return render(request, template, context)

@login_required
def position_detail_view(request, pk):
    template = 'human_resources/positions/position_details.html'
    positions_service = PositionsService(user=request.user)
    can_update_access = positions_service._checkout_full_access

    position_instance = positions_service.read_position(pk=pk)
    if not position_instance:
        messages.error(request, 'Puesto no encontrado o no tienes permisos para verlo.')
        return redirect('human_resources:position_list_view')

    context = {
        'position_instance': position_instance,
        'can_update_access': can_update_access
    }
    return render(request, template, context)

@login_required
def position_update_view(request, pk):
    template = 'human_resources/positions/position_form.html'
    positions_service = PositionsService(user=request.user)
    can_update_access = positions_service._checkout_full_access
    creating = False

    if not can_update_access:
        messages.error(request, 'No tienes permisos para editar puestos.')
        return render(request, settings.ACCESS_DENIED_TEMPLATE)

    position_instance = positions_service.read_position(pk=pk)
    if not position_instance:
        messages.error(request, 'Puesto no encontrado o no tienes permisos para editarlo.')
        return redirect('human_resources:position_list_view')

    if request.method == 'POST':
        form = PositionForm(
            request.POST, 
            request.FILES,
            instance=position_instance,
            requesting_user=request.user,
            is_full_access=positions_service._is_full_access
        )
        formset = PositionSkillFormSet(request.POST, request.FILES, instance=position_instance)
        
        if form.is_valid() and formset.is_valid():
            try:
                updated_position = positions_service.update_position(
                    pk=pk, 
                    position_data=form.cleaned_data, 
                    skills_data=formset.cleaned_data
                )
                messages.success(request, 'Puesto actualizado correctamente.')
                return redirect('human_resources:position_detail_view', updated_position.pk)
            except ServiceError as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, f"Ocurrió un error inesperado: {str(e)}")
        else:
            messages.error(request, 'Por favor revisa los errores en el formulario.')
    else:
        form = PositionForm(
            instance=position_instance,
            requesting_user=request.user,
            is_full_access=positions_service._is_full_access
        )
        formset = PositionSkillFormSet(instance=position_instance)

    context = {
        'form': form,
        'formset': formset,
        'creating': creating,
        'can_update_access': can_update_access
    }

    return render(request, template, context)

@login_required
def skill_list_view(request):
    template = 'human_resources/positions/skill_list.html'
    positions_service = PositionsService(user=request.user)
    can_create = positions_service._checkout_full_access

    if not can_create:
        messages.error(request, 'No tienes permisos para ver ni crear habilidades.')
        return render(request, settings.ACCESS_DENIED_TEMPLATE)

    skills_qs = positions_service.read_skills()
    skill_filter = SkillFilter(request.GET, queryset=skills_qs)
    skills_qs = skill_filter.qs

    paginator = Paginator(skills_qs, 100)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    query_dict = request.GET.copy()
    if 'page' in query_dict: del query_dict['page']

    skills = page_obj.object_list

    context = {
        'skills': skills,
        'query_string': query_dict.urlencode(),
        'page_obj': page_obj,
        'can_create': can_create,
        'filter': skill_filter
    }

    if request.htmx:
        return render(request, 'human_resources/positions/partials/skill_list_rows.html', context)

    return render(request, template, context)

@login_required
def skill_create_view(request):
    template = 'human_resources/positions/skill_form.html'
    positions_service = PositionsService(user=request.user)
    creating = True

    if not positions_service._is_full_access:
        messages.error(request, 'No tienes permisos para crear habilidades.')
        return render(request, settings.ACCESS_DENIED_TEMPLATE)

    if request.method == 'POST':
        form = SkillForm(request.POST)
        if form.is_valid():
            try:
                positions_service.create_skill(**form.cleaned_data)
                messages.success(request, 'Habilidad creada correctamente.')
                next_url = request.GET.get('next')
                if next_url:
                    return redirect(next_url)
                    
                return redirect('human_resources:position_list_view')
            except ServiceError as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, f"Ocurrió un error inesperado: {str(e)}")
        else:
            messages.error(request, 'Por favor revisa los errores en el formulario.')
    else:
        form = SkillForm()

    context = {
        'form': form,
        'creating': creating,
    }

    return render(request, template, context)

@login_required
def skill_detail_view(request, pk):
    template = 'human_resources/positions/skill_details.html'
    positions_service = PositionsService(user=request.user)
    can_update_access = positions_service._checkout_full_access
    
    skill_instance = positions_service.read_skill(pk=pk)
    if not skill_instance:
        messages.error(request, 'Habilidad no encontrada o no tienes permisos para verla.')
        return redirect('human_resources:position_list_view')

    context = {
        'skill_instance': skill_instance,
        'can_update_access': can_update_access
    }
    return render(request, template, context)

@login_required
def skill_update_view(request, pk):
    template = 'human_resources/positions/skill_form.html'
    positions_service = PositionsService(user=request.user)
    can_update_access = positions_service._checkout_full_access
    creating = False

    if not can_update_access:
        messages.error(request, 'No tienes permisos para editar habilidades.')
        return render(request, settings.ACCESS_DENIED_TEMPLATE)

    skill_instance = positions_service.read_skill(pk=pk)
    if not skill_instance:
        messages.error(request, 'Habilidad no encontrada o no tienes permisos para verla.')
        return redirect('human_resources:position_list_view')

    if request.method == 'POST':
        form = SkillForm(
            request.POST, 
            instance=skill_instance
        )
        if form.is_valid():
            try:
                updated_skill = positions_service.update_skill(
                    pk=pk, 
                    data=form.cleaned_data
                )
                messages.success(request, 'Habilidad actualizada correctamente.')
                return redirect('human_resources:skill_detail_view', updated_skill.pk)
            except ServiceError as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, f"Ocurrió un error inesperado: {str(e)}")
        else:
            messages.error(request, 'Por favor revisa los errores en el formulario.')
    else:
        form = SkillForm(
            instance=skill_instance
        )

    context = {
        'form': form,
        'creating': creating,
        'can_update_access': can_update_access
    }

    return render(request, template, context)

@login_required
def skill_delete_view(request, pk):
    positions_service = PositionsService(user=request.user)

    if not positions_service._is_full_access:
        messages.error(request, 'No tienes permisos para eliminar habilidades.')
        return render(request, settings.ACCESS_DENIED_TEMPLATE)

    skill_instance = positions_service.read_skill(pk=pk)
    if not skill_instance:
        messages.error(request, 'Habilidad no encontrada o no tienes permisos para editarla.')
        return redirect('human_resources:skill_list_view')

    if request.method == 'POST':
        try:
            positions_service.delete_skill(pk=pk)
            messages.success(request, 'Habilidad eliminada correctamente.')
            return redirect('human_resources:skill_list_view')
        except ServiceError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Ocurrió un error inesperado: {str(e)}")
            
    return redirect('human_resources:skill_detail_view', pk=pk)