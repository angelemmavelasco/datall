from apps.core.models import Warehouse, ProductClass, ProductCategory, CustomerType, Region, Route, Employee, SaleTransaction, Customer, SystemModule, Reference
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
import calendar
from dateutil.relativedelta import relativedelta


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
from apps.business_intelligence.services.target_scope.target_scope import TargetScopeService
from apps.business_intelligence.services.monthly_breakdown_by_warehouse.monthly_breakdown_by_warehouse import MonthlyBreakdownByWarehouse  
from apps.business_intelligence.services.collections.collections import Collections

from apps.sales.services.sale_transactions.sale_transactions_crud import SaleTransactionCRUD
from apps.sales.services.sale_targets.sale_targets_crud import SaleTargetCRUD

from apps.customers.services.customers_crud.customers_crud import CustomerCrud
from apps.customers.services.accounts_receivable.accounts_receivable_crud import AccountsReceivableCrud



from apps.data_admin.services.data_history.data_history_crud import ActivityLogger



@login_required
def sales_dashboard(request):
    template = 'business_intelligence/sales_dashboard/sales_dashboard.html'
    print(request.user)
    print(request.user.groups.all())
    allowed_routes = get_allowed_routes_for_user(request.user)
    print(allowed_routes)
    

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
        last_day = calendar.monthrange(today.year, today.month)[1]
        date_end = date(today.year, today.month, last_day).strftime('%Y-%m-%d')

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

    module = SystemModule.objects.filter(url_name='business_intelligence:sales_dashboard').first()
    metadata = filters if filters else None
    ActivityLogger.log_read(
        user=request.user, 
        module=module, 
        obj=None, 
        description='visualización del dashboard de ventas',
        metadata={
            'filters': metadata if metadata else {}
        }
    )

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

    context = {
        'route': route_data,
        'global_charts': json.dumps(global_charts),
        'filter_routes': allowed_routes,
        'selected_date_start': date_start,
        'selected_date_end': date_end,
        'selected_route': str(selected_route_id) if selected_route_id else '',
    }

    module = SystemModule.objects.filter(url_name='business_intelligence:routes_kpis').first()
    metadata = {}
    if date_start:
        metadata['date_start'] = date_start
    if date_end:
        metadata['date_end'] = date_end
    if selected_route_id:
        metadata['selected_route'] = selected_route_id

    ActivityLogger.log_read(
        user=request.user,
        module=module,
        description='visualización de kpis de rutas',
        metadata={
            'filters': metadata if metadata else {}
        }
    )

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
def collections(request):
    user = request.user
    template = 'business_intelligence/collections/collections.html'
    
    allowed_routes = get_allowed_routes_for_user(user)

    #valiodate which warehouses the user has access to
    if not user.groups.filter(name='acceso global').exists() and not user.is_superuser:
        allowed_warehouse_ids = allowed_routes.values_list('warehouse_id', flat=True)
        allowed_region_ids = allowed_routes.values_list('warehouse__region_id', flat=True)
        
        allowed_warehouses = Warehouse.objects.filter(
            id__in=allowed_warehouse_ids
        ).distinct().values('id', 'name').order_by('id')

        allowed_regions = Region.objects.filter(
            id__in=allowed_region_ids
        ).distinct().values('id', 'name').order_by('id')
    else:
        allowed_warehouses = Warehouse.objects.all().values('id', 'name').order_by('id')
        allowed_regions = Region.objects.all().values('id', 'name').order_by('id')

    # request filters
    today = date.today()
    date_end = request.GET.get('date_end', today)
    warehouses = request.GET.getlist('warehouses')
    regions = request.GET.getlist('regions')
    routes = request.GET.getlist('routes')
    customers = request.GET.getlist('customers')

    customer_filters = {}
    if routes: customer_filters['routes'] = routes
    if warehouses: customer_filters['warehouses'] = warehouses
    if regions: customer_filters['regions'] = regions

    allowed_customers = CustomerCrud().read(allowed_routes=allowed_routes, **customer_filters)

    filters = {}
    if customers:
        filters['customers'] = customers
    else:
        filters['customers'] = list(allowed_customers.values_list('id', flat=True))

    if date_end: filters['date_end'] = date_end

    ar_service = Collections(
        allowed_routes=allowed_routes, 
        allowed_customers=allowed_customers
    )
    raw_qs = ar_service.read(**filters)

    collections = ar_service.get_ar_by_customer(raw_qs)
    kpis = ar_service.get_ar_kpis(raw_qs)

    paginator = Paginator(collections, 100)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    collections_data = page_obj.object_list 
    query_dict = request.GET.copy()
    if 'page' in query_dict:
        del query_dict['page']
    query_string = query_dict.urlencode()

    print(kpis)
    


    context ={
        #htmx
        'page_obj': page_obj,
        'query_string': query_string,

        # filters
        'available_years': [2026, 2023],
        'filter_customers': allowed_customers,
        'filter_warehouses': allowed_warehouses,
        'filter_routes': allowed_routes,
        'filter_regions': allowed_regions,

        # selected filters
        'selected_customers': customers if customers else list(allowed_customers.values_list('id', flat=True)),
        'selected_warehouses': warehouses if warehouses else list(allowed_warehouses.values_list('id', flat=True)),
        'selected_routes': routes if routes else list(allowed_routes.values_list('id', flat=True)),
        'selected_regions': regions if regions else list(allowed_regions.values_list('id', flat=True)),
        'selected_date_end': date_end,

        # ar data
        'collections': collections_data,
        'kpis': kpis
    }

    if request.htmx:
        return render(request, 'business_intelligence/collections/partials/collections_rows.html', context)

    return render(request, template, context)




