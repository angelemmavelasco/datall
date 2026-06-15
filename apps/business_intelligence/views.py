from apps.core.models import Warehouse, ProductClass, ProductCategory, CustomerType, Region, Route, Employee, SaleTransaction, Customer
from apps.core.utils import get_allowed_routes_for_user
from django.db.models import Sum, Q
from django.db.models.functions import ExtractYear

import json
import csv
import asyncio
import openpyxl
from collections import defaultdict
from datetime import datetime, date, timedelta
from asgiref.sync import sync_to_async


from django.core.paginator import Paginator
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse


from apps.business_intelligence.services.sales_dashboard.sales_dashboard import SalesDashboard
from apps.business_intelligence.services.customers_kpis.customers_kpis import CustomersKpis, CustomerProfileBuilder
from apps.business_intelligence.services.routes_kpis.routes_kpis import RoutesKpisService
from apps.business_intelligence.services.commercial_risk.commercial_risk import CommercialRisk
from apps.business_intelligence.services.sales_breakdown.sales_breakdown import SalesBreakdownService
from apps.business_intelligence.services.unique_customers.unique_customers import UniqueCustomersService
from apps.business_intelligence.services.monthly_breakdown_by_warehouse.monthly_breakdown_by_warehouse import MonthlyBreakdownByWarehouse  

from apps.sales.services.sale_transactions.sale_transactions_crud import SaleTransactionCRUD
from apps.sales.services.sale_targets.sale_targets_crud import SaleTargetCRUD

from apps.customers.services.customers_crud.customers_crud import CustomerCrud



@login_required
def sales_dashboard(request):
    template = 'business_intelligence/sales_dashboard/sales_dashboard.html'

    allowed_routes = get_allowed_routes_for_user(request.user)

    warehouses = request.GET.getlist('warehouses')
    sale_warehouses = request.GET.getlist('sale_warehouses')
    product_class = request.GET.getlist('product_class')
    product_category = request.GET.getlist('product_category')
    routes = request.GET.getlist('routes')
    regions = request.GET.getlist('regions')
    today = date.today()
    date_start = request.GET.get('date_start')
    date_end = request.GET.get('date_end')
    
    if not date_start:
        date_start = date(today.year, 1, 1).strftime('%Y-%m-%d')
    if not date_end:
        date_end = today.strftime('%Y-%m-%d')

    filters = {}
    if routes: filters['routes'] = routes
    if warehouses: filters['route_warehouse_ids'] = warehouses
    if sale_warehouses: filters['warehouses'] = sale_warehouses
    if product_class: filters['product_classes'] = product_class
    if product_category: filters['product_categories'] = product_category
    if regions: filters['regions'] = regions

    transaction_filters = filters.copy()
    if date_start: transaction_filters['sale_date_start'] = date_start
    if date_end: transaction_filters['sale_date_end'] = date_end

    target_filters = filters.copy()
    if date_start: target_filters['period_start'] = date_start
    if date_end: target_filters['period_end'] = date_end

    transaction_crud = SaleTransactionCRUD()
    transactions_qs = transaction_crud.read(allowed_routes, **transaction_filters)

    transactions_data = list(transactions_qs.values(
        'sale_date', 'net_amount', 'gross_amount', 'quantity', 'profit', 
        'route_id', 'route__name', 'route__warehouse_id', 'route__warehouse__name',
        'warehouse_id', 'warehouse__name', 
        'product_class_id', 'product_class__name', 'product_class__product_category__name',
        'product_id', 'product__name', 'customer_id', 'customer__name'
    ))

    targets_crud = SaleTargetCRUD()
    targets_qs = targets_crud.read(allowed_routes, **target_filters)
    targets_data = list(targets_qs.values(
        'period', 'target_amount', 'route_id', 'route__name', 'route__warehouse_id', 'route__warehouse__name', 'warehouse_id', 'warehouse__name', 'product_class_id'
    ))

    calculator = SalesDashboard(transactions_data, targets_data, date_start, date_end)
    
    kpis = calculator.calculate_kpis()
    timeline_data = calculator.calculate_timeline()
    warehouse_chart_data = calculator.calculate_warehouse_chart()
    product_class_chart_data = calculator.calculate_product_class_chart()
    product_category_chart_data = calculator.calculate_product_category_chart()
    
    route_table = calculator.calculate_route_table()
    product_table = calculator.calculate_top_products()
    customer_table = calculator.calculate_top_customers()

    context = {
        'kpis': kpis,
        'timeline_data': json.dumps(timeline_data),
        'warehouse_chart_data': json.dumps(warehouse_chart_data),
        'product_class_chart_data': json.dumps(product_class_chart_data),
        'product_category_chart_data': json.dumps(product_category_chart_data),
        'route_table': route_table,
        'product_table': product_table,
        'customer_table': customer_table,


        'filter_routes': allowed_routes,
        'filter_warehouses': Warehouse.objects.all(),
        'filter_product_classes': ProductClass.objects.all(),
        'filter_product_categories': ProductCategory.objects.all(),
        'filter_regions': Region.objects.all(),


        'selected_warehouses': warehouses,
        'selected_sale_warehouses': sale_warehouses,
        'selected_product_class': product_class,
        'selected_product_category': product_category,
        'selected_routes': routes,
        'selected_regions': regions,
        'selected_date_start': date_start,
        'selected_date_end': date_end,
    }

    return render(request, template, context)

