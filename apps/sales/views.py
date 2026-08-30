from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.utils import timezone
from django.http import HttpResponse
from django.db.models import Q
from dateutil.relativedelta import relativedelta
import datetime

from .exports import *

from .services.warehouses import (
    WarehousesService,
    WarehouseNotFound,
    PermissionsError,
    ServiceError,
)
from .services.routes import (
    RoutesService,
    RouteNotFound,
    PermissionsError as RoutePermissionsError,
    ServiceError as RouteServiceError,
)
from .services.sale_transactions import (
    SaleTransactionsService,
    SaleTransactionsStats,
    SaleTransactionNotFound,
    ServiceError as SaleTransactionServiceError,
    PermissionsError as SaleTransactionPermissionsError,
)
from .services.sale_targets import (
    SaleTargetsService,
    SaleTargetsStats,
    SaleTargetNotFound,
    ServiceError as SaleTargetServiceError,
    PermissionsError as SaleTargetPermissionsError,
)
from .services.sale_targets_calculator import (
    SaleTargetCalculatorService,
    TargetCalculatorError,
)
from apps.customers.services.customers import CustomersService
from apps.products.services.products import ProductsService
from apps.products.models import ProductClass
from apps.human_resources.services.employees import EmployeesService
from apps.core.models import User
from .filters import WarehouseFilter, RouteFilter, SaleTransactionFilter, SaleTargetFilter
from .forms import (
    WarehouseForm,
    RouteForm,
    RouteAssignmentFormSet,
    UserRouteAccessFormSet,
    SaleTargetForm,
)

@login_required
def warehouse_list_view(request):
    template = 'sales/warehouses/warehouse_list.html'
    service = WarehousesService(user=request.user)

    available_actions = None
    if service.has_full_access:
        available_actions = 'sales/warehouses/partials/warehouse_list__actions.html'

    warehouses = service.read_warehouses()
    warehouse_filter = WarehouseFilter(request.GET, queryset=warehouses)
    warehouses = warehouse_filter.qs

    context = {
        'warehouses': warehouses,
        'filter': warehouse_filter,
        'available_actions': available_actions,
    }
    return render(request, template, context)

@login_required
def warehouse_detail_view(request, pk: str):
    template = 'sales/warehouses/warehouse_detail.html'
    service = WarehousesService(user=request.user)

    try:
        warehouse = service.read_warehouse(pk=pk)
    except Exception as e:
        messages.error(request, str(e))
        return redirect('sales:warehouse_list_view')

    available_actions = None
    if service.has_full_access:
        available_actions = 'sales/warehouses/partials/warehouse_detail__actions.html'

    context = {
        'warehouse': warehouse,
        'available_actions': available_actions,
    }
    return render(request, template, context)

@login_required
def warehouse_create_view(request):
    template = 'sales/warehouses/warehouse_form.html'
    service = WarehousesService(user=request.user)

    if not service.has_full_access:
        messages.error(request, 'No tienes permisos para crear centros de distribución.')
        return redirect('sales:warehouse_list_view')

    if request.method == 'POST':
        form = WarehouseForm(request.POST)
        if form.is_valid():
            try:
                new_warehouse = service.create_warehouse(**form.cleaned_data)
                messages.success(request, f'Centro de distribución {new_warehouse.name} creado correctamente.')
                next_url = request.GET.get('next') or request.POST.get('next')
                if next_url:
                    return redirect(next_url)
                return redirect('sales:warehouse_detail_view', new_warehouse.pk)

            except PermissionsError as e:
                messages.error(request, str(e))
                return redirect('sales:warehouse_list_view')

            except ServiceError as e:
                messages.error(request, str(e))

            except Exception as e:
                messages.error(request, f"Ocurrió un error inesperado al crear: {str(e)}")
        else:
            messages.error(request, 'Por favor revisa los errores en el formulario.')
    else:
        form = WarehouseForm()

    context = {
        'form': form,
    }
    return render(request, template, context)

