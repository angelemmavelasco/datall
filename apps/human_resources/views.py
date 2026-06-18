from django.shortcuts import render, redirect
from django.http import JsonResponse

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth import get_user_model

from apps.human_resources.services.employees import employees_crud
from apps.core.models import Position, Warehouse, Employee, PayrollType, Periodicity, TaxSystem, DataHistory
from django.contrib.contenttypes.models import ContentType
from apps.data_admin.services.data_history.data_history_crud import DataHistoryCrud

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
    DataHistoryCrud().log_action(
        request=request,
        action=DataHistory.Action.READ,
        description="Consulta del catálogo de empleados.",
        changes={"filters": current_filters}
    )
    
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
    DataHistoryCrud().log_action(
        request=request,
        action=DataHistory.Action.READ,
        description=f"Consulta de historial laboral del usuario {user_id}.",
        changes={"user_id": user_id}
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
            from django.forms.models import model_to_dict
            new_state = model_to_dict(new_employee)
            DataHistoryCrud().log_action(
                request=request,
                action=DataHistory.Action.CREATE,
                content_type=ContentType.objects.get_for_model(Employee),
                object_id=str(new_employee.id),
                description=f"Asignación de posición laboral al usuario {new_employee.user_id}.",
                changes={"new_state": new_state}
            )
            messages.success(request, 'Posición asignada con éxito al empleado.')
            return redirect('human_resources:employee', user_id=new_employee.user_id)
        else:
            messages.error(request, 'Error al crear: Verifica que los campos obligatorios estén completos.')
            context['employee_data'] = raw_data
            return render(request, TEMPLATE, context)
            
    DataHistoryCrud().log_action(
        request=request,
        action=DataHistory.Action.READ,
        description="Consulta del formulario de asignación de posición laboral."
    )
    return render(request, TEMPLATE, context)

@login_required
def org_chart(request):
    TEMPLATE = 'human_resources/org_chart/org_chart.html'
    DataHistoryCrud().log_action(
        request=request,
        action=DataHistory.Action.READ,
        description="Consulta del organigrama de la empresa."
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
    
    DataHistoryCrud().log_action(
        request=request,
        action=DataHistory.Action.READ,
        description="Carga de datos del organigrama de la empresa.",
        changes={"filters": {"q": search_query}}
    )
    return JsonResponse(chart_data)