@login_required
def routes_kpis(request):
    template = 'business_intelligence/routes_kpis/routes_kpis.html'
    
    allowed_routes = get_allowed_routes_for_user(request.user)
    
    today = date.today()
    date_start = request.GET.get('date_start')
    date_end = request.GET.get('date_end')
    selected_route_id = request.GET.get('route')

    if not date_start:
        date_start = date(today.year, 1, 1).strftime('%Y-%m-%d')
    if not date_end:
        date_end = (date(today.year, today.month, 1) - timedelta(days=1)).strftime('%Y-%m-%d')
    
    if not selected_route_id and allowed_routes.exists():
        selected_route_id = allowed_routes.first().id

    if selected_route_id:
        target_route = allowed_routes.filter(id=selected_route_id)
    else:
        target_route = allowed_routes.none()
    
    service = RoutesKpisService(target_route, date_start, date_end)
    routes_data, global_charts = service.get_data()
    
    route_data = routes_data[0] if routes_data else None
    print(route_data)
    print(global_charts)

    context = {
        'route': route_data,
        'global_charts': json.dumps(global_charts),
        'filter_routes': allowed_routes,
        'selected_date_start': date_start,
        'selected_date_end': date_end,
        'selected_route': str(selected_route_id) if selected_route_id else '',
    }

    return render(request, template, context)

@login_required
def warehouses_kpis(request):
    context = {}
    return render(request, 'business_intelligence/warehouses_kpis/warehouses_kpis.html', context)



@login_required
def products_kpis(request):
    context = {}
    return render(request, 'business_intelligence/products_kpis/products_kpis.html', context)