@login_required
def customers_kpis(request):
    template = 'business_intelligence/customers_kpis/customers_kpis.html'
    allowed_routes = get_allowed_routes_for_user(request.user)

    warehouses = request.GET.getlist('warehouses')
    routes = request.GET.getlist('routes')
    customer_types = request.GET.getlist('customer_types')
    opinion_leader = request.GET.get('opinion_leader')
    start_registration_date = request.GET.get('start_registration_date')
    end_registration_date = request.GET.get('end_registration_date')
    query_text = request.GET.get('query_text')

    order_contrib = request.GET.get('order_contrib', 'net_amount')
    start_contrib = request.GET.get('start_contrib_from')
    end_contrib = request.GET.get('start_contrib_to')

    filters = {}
    if routes: filters['routes'] = routes
    if warehouses: filters['warehouses'] = warehouses
    if customer_types: filters['customer_types'] = customer_types
    if query_text: filters['query_text'] = query_text
    if opinion_leader: filters['opinion_leader'] = opinion_leader
    if start_registration_date: filters['start_registration_date'] = start_registration_date
    if end_registration_date: filters['end_registration_date'] = end_registration_date

    if start_contrib:
        try:
            start_contrib = datetime.strptime(start_contrib, '%Y-%m-%d').date()
        except ValueError:
            start_contrib = None

    if end_contrib:
        try:
            end_contrib = datetime.strptime(end_contrib, '%Y-%m-%d').date()
        except ValueError:
            end_contrib = None

    today = date.today()
    if not start_contrib:
        start_contrib = date(today.year, today.month, 1) + relativedelta(months=-3)

    if not end_contrib:
        end_contrib = date(today.year, today.month, 1) + relativedelta(days=-1)

    contrib_config = {
        'order_contrib': order_contrib,
        'start_date': start_contrib,
        'end_date': end_contrib
    }

    customers_crud = CustomerCrud()
    customers_qs = customers_crud.read(allowed_routes, **filters)

    customers_kpis_service = CustomersKpis(customers_qs)
    all_customers_data, months_headers, global_kpis = customers_kpis_service.build_dashboard_data(contrib_config)

    paginator = Paginator(all_customers_data, 100)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    customers_data = page_obj.object_list 
    query_dict = request.GET.copy()

    if 'page' in query_dict:
        del query_dict['page']
    query_string = query_dict.urlencode()

    relevant_product_classes_count = len(Reference.objects.filter(
        field_context='relevant_product_classes',
        key='customer',
        module__url_name='business_intelligence:customers_kpis'
    ).values_list('reference', flat=True))

    context = {
        'customers': customers_data,
        'global_kpis': global_kpis,
        'page_obj': page_obj,
        'query_string': query_string,
        'months_headers': months_headers,
        'filter_warehouses': Warehouse.objects.all(),
        'filter_product_classes': ProductClass.objects.all(),
        'filter_product_categories': ProductCategory.objects.all(),
        'filter_customer_types': CustomerType.objects.all(),
        'filter_routes': allowed_routes,
        'relevant_product_classes_count': relevant_product_classes_count,
        
        'selected_start_registration_date': start_registration_date,
        'selected_end_registration_date': end_registration_date,
        'selected_warehouses': warehouses,
        'selected_routes': routes,
        'selected_customer_types': customer_types,
        'selected_opinion_leader': opinion_leader,
        'query_text': query_text,

        'order_contrib': order_contrib,
        'contrib_config': contrib_config,

        # helpers for tooltips
        'today': today,
        'end_last_q': today.replace(day=1) - timedelta(days=1),
        'start_last_q': today.replace(day=1) - relativedelta(months=3),
    }

    if request.htmx:
        return render(request, 'business_intelligence/customers_kpis/partials/customer_kpis_rows.html', context)

    module = SystemModule.objects.filter(url_name='business_intelligence:customers_kpis').first()

    ActivityLogger.log_read(
        user=request.user,
        obj=None,
        module=module,
        description='visualización de kpis de clientes',
        metadata={
            'filters': filters if filters else {}
        }
    )

    return render(request, template, context)


