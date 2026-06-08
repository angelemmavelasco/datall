import json
from django.shortcuts import render
from apps.core.utils import get_allowed_routes_for_user
from django.contrib.auth.decorators import login_required
from apps.core.models import Warehouse, ProductClass, ProductCategory
from apps.sales.services.sale_transactions.sale_transactions_crud import SaleTransactionCRUD
from apps.sales.services.sale_targets.sale_targets_crud import SaleTargetCRUD
from apps.business_intelligence.services.sales_dashboard.dashboard_calculator import SalesDashboardCalculator

@login_required
def sales_dashboard(request):
    template = 'business_intelligence/sales_dashboard/sales_dashboard.html'

    allowed_routes = get_allowed_routes_for_user(request.user)

    gerencias = request.GET.getlist('gerencia')
    lugar_venta = request.GET.getlist('lugar_venta')
    product_class = request.GET.getlist('product_class')
    product_category = request.GET.getlist('product_category')
    routes = request.GET.getlist('routes')
    date_start = request.GET.get('date_start')
    date_end = request.GET.get('date_end')

    filters = {}
    if routes: filters['routes'] = routes
    if gerencias: filters['route_warehouse_ids'] = gerencias
    if lugar_venta: filters['warehouses'] = lugar_venta
    if product_class: filters['product_classes'] = product_class
    if product_category: filters['product_categories'] = product_category

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
        'route_id', 'route__name', 'warehouse_id', 'warehouse__name', 
        'product_class_id', 'product_class__name', 'product_class__product_category__name',
        'product_id', 'product__name', 'customer_id', 'customer__name'
    ))

    targets_crud = SaleTargetCRUD()
    targets_qs = targets_crud.read(allowed_routes, **target_filters)
    targets_data = list(targets_qs.values(
        'period', 'target_amount', 'route_id', 'route__name', 'warehouse_id', 'warehouse__name', 'product_class_id'
    ))

    calculator = SalesDashboardCalculator(transactions_data, targets_data)
    
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


        'selected_gerencias': gerencias,
        'selected_lugar_venta': lugar_venta,
        'selected_product_class': product_class,
        'selected_product_category': product_category,
        'selected_routes': routes,
        'selected_date_start': date_start,
        'selected_date_end': date_end,
    }

    return render(request, template, context)


@login_required
def routes_kpis(request):
    context = {}
    return render(request, 'business_intelligence/routes_kpis/routes_kpis.html', context)


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
    context = {}
    return render(request, 'business_intelligence/customers_kpis/customers_kpis.html', context)