@login_required
def customers_kpis(request):
    template = 'business_intelligence/customers_kpis/customers_kpis.html'
    allowed_routes = get_allowed_routes_for_user(request.user)
    print(allowed_routes)

    #get filters
    warehouses = request.GET.getlist('warehouses')
    routes = request.GET.getlist('routes')
    customer_types = request.GET.getlist('customer_types')
    opinion_leader = request.GET.get('opinion_leader')
    start_registration_date = request.GET.get('start_registration_date')
    end_registration_date = request.GET.get('end_registration_date')
    query_text = request.GET.get('query_text')

    #set filters dict
    filters = {}
    if routes: filters['routes'] = routes
    if warehouses: filters['warehouses'] = warehouses
    if customer_types: filters['customer_types'] = customer_types
    if query_text: filters['query_text'] = query_text
    if opinion_leader: filters['opinion_leader'] = opinion_leader
    if start_registration_date: filters['start_registration_date'] = start_registration_date
    if end_registration_date: filters['end_registration_date'] = end_registration_date

    #apply filters and instance objs
    customers_crud = CustomerCrud()
    customers_qs = customers_crud.read(allowed_routes, **filters)

    if request.GET.get('export') == 'csv':


        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="customers_kpis.csv"'
        response.write(b'\xef\xbb\xbf')
        writer = csv.writer(response)

        customers_kpis_service = CustomersKpis(customers_qs)
        all_customers_data, months_headers = customers_kpis_service.build_dashboard_data()

        header_row = [
            'ID', 'Nombre', 'Clasificación', 'Frecuencia de compra',
            'Saldo Actual', 'Saldo Vencido', 'Límite de crédito', '% Uso de crédito',
            'Categorías de productos', 'Promedio mensual año pasado', 'Promedio mensual año actual'
        ]
        for h in months_headers:
            header_row.append(h.strftime('%b %Y'))
            
        writer.writerow(header_row)

        for c in all_customers_data:
            row = [
                c.id, c.name, getattr(c.category_last_moving_q, 'name', ''),
                getattr(c, 'frequency', ''),
                round(getattr(c, 'current_balance', 0), 2),
                round(getattr(c, 'overdue_balance', 0), 2),
                round(getattr(c, 'credit_limit', 0), 2),
                round(getattr(c, 'credit_usage', 0), 2),
                getattr(c, 'product_classes_with_consumption', 0),
                round(getattr(c, 'previous_year_average', 0), 2),
                round(getattr(c, 'current_year_average', 0), 2)
            ]
            for m in getattr(c, 'monthly_consumption_qs', []):
                row.append(round(m.get('sale', 0), 2))
                
            writer.writerow(row)

        return response

    paginator = Paginator(customers_qs, 100)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    #get metrics only for the paginated slice
    customers_data = []
    months_headers = []
    if page_obj.object_list:
        customers_kpis_service = CustomersKpis(page_obj.object_list)
        customers_data, months_headers = customers_kpis_service.build_dashboard_data()

    context = {
        'customers': customers_data,
        'page_obj': page_obj,
        'months_headers': months_headers,
        'filter_warehouses': Warehouse.objects.all(),
        'filter_product_classes': ProductClass.objects.all(),
        'filter_product_categories': ProductCategory.objects.all(),
        'filter_customer_types': CustomerType.objects.all(),
        'filter_routes': allowed_routes,
        
        'selected_start_registration_date': start_registration_date,
        'selected_end_registration_date': end_registration_date,
        'selected_warehouses': warehouses,
        'selected_routes': routes,
        'selected_customer_types': customer_types,
        'selected_opinion_leader': opinion_leader,
        'query_text': query_text,
    }

    if request.htmx:
        return render(request, 'business_intelligence/customers_kpis/partials/customer_kpis_rows.html', context)

    return render(request, template, context)

@login_required
def customer_kpis(request, customer_id):
    template = 'business_intelligence/customers_kpis/customer_kpis.html'

    customer_base = get_object_or_404(
        Customer.objects.select_related('customer_type', 'route'), 
        pk=customer_id
    )


    builder = CustomerProfileBuilder(customer_base)
    customer_with_kpis = builder.build()

    context = {
        'customer': customer_with_kpis
    }

    return render(request, template, context)







@login_required
def commercial_risk(request):
    template = 'business_intelligence/commercial_risk/commercial_risk.html'
    allowed_routes = get_allowed_routes_for_user(request.user)

    today = date.today()
    date_start = request.GET.get('date_start')
    date_end = request.GET.get('date_end')
    selected_route_id = request.GET.get('route')

    if not date_start:
        date_start = date(today.year-1, 1, 1).strftime('%Y-%m-%d')
    if not date_end:
        #the last day of the previous month
        date_end = date(today.year, today.month, 1).replace(day=1) - timedelta(days=1)
        date_end = date_end.strftime('%Y-%m-%d')
    if not selected_route_id and allowed_routes.exists():
        selected_route_id = allowed_routes.first().id

    date_start_obj = datetime.strptime(date_start, '%Y-%m-%d').date()
    date_end_obj = datetime.strptime(date_end, '%Y-%m-%d').date()

    risk_engine = CommercialRisk(
        date_start=date_start_obj, 
        date_end=date_end_obj, 
        route_id=selected_route_id
    )

    data = risk_engine.get_data()
    global_kpis = risk_engine.get_global_kpis()


    context = {
        'data': data,
        **global_kpis,

        'filter_routes': allowed_routes,
        'selected_date_start': date_start,
        'selected_date_end': date_end,
        'selected_route': str(selected_route_id) if selected_route_id else '',
        
    }

    return render(request, template, context)