@login_required
def warehouse_update_view(request, pk: str):
    template = 'sales/warehouses/warehouse_form.html'
    service = WarehousesService(user=request.user)

    if not service.has_full_access:
        messages.error(request, 'No tienes permisos para actualizar centros de distribución.')
        return redirect('sales:warehouse_list_view')

    try:
        warehouse_instance = service.read_warehouse(pk=pk)
    except WarehouseNotFound:
        messages.error(request, "El centro de distribución solicitado no existe.")
        return redirect('sales:warehouse_list_view')
    except PermissionsError:
        messages.error(request, "No tienes permisos para actualizar este centro de distribución.")
        return redirect('sales:warehouse_list_view')
    except ServiceError as e:
        messages.error(request, str(e))
        return redirect('sales:warehouse_list_view')

    if request.method == 'POST':
        form = WarehouseForm(request.POST, instance=warehouse_instance)
        if form.is_valid():
            try:
                updated_warehouse = service.update_warehouse(pk=pk, **form.cleaned_data)
                messages.success(request, "Centro de distribución actualizado correctamente.")
                return redirect('sales:warehouse_detail_view', updated_warehouse.pk)
            except (PermissionsError, WarehouseNotFound) as e:
                messages.error(request, str(e))
                return redirect('sales:warehouse_list_view')
            except ServiceError as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, f"Ocurrió un error inesperado al actualizar: {str(e)}")
        else:
            messages.error(request, 'Por favor revisa los errores en el formulario.')
    else:
        form = WarehouseForm(instance=warehouse_instance)

    context = {
        'form': form,
        'updating': warehouse_instance,
    }
    return render(request, template, context)

@login_required
def route_list_view(request):
    template = 'sales/routes/route_list.html'
    service = RoutesService(user=request.user)

    available_actions = None
    if service.has_full_access:
        available_actions = 'sales/routes/partials/route_list__actions.html'

    routes = service.read_routes()
    route_filter = RouteFilter(request.GET, queryset=routes, request=request)
    routes = route_filter.qs

    context = {
        'routes': routes,
        'filter': route_filter,
        'available_actions': available_actions,
    }
    return render(request, template, context)

@login_required
def route_detail_view(request, pk: str):
    template = 'sales/routes/route_detail.html'
    service = RoutesService(user=request.user)

    try:
        route = service.read_route(pk=pk)
    except RouteNotFound:
        messages.error(request, f"La ruta con ID '{pk}' no fue encontrada.")
        return redirect('sales:route_list_view')
    except (PermissionsError, RoutePermissionsError) as e:
        messages.error(request, str(e))
        return redirect('sales:route_list_view')
    except Exception as e:
        messages.error(request, f"Ocurrió un error al cargar la ruta: {str(e)}")
        return redirect('sales:route_list_view')

    available_actions = None
    if service.has_full_access:
        available_actions = 'sales/routes/partials/route_detail__actions.html'

    context = {
        'route': route,
        'available_actions': available_actions,
    }
    return render(request, template, context)

@login_required
def route_create_view(request):
    template = 'sales/routes/route_form.html'
    service = RoutesService(user=request.user)

    if not service.has_full_access:
        messages.error(request, 'No tienes permisos para crear rutas.')
        return redirect('sales:route_list_view')

    if request.method == 'POST':
        form = RouteForm(request.POST)
        assignments_formset = RouteAssignmentFormSet(request.POST, prefix='assignments')
        accesses_formset = UserRouteAccessFormSet(request.POST, prefix='accesses')

        if form.is_valid() and assignments_formset.is_valid() and accesses_formset.is_valid():
            try:
                assignments_data = [f.cleaned_data for f in assignments_formset if f.cleaned_data]
                accesses_data = [f.cleaned_data for f in accesses_formset if f.cleaned_data]

                new_route = service.create_route(
                    route_data=form.cleaned_data,
                    assignments_data=assignments_data,
                    accesses_data=accesses_data,
                )
                messages.success(request, f'Ruta {new_route.id} creada correctamente.')
                next_url = request.GET.get('next') or request.POST.get('next')
                if next_url:
                    return redirect(next_url)
                return redirect('sales:route_detail_view', new_route.pk)

            except (RoutePermissionsError, PermissionsError) as e:
                messages.error(request, str(e))
                return redirect('sales:route_list_view')

            except (RouteServiceError, ServiceError) as e:
                messages.error(request, str(e))

            except Exception as e:
                messages.error(request, f"Ocurrió un error inesperado al crear: {str(e)}")
        else:
            messages.error(request, 'Por favor revisa los errores en el formulario.')
    else:
        form = RouteForm()
        assignments_formset = RouteAssignmentFormSet(prefix='assignments')
        accesses_formset = UserRouteAccessFormSet(prefix='accesses')

    employees_service = EmployeesService(user=request.user)
    initial_employees = employees_service.read_employees()[:30]
    initial_users = User.objects.filter(is_active=True).order_by('first_name', 'last_name', 'username')[:30]

    context = {
        'form': form,
        'assignments_formset': assignments_formset,
        'accesses_formset': accesses_formset,
        'initial_employees': initial_employees,
        'initial_users': initial_users,
        'can_update_access': service.has_full_access,
    }
    return render(request, template, context)