@login_required
async def export_customers_kpis_data(request):
    warehouses = request.GET.getlist('warehouses')
    routes = request.GET.getlist('routes')
    customer_types = request.GET.getlist('customer_types')
    opinion_leader = request.GET.get('opinion_leader')
    start_registration_date = request.GET.get('start_registration_date')
    end_registration_date = request.GET.get('end_registration_date')
    query_text = request.GET.get('query_text')

    filters = {}
    if routes: filters['routes'] = routes
    if warehouses: filters['warehouses'] = warehouses
    if customer_types: filters['customer_types'] = customer_types
    if query_text: filters['query_text'] = query_text
    if opinion_leader: filters['opinion_leader'] = opinion_leader
    if start_registration_date: filters['start_registration_date'] = start_registration_date
    if end_registration_date: filters['end_registration_date'] = end_registration_date

    user = request.user

    order_contrib = request.POST.get('order_contrib') or request.GET.get('order_contrib', 'net_amount')
    start_contrib = request.POST.get('start_contrib_from') or request.GET.get('start_contrib_from')
    end_contrib = request.POST.get('start_contrib_to') or request.GET.get('start_contrib_to')

    contrib_config = {
        'order_contrib': order_contrib,
        'start_date': start_contrib,
        'end_date': end_contrib
    }

    @sync_to_async
    def generate_file():
        allowed_routes = get_allowed_routes_for_user(user)
        customers_crud = CustomerCrud()
        customers_qs = customers_crud.read(allowed_routes, **filters)
        customers_kpis_service = CustomersKpis(customers_qs)
        csv_content = customers_kpis_service.export_report_data(contrib_config)

        module = SystemModule.objects.filter(url_name='business_intelligence:customers_kpis').first()
        ActivityLogger.log_download(
            user=user,
            obj=None,
            module=module,
            description='Exportación de KPIs de clientes',
            metadata={
                'filters': filters if filters else {}
            }
        )

        return csv_content

    csv_file = await generate_file()
    response = HttpResponse(
        csv_file, 
        content_type='text/csv; charset=utf-8'
    )
    response['Content-Disposition'] = 'attachment; filename="customers_kpis.csv"'
    
    return response


@login_required
def customer_kpis(request, customer_id):
    template = 'business_intelligence/customers_kpis/customer_kpis.html'

    customer_base = get_object_or_404(
        Customer.objects.select_related('customer_type', 'route'), 
        pk=customer_id
    )

    today = date.today()
    date_start = request.GET.get('date_start')
    date_end = request.GET.get('date_end')

    if not date_start:
        date_start = date(today.year, 1, 1).strftime('%Y-%m-%d')
    if not date_end:
        date_end = (date(today.year, today.month, 1) - timedelta(days=1)).strftime('%Y-%m-%d')
    
    product_classes = request.GET.getlist('product_class')
    product_categories = request.GET.getlist('product_category')
    regions = request.GET.getlist('regions')
    warehouses = request.GET.getlist('warehouses')

    filters = {
        'date_start': date_start,
        'date_end': date_end,
        'product_classes': product_classes,
        'product_categories': product_categories,
        'regions': regions,
        'warehouses': warehouses
    }

    builder = CustomerProfileBuilder(customer_base, filters=filters)
    customer_with_kpis = builder.build()

    context = {
        'customer': customer_with_kpis,
        'filter_warehouses': Warehouse.objects.all(),
        'filter_regions': Region.objects.all(),
        'filter_product_classes': ProductClass.objects.all(),
        'filter_product_categories': ProductCategory.objects.all(),
        
        'selected_date_start': date_start,
        'selected_date_end': date_end,
        'selected_warehouses': warehouses,
        'selected_regions': regions,
        'selected_product_class': product_classes,
        'selected_product_category': product_categories,
    }

    metadata = {
        'customer_id': customer_id,
        'date_start': date_start,
        'date_end': date_end,
        'product_classes': product_classes,
        'product_categories': product_categories,
        'regions': regions,
        'warehouses': warehouses
    }

    module = SystemModule.objects.filter(url_name='business_intelligence:customers_kpis').first()

    ActivityLogger.log_read(
        user=request.user,
        obj=customer_with_kpis,
        module=module,
        description=f'Visualización de KPIs del cliente {customer_with_kpis.name.title()}',    
        metadata={
            'filters': metadata if metadata else {}
        }
    )

    return render(request, template, context)