@login_required
async def export_commercial_risk_data(request):

    today = date.today()
    date_start = request.GET.get('date_start')
    date_end = request.GET.get('date_end')
    selected_route_id = request.GET.get('route')

    if not date_start:
        date_start = date(today.year-1, 1, 1).strftime('%Y-%m-%d')
    if not date_end:
        date_end = (date(today.year, today.month, 1) - timedelta(days=1)).strftime('%Y-%m-%d')

    date_start_obj = datetime.strptime(date_start, '%Y-%m-%d').date()
    date_end_obj = datetime.strptime(date_end, '%Y-%m-%d').date()

    @sync_to_async
    def generate_file():
        risk_engine = CommercialRisk(
            date_start=date_start_obj, 
            date_end=date_end_obj, 
            route_id=selected_route_id
        )
        return risk_engine.get_data_report()

    excel_file = await generate_file()

    response = HttpResponse(
        excel_file, 
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="reporte_riesgo_comercial_ruta_{selected_route_id}.xlsx"'
    
    return response








@login_required
def monthly_breakdown_by_warehouse(request):
    template = 'business_intelligence/monthly_breakdown_by_warehouse/monthly_breakdown_by_warehouse.html'
    user = request.user
    context = {}
    allowed_routes = get_allowed_routes_for_user(user)

    #valiodate which warehouses the user has access to
    if not user.groups.filter(name='acceso global').exists() and not user.is_superuser:
        employee = Employee.objects.filter(user=user).first()
        allowed_warehouses = Warehouse.objects.filter(
            Q(manager=employee) | Q(region__manager=employee)
        ).values('id', 'name').order_by('id')
    else:
        allowed_warehouses = Warehouse.objects.all().values('id', 'name').order_by('id')

    #catch filters
    today = date.today()
    try:
        year = int(request.POST.get('year', today.year))
    except ValueError:
        year = today.year
    warehouse_id_str = request.POST.get('warehouse')
    if not warehouse_id_str and allowed_warehouses.exists():
        warehouse = allowed_warehouses.first()['id']
    else:
        warehouse = warehouse_id_str

    #get dynamic years available from SaleTransaction
    years_qs = SaleTransaction.objects.dates('sale_date', 'year')
    filter_years = sorted([dt.year for dt in years_qs], reverse=True)
    if not filter_years:
        filter_years = [today.year]

    service = MonthlyBreakdownByWarehouse(year, allowed_routes, warehouse)
    warehouse_data = service.get_data()
    print(service.summary_for_assistant())

    context['filter_warehouses'] = allowed_warehouses
    context['filter_years'] = filter_years
    context['selected_warehouse'] = str(warehouse)
    context['selected_year'] = str(year)
    context['warehouse_data'] = warehouse_data

    return render(request, template, context)

@login_required
def export_monthly_breakdown_data(request):
    allowed_routes = get_allowed_routes_for_user(request.user)
    
    year = int(request.GET.get('year', date.today().year))
    warehouse = request.GET.get('warehouse')
    
    if not warehouse:
        return HttpResponse("No se seleccionó ninguna gerencia.", status=400)
    service = MonthlyBreakdownByWarehouse(year, allowed_routes, warehouse)
    
    return service.get_data_report()








@login_required
def sales_breakdown(request):
    template = 'business_intelligence/sales_breakdown/sales_breakdown.html'

    dimension_dict = {
        'customer_productclass_product': 'Cliente - Línea - Producto',
        'productclass_customer_product': 'Línea - Cliente - Producto',
        'productclass_product': 'Línea - Producto',
        'management_productclass_product': 'Gerencia - Línea - Producto',
        'product_customer': 'Producto - Cliente',
    } 
    
    allowed_routes = get_allowed_routes_for_user(request.user)
    
    # Get filters
    warehouses = request.GET.getlist('warehouses')
    routes = request.GET.getlist('routes')
    product_classes = request.GET.getlist('product_classes')
    product_categories = request.GET.getlist('product_categories')
    months = request.GET.getlist('months')
    dimension = request.GET.get('dimension', 'customer_productclass_product')
    page_number = request.GET.get('page', 1)
    
    filters = {}
    if routes: filters['routes'] = routes
    if warehouses: filters['warehouses'] = warehouses
    if product_classes: filters['product_classes'] = product_classes
    if product_categories: filters['product_categories'] = product_categories
    if months: filters['months'] = months
    
    transaction_crud = SaleTransactionCRUD()
    transactions_qs = transaction_crud.read(allowed_routes, **filters)

    service = SalesBreakdownService(transactions_qs, dimension)
    pivot_data, sorted_years, page_obj, selected_dimension = service.get_data(page_number)
    
    context = {
        'pivot_data': pivot_data,
        'years': sorted_years,
        'page_obj': page_obj,
        'dimension': dimension,
        
        'filter_warehouses': Warehouse.objects.all(),
        'filter_routes': allowed_routes,
        'filter_product_classes': ProductClass.objects.all(),
        'filter_product_categories': ProductCategory.objects.all(),
        
        'selected_warehouses': warehouses,
        'selected_routes': routes,
        'selected_product_classes': product_classes,
        'selected_product_categories': product_categories,
        'selected_months': months,
        'selected_dimension': selected_dimension,
    }

    if request.htmx:
        return render(request, 'business_intelligence/sales_breakdown/partials/sales_breakdown_rows.html', context)
        
    return render(request, template, context)

@login_required
async def export_sales_breakdown_data(request):
    user = await request.auser()
    
    @sync_to_async
    def generate_csv_sync():
        allowed_routes = get_allowed_routes_for_user(user)
        
        warehouses = request.GET.getlist('warehouses')
        routes = request.GET.getlist('routes')
        product_classes = request.GET.getlist('product_classes')
        product_categories = request.GET.getlist('product_categories')
        months = request.GET.getlist('months')
        dimension = request.GET.get('dimension', 'customer_productclass_product')
        
        filters = {}
        if routes: filters['routes'] = routes
        if warehouses: filters['warehouses'] = warehouses
        if product_classes: filters['product_classes'] = product_classes
        if product_categories: filters['product_categories'] = product_categories
        if months: filters['months'] = months
        
        transaction_crud = SaleTransactionCRUD()
        transactions_qs = transaction_crud.read(allowed_routes, **filters)

        service = SalesBreakdownService(transactions_qs, dimension)
        
        return service.get_report_data()

    csv_string = await generate_csv_sync()
    
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="desglose_ventas.csv"'
    response.write(b'\xef\xbb\xbf')
    response.write(csv_string)
    
    return response






@login_required
def unique_customers(request):
    template = 'business_intelligence/unique_customers/unique_customers.html'
    allowed_routes = get_allowed_routes_for_user(request.user)
    
    date_start = request.GET.get('date_start')
    date_end = request.GET.get('date_end')
    
    product_classes = request.GET.getlist('product_class')
    product_categories = request.GET.getlist('product_category')
    routes = request.GET.getlist('routes')
    warehouses = request.GET.getlist('warehouses')
    regions = request.GET.getlist('regions')
    
    filters = {}
    if date_start: filters['sale_date_start'] = date_start
    if date_end: filters['sale_date_end'] = date_end
    if product_classes: filters['product_classes'] = product_classes
    if product_categories: filters['product_categories'] = product_categories
    if routes: filters['routes'] = routes
    if warehouses: filters['route_warehouse_ids'] = warehouses
    if regions: filters['regions'] = regions

    transaction_crud = SaleTransactionCRUD()
    transactions_qs = transaction_crud.read(allowed_routes, **filters)
    
    service = UniqueCustomersService(transactions_qs)
    warehouses_data, product_classes_data = service.get_pivot_data()
    
    context = {
        'warehouses_data': warehouses_data,
        'product_classes_data': product_classes_data,
        
        # Filter options
        'filter_warehouses': Warehouse.objects.all(),
        'filter_product_classes': ProductClass.objects.all(),
        'filter_product_categories': ProductCategory.objects.all(),
        'filter_regions': Region.objects.all(),
        'filter_routes': allowed_routes,
        
        # Selected states
        'selected_date_start': date_start,
        'selected_date_end': date_end,
        'selected_product_class': product_classes,
        'selected_product_category': product_categories,
        'selected_routes': routes,
        'selected_warehouses': warehouses,
        'selected_regions': regions,
    }

    return render(request, template, context)








@login_required
def sale_targets(request):
    template = 'sales/sale_targets/sale_targets.html'
    allowed_routes = get_allowed_routes_for_user(request.user)
    
    # Extract filters
    date_start = request.GET.get('date_start')
    date_end = request.GET.get('date_end')
    
    product_classes = request.GET.getlist('product_classes')
    product_categories = request.GET.getlist('product_categories')
    routes = request.GET.getlist('routes')
    warehouses = request.GET.getlist('warehouses')
    
    # We rename date_start/date_end to period_start/period_end for the CRUD
    filters = {}
    if date_start: filters['period_start'] = date_start
    if date_end: filters['period_end'] = date_end
    if product_classes: filters['product_classes'] = product_classes
    if product_categories: filters['product_categories'] = product_categories
    if routes: filters['routes'] = routes
    if warehouses: filters['warehouses'] = warehouses

    targets_crud = SaleTargetCRUD()
    targets_qs = targets_crud.read(allowed_routes, **filters).order_by('-period', 'route_id')

    paginator = Paginator(targets_qs, 100)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'targets': page_obj.object_list,
        'page_obj': page_obj,
        
        # Filter options
        'filter_warehouses': Warehouse.objects.all(),
        'filter_product_classes': ProductClass.objects.all(),
        'filter_product_categories': ProductCategory.objects.all(),
        'filter_routes': allowed_routes,
        
        # Selected states
        'selected_date_start': date_start,
        'selected_date_end': date_end,
        'selected_product_classes': product_classes,
        'selected_product_categories': product_categories,
        'selected_routes': routes,
        'selected_warehouses': warehouses,
    }

    if request.htmx:
        return render(request, 'sales/sale_targets/partials/sale_targets_rows.html', context)

    return render(request, template, context)