@login_required
def route_update_view(request, pk: str):
    template = 'sales/routes/route_form.html'
    service = RoutesService(user=request.user)

    if not service.has_full_access:
        messages.error(request, 'No tienes permisos para actualizar rutas.')
        return redirect('sales:route_detail_view', pk=pk)

    try:
        route_instance = service.read_route(pk=pk)
    except RouteNotFound:
        messages.error(request, "La ruta solicitada no existe.")
        return redirect('sales:route_list_view')
    except (PermissionsError, RoutePermissionsError):
        messages.error(request, "No tienes permisos para actualizar esta ruta.")
        return redirect('sales:route_list_view')
    except Exception as e:
        messages.error(request, str(e))
        return redirect('sales:route_list_view')

    if request.method == 'POST':
        form = RouteForm(request.POST, instance=route_instance)
        assignments_formset = RouteAssignmentFormSet(request.POST, instance=route_instance, prefix='assignments')
        accesses_formset = UserRouteAccessFormSet(request.POST, instance=route_instance, prefix='accesses')

        if form.is_valid() and assignments_formset.is_valid() and accesses_formset.is_valid():
            try:
                assignments_data = [f.cleaned_data for f in assignments_formset if f.cleaned_data]
                accesses_data = [f.cleaned_data for f in accesses_formset if f.cleaned_data]

                updated_route = service.update_route(
                    pk=pk,
                    route_data=form.cleaned_data,
                    assignments_data=assignments_data,
                    accesses_data=accesses_data,
                )
                messages.success(request, f"Ruta {updated_route.id} actualizada correctamente.")
                return redirect('sales:route_detail_view', updated_route.pk)

            except (RoutePermissionsError, PermissionsError) as e:
                messages.error(request, str(e))
                return redirect('sales:route_list_view')

            except (RouteServiceError, ServiceError) as e:
                messages.error(request, str(e))

            except Exception as e:
                messages.error(request, f"Ocurrió un error inesperado al actualizar: {str(e)}")
        else:
            messages.error(request, 'Por favor revisa los errores en el formulario.')
    else:
        form = RouteForm(instance=route_instance)
        assignments_formset = RouteAssignmentFormSet(instance=route_instance, prefix='assignments')
        accesses_formset = UserRouteAccessFormSet(instance=route_instance, prefix='accesses')

    employees_service = EmployeesService(user=request.user)
    initial_employees = employees_service.read_employees()[:30]
    initial_users = User.objects.filter(is_active=True).order_by('first_name', 'last_name', 'username')[:30]

    context = {
        'form': form,
        'assignments_formset': assignments_formset,
        'accesses_formset': accesses_formset,
        'updating': route_instance,
        'initial_employees': initial_employees,
        'initial_users': initial_users,
        'can_update_access': service.has_full_access,
    }
    return render(request, template, context)

@login_required
def route_options_view(request):
    """
    Returns HTML option items for searchable route dropdowns via HTMX.
    """
    q = request.GET.get('q_route', request.GET.get('q', '')).strip()
    field_name = request.GET.get('field_name', 'route')
    selected_id = request.GET.get('selected_id', '')

    service = RoutesService(user=request.user)
    base_qs = service.get_allowed_routes(can_view=True).filter(is_active=True)

    if q:
        base_qs = base_qs.filter(
            Q(id__icontains=q) |
            Q(name__icontains=q) |
            Q(business_unit__name__icontains=q)
        )

    routes = base_qs.select_related('business_unit')[:30]

    return render(
        request,
        'sales/routes/partials/route_options.html',
        {
            'routes': routes,
            'field_name': field_name,
            'selected_id': selected_id,
        }
    )