@login_required
def commercial_risk(request):
    template = 'business_intelligence/commercial_risk/commercial_risk.html'
    allowed_routes = get_allowed_routes_for_user(request.user)

    today = date.today()
    date_start = request.POST.get('date_start')
    date_end = request.POST.get('date_end')
    selected_route_id = request.POST.get('route')

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

    metadata = {
        'route_id': selected_route_id,
        'date_start': date_start,
        'date_end': date_end,
    }

    module = SystemModule.objects.filter(url_name='business_intelligence:commercial_risk').first()

    ActivityLogger.log_read(
        user=request.user,
        obj=None,
        module=module,
        description='Visualización de riesgo comercial',
        metadata={
            'filters': metadata if metadata else {}
        }
    )

    return render(request, template, context)

@login_required
async def export_commercial_risk_data(request):
    user = await request.auser()

    today = date.today()
    date_start = request.POST.get('date_start')
    date_end = request.POST.get('date_end')
    selected_route_id = request.POST.get('route')

    print("Filtros recibidos:", date_start, date_end, selected_route_id)

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

        metadata = {
            'route_id': selected_route_id,
            'date_start': date_start,
            'date_end': date_end,
        }

        module = SystemModule.objects.filter(url_name='business_intelligence:commercial_risk').first()
        ActivityLogger.log_download(
            user=user,
            obj=None,
            module=module,
            description='Exportación de riesgo comercial',
            metadata={
                'filters': metadata if metadata else {}
            }
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
def target_scope(request):
    template = 'business_intelligence/target_scope/target_scope.html'
    allowed_routes = get_allowed_routes_for_user(request.user)

    today = date.today()
    date_start = request.GET.get('date_start')
    date_end = request.GET.get('date_end')
    
    if not date_start:
        date_start = today.replace(day=1).strftime('%Y-%m-%d')
    if not date_end:
        date_end = (today.replace(today.year, today.month+1, 1) - timedelta(days=1)).strftime('%Y-%m-%d')

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

    service = TargetScopeService(allowed_routes, filters)
    data = service.get_data()
    
    context = {
        'allowed_routes': allowed_routes,
        'data': data,
        
        'filter_warehouses': Warehouse.objects.all(),
        'filter_product_classes': ProductClass.objects.all(),
        'filter_product_categories': ProductCategory.objects.all(),
        'filter_regions': Region.objects.all(),
        'filter_routes': allowed_routes,
        
        'selected_date_start': date_start,
        'selected_date_end': date_end,
        'selected_product_class': product_classes,
        'selected_product_category': product_categories,
        'selected_routes': routes,
        'selected_warehouses': warehouses,
        'selected_regions': regions,
    }

    module = SystemModule.objects.filter(url_name='business_intelligence:target_scope').first()
    ActivityLogger.log_read(
        user=request.user,
        obj=None,
        module=module,
        description='Visualización de alcance de objetivos',
        metadata={
            'filters': filters if filters else {}
        }
    )
    return render(request, template, context)



@login_required
async def export_target_scope_data(request):
    
    user = await request.auser()
    allowed_routes = await sync_to_async(get_allowed_routes_for_user)(user)

    today = date.today()
    date_start = request.GET.get('date_start')
    date_end = request.GET.get('date_end')
    
    if not date_start:
        date_start = today.replace(day=1).strftime('%Y-%m-%d')
    if not date_end:
        date_end = (today.replace(today.year, today.month+1, 1) - timedelta(days=1)).strftime('%Y-%m-%d')

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

    service = TargetScopeService(allowed_routes, filters)
    excel_data = await sync_to_async(service.export_report_data)()

    response = HttpResponse(
        excel_data, 
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="reporte_alcance_objetivos.xlsx"'
    return response



@login_required
def monthly_breakdown_by_warehouse(request):
    template = 'business_intelligence/monthly_breakdown_by_warehouse/monthly_breakdown_by_warehouse.html'
    user = request.user
    context = {}
    allowed_routes = get_allowed_routes_for_user(user)

    #valiodate which warehouses the user has access to
    if not user.groups.filter(name='acceso global').exists() and not user.is_superuser:
        allowed_warehouse_ids = allowed_routes.values_list('warehouse_id', flat=True)
        
        allowed_warehouses = Warehouse.objects.filter(
            id__in=allowed_warehouse_ids
        ).distinct().values('id', 'name').order_by('id')
    else:
        allowed_warehouses = Warehouse.objects.all().values('id', 'name').order_by('id')

    #catch filters
    today = date.today()
    try:
        year = int(request.GET.get('year', today.year))
    except ValueError:
        year = today.year
    warehouse_id_str = request.GET.get('warehouse')
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

    context['filter_warehouses'] = allowed_warehouses
    context['filter_years'] = filter_years
    context['selected_warehouse'] = str(warehouse)
    context['selected_year'] = str(year)
    context['warehouse_data'] = warehouse_data

    module = SystemModule.objects.filter(url_name='business_intelligence:monthly_breakdown_by_warehouse').first()
    ActivityLogger.log_read(
        user=request.user,
        obj=None,
        module=module,
        description='Visualización de desglose mensual por gerencia',
        metadata={
            'filters': {
                'year': year,
                'warehouse': warehouse,
            }
        }
    )

    return render(request, template, context)

@login_required
def export_monthly_breakdown_data(request):
    allowed_routes = get_allowed_routes_for_user(request.user)
    
    year = int(request.GET.get('year', date.today().year))
    warehouse = request.GET.get('warehouse')
    
    if not warehouse:
        return HttpResponse("No se seleccionó ninguna gerencia.", status=400)
    service = MonthlyBreakdownByWarehouse(year, allowed_routes, warehouse)

    module = SystemModule.objects.filter(url_name='business_intelligence:monthly_breakdown_by_warehouse').first()
    ActivityLogger.log_read(
        user=request.user,
        obj=None,
        module=module,
        description='Exportación de desglose mensual por gerencia',
        metadata={
            'filters': {
                'year': year,
                'warehouse': warehouse,
            }
        }
    )
    
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
    if warehouses: filters['route_warehouse_ids'] = warehouses
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

    module = SystemModule.objects.filter(url_name='business_intelligence:sales_breakdown').first()
    metadata = {
        'dimension': selected_dimension,
        'filters': filters if filters else {}
    }
    ActivityLogger.log_read(
        user=request.user,
        obj=None,
        module=module,
        description='Visualización de desglose de ventas',
        metadata=metadata
    )
    return render(request, template, context)

@login_required
async def export_sales_breakdown_data(request):
    user = await request.auser()
    
    # Extract query parameters outside the sync_to_async thread
    warehouses = request.GET.getlist('warehouses')
    routes = request.GET.getlist('routes')
    product_classes = request.GET.getlist('product_classes')
    product_categories = request.GET.getlist('product_categories')
    months = request.GET.getlist('months')
    dimension = request.GET.get('dimension', 'customer_productclass_product')

    @sync_to_async
    def generate_csv_sync(warehouses, routes, product_classes, product_categories, months, dimension):
        allowed_routes = get_allowed_routes_for_user(user)
        
        filters = {}
        if routes: filters['routes'] = routes
        if warehouses: filters['route_warehouse_ids'] = warehouses
        if product_classes: filters['product_classes'] = product_classes
        if product_categories: filters['product_categories'] = product_categories
        if months: filters['months'] = months
        
        transaction_crud = SaleTransactionCRUD()
        transactions_qs = transaction_crud.read(allowed_routes, **filters)

        service = SalesBreakdownService(transactions_qs, dimension)


        module = SystemModule.objects.filter(url_name='business_intelligence:sales_breakdown').first()
        metadata = {
            'dimension': dimension,
            'filters': filters if filters else {}
        }
        ActivityLogger.log_read(
            user=user,
            obj=None,
            module=module,
            description='Exportación de desglose de ventas',
            metadata=metadata
        )  
        
        return service.get_report_data()

    csv_string = await generate_csv_sync(warehouses, routes, product_classes, product_categories, months, dimension)
    
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

    module = SystemModule.objects.filter(url_name='business_intelligence:unique_customers').first()
    ActivityLogger.log_read(
        user=request.user,
        obj=None,
        module=module,
        description='Visualización de clientes únicos',
        metadata={
            'filters': filters if filters else {}
        }
    )

    return render(request, template, context)








@login_required
def sale_targets(request):
    template = 'sales/sale_targets/sale_targets.html'
    allowed_routes = get_allowed_routes_for_user(request.user)
    
    # Extract filters
    today = date.today()
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