@login_required
def sale_targets_export(request):
    # Allowed routes based on Employee hierarchy
    employee = request.user.employee_profile
    allowed_routes_qs = employee.get_reporting_tree_ids()
    allowed_routes = Route.objects.filter(id__in=allowed_routes_qs)
    
    # Extract filters
    date_start = request.GET.get('date_start')
    date_end = request.GET.get('date_end')
    
    product_classes = request.GET.getlist('product_classes')
    product_categories = request.GET.getlist('product_categories')
    routes = request.GET.getlist('routes')
    warehouses = request.GET.getlist('warehouses')
    
    filters = {}
    if date_start: filters['period_start'] = date_start
    if date_end: filters['period_end'] = date_end
    if product_classes: filters['product_classes'] = product_classes
    if product_categories: filters['product_categories'] = product_categories
    if routes: filters['routes'] = routes
    if warehouses: filters['warehouses'] = warehouses

    targets_crud = SaleTargetCRUD()
    targets_qs = targets_crud.read(allowed_routes, **filters).order_by('-period', 'route_id')

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Objetivos de Venta"

    # Headers based on HTML table
    headers = [
        "Periodo", 
        "Ruta", 
        "Gerencia", 
        "Clase de producto", 
        "Monto objetivo"
    ]
    ws.append(headers)

    for t in targets_qs:
        ws.append([
            t.period.strftime('%b %Y') if t.period else '',
            f"{t.route_id} - {t.route.name}" if t.route else '',
            f"{t.warehouse_id} - {t.warehouse.name}" if t.warehouse else '',
            f"{t.product_class_id} - {t.product_class.name}" if t.product_class else '',
            float(t.target_amount) if t.target_amount else 0.0
        ])

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=objetivos_venta.xlsx'
    wb.save(response)
    return response



summary = {
    # solo se muestra la info de la gerenci qeu se selecciono
    'gerencia': 'warehouse.name (de la cual se tiene el filtro activo)',
    'metricas_promedio_mensuales': {
        'venta_promedio': 0,
        'alcance_promedio': 0,
        'margen_promedio': 0,
        'clientes_nuevos_promedio': 0,
        'cuentas_por_cobrar_promedio': 0,
        'convenios_promedio': 0,

    },
   'metricas_mensuales': {
        'route.id - route.name': {
            'enero': {
                'alcance': 0,
                'margen': 0,
                'cuentas_por_cobrar': 0,
                'convenios': 0,
                'venta': 0,
                'desempeño_por_clase': {
                    'diamond': {
                        'objetivo': 0,
                        'venta': 0,
                        'alcance': 0,
                    },
                    'diamond naturals': {
                        'objetivo': 0,
                        'venta': 0,
                        'alcance': 0,
                    }, 
                    # ... y asi con todas las clase de productos. Ojo, se deben mostrar todas las clases auqnue tengan objetivo o venta 0
                }
                # ... y asi con todos los meses (hasta la fecha, es decir, a menos que el usuario seleccione años previos, solo se muestran los datos hasta el mes en curso)

            }
        }
   } 

}