@login_required
def sale_transaction_list_view(request):
    template = 'sales/sale_transactions/sale_transaction_list.html'
    service = SaleTransactionsService(user=request.user)
    stats_service = SaleTransactionsStats(sale_transactions_service=service)

    transactions_qs = service.read_transactions()
    transaction_filter = SaleTransactionFilter(request.GET, queryset=transactions_qs, request=request)
    transactions_qs = transaction_filter.qs

    paginator = Paginator(transactions_qs, 100)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    query_dict = request.GET.copy()
    if 'page' in query_dict:
        del query_dict['page']

    transactions = page_obj.object_list
    kpis = stats_service.stats(qs=transactions_qs)

    selected_customer_ids = request.GET.getlist('customer')
    selected_product_ids = request.GET.getlist('product')

    customers_service = CustomersService(user=request.user)
    cust_base = customers_service.read_customers()
    cust_selected = cust_base.filter(pk__in=selected_customer_ids) if selected_customer_ids else cust_base.none()
    cust_remaining = cust_base.exclude(pk__in=selected_customer_ids).order_by('name', 'id')[:20]
    initial_customers = list(cust_selected) + list(cust_remaining)

    products_service = ProductsService(user=request.user)
    prd_base = products_service.read_products()
    prd_selected = prd_base.filter(pk__in=selected_product_ids) if selected_product_ids else prd_base.none()
    prd_remaining = prd_base.exclude(pk__in=selected_product_ids).order_by('name', 'id')[:20]
    initial_products = list(prd_selected) + list(prd_remaining)

    context = {
        'transactions': transactions,
        'kpis': kpis,
        'query_string': query_dict.urlencode(),
        'page_obj': page_obj,
        'filter': transaction_filter,
        'initial_customers': initial_customers,
        'selected_customer_ids': selected_customer_ids,
        'initial_products': initial_products,
        'selected_product_ids': selected_product_ids,
        'can_view_cost': service.has_full_access,
    }

    if request.htmx:
        target = request.headers.get('HX-Target')
        if target == 'sale-transaction-list-content':
            return render(request, 'sales/sale_transactions/partials/sale_transaction_list_content.html', context)
        return render(request, 'sales/sale_transactions/partials/sale_transaction_list_rows.html', context)

    return render(request, template, context)

@login_required
def sale_transaction_detail_view(request, pk: str):
    template = 'sales/sale_transactions/sale_transaction_detail.html'
    service = SaleTransactionsService(user=request.user)

    try:
        transaction_obj = service.read_transaction(pk=pk)
    except (SaleTransactionNotFound, PermissionsError) as e:
        messages.error(request, str(e))
        return redirect('sales:sale_transaction_list_view')
    except Exception as e:
        messages.error(request, f"Ocurrió un error al cargar la transacción: {str(e)}")
        return redirect('sales:sale_transaction_list_view')

    context = {
        'transaction': transaction_obj,
        'can_view_cost': service.has_full_access,
    }
    return render(request, template, context)

@login_required
def sale_target_list_view(request):
    template = 'sales/sale_targets/sale_target_list.html'
    service = SaleTargetsService(user=request.user)
    stats_service = SaleTargetsStats(sale_targets_service=service)

    query_dict = request.GET.copy()
    if 'period_from' not in request.GET and 'period_to' not in request.GET:
        current_month = timezone.localdate().strftime('%Y-%m')
        query_dict['period_from'] = current_month
        query_dict['period_to'] = current_month

    targets_qs = service.read_sale_targets()
    target_filter = SaleTargetFilter(query_dict, queryset=targets_qs, request=request)
    targets_qs = target_filter.qs

    paginator = Paginator(targets_qs, 100)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    if 'page' in query_dict:
        del query_dict['page']

    targets = page_obj.object_list
    kpis = stats_service.stats(qs=targets_qs)

    context = {
        'targets': targets,
        'kpis': kpis,
        'query_string': query_dict.urlencode(),
        'page_obj': page_obj,
        'filter': target_filter,
    }

    if request.htmx:
        target = request.headers.get('HX-Target')
        if target == 'sale-target-list-content':
            return render(request, 'sales/sale_targets/partials/sale_target_list_content.html', context)
        return render(request, 'sales/sale_targets/partials/sale_target_list_rows.html', context)

    return render(request, template, context)

