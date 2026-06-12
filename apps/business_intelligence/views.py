import json
from django.core.paginator import Paginator
from django.shortcuts import render
from apps.core.utils import get_allowed_routes_for_user
from django.contrib.auth.decorators import login_required
from apps.core.models import Warehouse, ProductClass, ProductCategory, CustomerType, Region, Route
from django.http import HttpResponse
import openpyxl
from apps.sales.services.sale_transactions.sale_transactions_crud import SaleTransactionCRUD
from apps.sales.services.sale_targets.sale_targets_crud import SaleTargetCRUD
from apps.business_intelligence.services.sales_dashboard.sales_dashboard import SalesDashboard
from apps.business_intelligence.services.customers_kpis.customers_kpis import CustomersKpis
from apps.business_intelligence.services.sales_breakdown.sales_breakdown import SalesBreakdownService
from apps.customers.services.customers_crud.customers_crud import CustomerCrud
import csv
from django.db.models.functions import ExtractYear
from django.db.models import Sum
from datetime import datetime, date
from apps.business_intelligence.services.commercial_risk.commercial_risk import CommercialRisk


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


from apps.business_intelligence.services.routes_kpis.routes_kpis import RoutesKpisService

@login_required
def routes_kpis(request):
    template = 'business_intelligence/routes_kpis/routes_kpis.html'
    
    allowed_routes = get_allowed_routes_for_user(request.user)
    
    date_start = request.GET.get('date_start')
    date_end = request.GET.get('date_end')
    selected_route_id = request.GET.get('route')
    
    if not selected_route_id and allowed_routes.exists():
        selected_route_id = allowed_routes.first().id

    if selected_route_id:
        target_route = allowed_routes.filter(id=selected_route_id)
    else:
        target_route = allowed_routes.none()
    
    service = RoutesKpisService(target_route, date_start, date_end)
    routes_data, global_charts = service.get_data()
    
    route_data = routes_data[0] if routes_data else None

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
def commercial_risk(request):
    template = 'business_intelligence/commercial_risk/commercial_risk.html'
    allowed_routes = get_allowed_routes_for_user(request.user)

    today = date.today()
    date_start = request.GET.get('date_start')
    date_end = request.GET.get('date_end')
    selected_route_id = request.GET.get('route')

    if not date_start:
        date_start = date(today.year, 1, 1).strftime('%Y-%m-%d')
    if not date_end:
        date_end = today.strftime('%Y-%m-%d')
    if not selected_route_id and allowed_routes.exists():
        selected_route_id = allowed_routes.first().id

    print('params:', date_start, date_end, selected_route_id)

    date_start_obj = datetime.strptime(date_start, '%Y-%m-%d').date()
    date_end_obj = datetime.strptime(date_end, '%Y-%m-%d').date()

    risk_engine = CommercialRisk(
        date_start=date_start_obj, 
        date_end=date_end_obj, 
        route_id=selected_route_id
    )

    data = risk_engine.get_data()
    global_kpis = risk_engine.get_global_kpis()

    print(global_kpis)

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
def sales_breakdown(request):
    template = 'business_intelligence/sales_breakdown/sales_breakdown.html'
    
    allowed_routes = get_allowed_routes_for_user(request.user)
    
    # Get filters
    warehouses = request.GET.getlist('warehouses')
    routes = request.GET.getlist('routes')
    product_classes = request.GET.getlist('product_classes')
    product_categories = request.GET.getlist('product_categories')
    date_start = request.GET.get('date_start')
    date_end = request.GET.get('date_end')
    dimension = request.GET.get('dimension', 'customer_productclass_product')
    page_number = request.GET.get('page', 1)
    
    filters = {}
    if routes: filters['routes'] = routes
    if warehouses: filters['warehouses'] = warehouses
    if product_classes: filters['product_classes'] = product_classes
    if product_categories: filters['product_categories'] = product_categories
    if date_start: filters['sale_date_start'] = date_start
    if date_end: filters['sale_date_end'] = date_end
    
    transaction_crud = SaleTransactionCRUD()
    transactions_qs = transaction_crud.read(allowed_routes, **filters)
    
    if request.GET.get('export') == 'csv':

        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="desglose_ventas.csv"'
        response.write(b'\xef\xbb\xbf')

        dimension_config = {
            'customer_productclass_product': {
                'fields': ['customer__id', 'customer__name', 'product_class__name', 'product__id', 'product__name'],
                'headers': ['Cliente', 'Línea', 'Producto']
            },
            'productclass_customer_product': {
                'fields': ['product_class__name', 'customer__id', 'customer__name', 'product__id', 'product__name'],
                'headers': ['Línea', 'Cliente', 'Producto']
            },
            'productclass_product': {
                'fields': ['product_class__name', 'product__id', 'product__name'],
                'headers': ['Línea', 'Producto']
            },
            'management_productclass_product': {
                'fields': ['warehouse__name', 'product_class__name', 'product__id', 'product__name'],
                'headers': ['Gerencia', 'Línea', 'Producto']
            },
            'product_customer': {
                'fields': ['product__id', 'product__name', 'customer__id', 'customer__name'],
                'headers': ['Producto', 'Cliente']
            }
        }
        
        config = dimension_config.get(dimension, dimension_config['customer_productclass_product'])

        writer = csv.writer(response)
        writer.writerow(config['headers'] + ['Año', 'Venta Neta'])

        export_qs = transactions_qs.values(*config['fields']).annotate(
            year=ExtractYear('sale_date'), 
            total=Sum('net_amount')
        ).iterator(chunk_size=2000)

        for row in export_qs:
            out_row = []
            
            c_id = row.get('customer__id')
            c_name = row.get('customer__name')
            c = f"{c_id} - {c_name}".strip(" -") if c_id or c_name else 'Sin Cliente'
            
            p_id = row.get('product__id')
            p_name = row.get('product__name')
            p = f"{p_id} - {p_name}".strip(" -") if p_id or p_name else 'Sin Producto'
            
            l = row.get('product_class__name') or 'Sin Línea'
            w = row.get('warehouse__name') or 'Sin Gerencia'
            
            if dimension == 'customer_productclass_product':
                out_row.extend([c, l, p])
            elif dimension == 'productclass_customer_product':
                out_row.extend([l, c, p])
            elif dimension == 'productclass_product':
                out_row.extend([l, p])
            elif dimension == 'management_productclass_product':
                out_row.extend([w, l, p])
            elif dimension == 'product_customer':
                out_row.extend([p, c])
            else:
                out_row.extend([c, l, p])

            out_row.extend([row.get('year'), round(row.get('total') or 0, 2)])
            writer.writerow(out_row)

        return response

    service = SalesBreakdownService(transactions_qs, dimension)
    pivot_data, sorted_years, page_obj = service.get_data(page_number)
    
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
        'selected_date_start': date_start,
        'selected_date_end': date_end,
    }

    if request.htmx:
        return render(request, 'business_intelligence/sales_breakdown/partials/sales_breakdown_rows.html', context)
        
    return render(request, template, context)

@login_required
def sale_targets(request):
    template = 'sales/sale_targets/sale_targets.html'
    
    # Allowed routes based on Employee hierarchy
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