@login_required
def sale_target_detail_view(request, pk: int):
    template = 'sales/sale_targets/sale_target_detail.html'
    service = SaleTargetsService(user=request.user)

    available_actions = None
    if service.has_full_access:
        available_actions = 'sales/sale_targets/partials/sale_target_detail__actions.html'

    try:
        target_obj = service.read_sale_target(pk=pk)
    except (SaleTargetNotFound, PermissionsError, SaleTargetPermissionsError) as e:
        messages.error(request, str(e))
        return redirect('sales:sale_target_list_view')
    except Exception as e:
        messages.error(request, f"Ocurrió un error al cargar el objetivo de venta: {str(e)}")
        return redirect('sales:sale_target_list_view')

    context = {
        'target': target_obj,
        'available_actions': available_actions,
    }
    return render(request, template, context)

@login_required
def sale_target_update_view(request, pk: int):
    template = 'sales/sale_targets/sale_target_form.html'
    service = SaleTargetsService(user=request.user)

    if not service.has_full_access:
        messages.error(request, 'No tienes permisos para actualizar objetivos de venta.')
        return redirect('sales:sale_target_detail_view', pk=pk)

    try:
        target_instance = service.read_sale_target(pk=pk)
    except SaleTargetNotFound:
        messages.error(request, "El objetivo de venta solicitado no existe.")
        return redirect('sales:sale_target_list_view')
    except (PermissionsError, SaleTargetPermissionsError):
        messages.error(request, "No tienes permisos para actualizar este objetivo de venta.")
        return redirect('sales:sale_target_list_view')
    except Exception as e:
        messages.error(request, str(e))
        return redirect('sales:sale_target_list_view')

    if request.method == 'POST':
        form = SaleTargetForm(request.POST, instance=target_instance)

        if form.is_valid():
            try:
                updated_target = service.update_sale_target(
                    pk=pk,
                    target_data=form.cleaned_data,
                )
                messages.success(request, f"Objetivo de venta para ruta {updated_target.route_id} actualizado correctamente.")
                return redirect('sales:sale_target_detail_view', updated_target.pk)

            except (SaleTargetPermissionsError, PermissionsError) as e:
                messages.error(request, str(e))
                return redirect('sales:sale_target_list_view')

            except (SaleTargetServiceError, ServiceError) as e:
                messages.error(request, str(e))

            except Exception as e:
                messages.error(request, f"Ocurrió un error inesperado al actualizar: {str(e)}")
        else:
            messages.error(request, 'Por favor revisa los errores en el formulario.')
    else:
        form = SaleTargetForm(instance=target_instance)

    context = {
        'form': form,
        'updating': target_instance,
    }
    return render(request, template, context)

@login_required
def sale_target_calculator_view(request):
    template = 'sales/sale_target_calculator/sale_target_calculator.html'
    calculator_service = SaleTargetCalculatorService(user=request.user)

    routes = calculator_service.get_allowed_routes_qs()
    product_classes = ProductClass.objects.all().order_by('name')
    today = timezone.localdate()

    if request.htmx:
        action = request.GET.get('action') or request.POST.get('action')

        if action == 'toggle_mode':
            mode = request.GET.get('mode', 'transfer')
            origin_route_id = request.GET.get('origin_route', '')
            destination_route_id = request.GET.get('destination_route', '')

            origin_route_obj = routes.filter(id=origin_route_id).first() if origin_route_id else None
            dest_route_obj = routes.filter(id=destination_route_id).first() if destination_route_id else None

            context = {
                'mode': mode,
                'routes': routes,
                'origin_route_id': origin_route_id,
                'destination_route_id': destination_route_id,
                'origin_route_obj': origin_route_obj,
                'destination_route_obj': dest_route_obj,
            }
            return render(request, 'sales/sale_target_calculator/partials/scenario_config.html', context)

        if action == 'load_customers':
            origin_route_id = request.GET.get('origin_route', '')
            filter_type = request.GET.get('filter_type', 'assigned')
            search_query = request.GET.get('search', '').strip().lower()

            customers = []
            if origin_route_id:
                customers_qs = calculator_service.get_route_customers(origin_route_id, filter_type=filter_type)
                if search_query:
                    customers_qs = customers_qs.filter(
                        Q(id__icontains=search_query) | Q(name__icontains=search_query)
                    )
                customers = list(customers_qs)

            context = {
                'customers': customers,
                'filter_type': filter_type,
                'origin_route_id': origin_route_id,
            }
            return render(request, 'sales/sale_target_calculator/partials/customer_selector.html', context)

        if action == 'search_available_customers':
            origin_route_id = request.GET.get('origin_route', '')
            filter_type = request.GET.get('customer_filter', request.GET.get('filter_type', 'assigned'))
            search_query = request.GET.get('q_customer', request.GET.get('search', '')).strip().lower()
            selected_ids = request.GET.getlist('selected_customers')

            customers = []
            if origin_route_id:
                customers_qs = calculator_service.get_route_customers(origin_route_id, filter_type=filter_type)
                if selected_ids:
                    customers_qs = customers_qs.exclude(id__in=selected_ids)
                if search_query:
                    customers_qs = customers_qs.filter(
                        Q(id__icontains=search_query) | Q(name__icontains=search_query)
                    )
                customers = list(customers_qs[:50] if filter_type == 'all' and not search_query else customers_qs)

            context = {
                'customers': customers,
                'filter_type': filter_type,
            }
            return render(request, 'sales/sale_target_calculator/partials/available_customers_list.html', context)

        if action == 'calculate':
            mode = request.POST.get('mode', 'transfer')
            calc_method = request.POST.get('calc_method', 'average')
            origin_route_id = request.POST.get('origin_route')
            destination_route_id = request.POST.get('destination_route')
            adjustment_direction = request.POST.get('adjustment_direction', 'remove')
            transfer_growth_rule = request.POST.get('transfer_growth_rule', 'exact')
            target_year = request.POST.get('target_year')
            effective_month = request.POST.get('effective_month')
            eval_customer_start = request.POST.get('eval_customer_start')
            eval_customer_end = request.POST.get('eval_customer_end')
            eval_route_start = request.POST.get('eval_route_start')
            eval_route_end = request.POST.get('eval_route_end')
            product_classes_selected = request.POST.getlist('product_classes')
            selected_customers = request.POST.getlist('selected_customers')

            custom_growths = {}
            custom_bases = {}
            for key in request.POST.keys():
                if key.startswith('growth_pc_'):
                    parts = key.split('_')
                    if len(parts) == 4:
                        _, _, pc_id, m_num = parts
                        if pc_id not in custom_growths:
                            custom_growths[pc_id] = {}
                        val = request.POST.get(key)
                        if val != '' and val is not None:
                            try:
                                custom_growths[pc_id][int(m_num)] = float(val)
                            except (ValueError, TypeError):
                                pass
                elif key.startswith('base_pc_'):
                    parts = key.split('_')
                    if len(parts) == 3:
                        _, _, pc_id = parts
                        val = request.POST.get(key)
                        if val != '' and val is not None:
                            try:
                                custom_bases[pc_id] = float(val)
                            except (ValueError, TypeError):
                                pass

            try:
                results = calculator_service.calculate_simulation(
                    mode=mode,
                    calc_method=calc_method,
                    origin_route_id=origin_route_id,
                    destination_route_id=destination_route_id,
                    customer_ids=selected_customers,
                    adjustment_direction=adjustment_direction,
                    transfer_growth_rule=transfer_growth_rule,
                    target_year=int(target_year) if target_year else today.year,
                    effective_month=effective_month,
                    eval_customer_start=eval_customer_start,
                    eval_customer_end=eval_customer_end,
                    eval_route_start=eval_route_start,
                    eval_route_end=eval_route_end,
                    product_class_ids=product_classes_selected,
                    custom_growths=custom_growths,
                    custom_bases=custom_bases,
                )
                context = {
                    'results': results,
                    'errors': [],
                }
            except Exception as e:
                context = {
                    'results': None,
                    'errors': [str(e)],
                }

            return render(request, 'sales/sale_target_calculator/partials/calculator_results.html', context)

    default_year = today.year
    default_eff_month = f"{default_year}-{today.month:02d}"

    first_curr_month = today.replace(day=1)
    past_end = first_curr_month - datetime.timedelta(days=1)
    past_start = (past_end.replace(day=1)) - relativedelta(months=2)

    context = {
        'routes': routes,
        'product_classes': product_classes,
        'default_year': default_year,
        'default_eff_month': default_eff_month,
        'default_eval_cust_start': past_start.strftime('%Y-%m'),
        'default_eval_cust_end': past_end.strftime('%Y-%m'),
        'default_eval_route_start': past_start.strftime('%Y-%m'),
        'default_eval_route_end': past_end.strftime('%Y-%m'),
    }
    return render(request, template, context)