import json
from datetime import date
from django.shortcuts import render, redirect
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .exports import *

from datetime import timedelta
from dateutil.relativedelta import relativedelta
from django.core.paginator import Paginator
from django.utils import timezone

from decimal import Decimal

#base services qs
from apps.customers.services.accounts_receivables import AccountsReceivablesService, AccountsReceivablesStats
from apps.sales.services.sale_transactions import SaleTransactionsService
from apps.sales.services.sale_targets import SaleTargetsService
from apps.customers.services.customers import CustomersService
from apps.sales.services.routes import RoutesService

#base services analytics
from apps.analytics.filters import SalesDashboardFilter, CustomerKpisFilter, RouteKpisFilter, CollectionsDashboardFilter
from apps.analytics.services.sales_dashboard import SalesDashboardService
from apps.analytics.services.customer_kpis import CustomerKpisService
from apps.analytics.services.route_kpis import RouteKpisService

@login_required
def sales_dashboard_view(request):
    template = 'analytics/sales_dashboard/sales_dashboard.html'

    # Default date range: current month
    today = timezone.localdate()
    first_day_curr_month = today.replace(day=1)
    last_day_curr_month = (first_day_curr_month + relativedelta(months=1)) - timedelta(days=1)

    req_data = request.GET.copy()
    if 'date_start' not in req_data:
        req_data['date_start'] = first_day_curr_month.strftime('%Y-%m-%d')
    if 'date_end' not in req_data:
        req_data['date_end'] = last_day_curr_month.strftime('%Y-%m-%d')

    #base service
    tx_service = SaleTransactionsService(user=request.user)
    base_tx_qs = tx_service.read_transactions_by_allowed_routes()
    filter_set = SalesDashboardFilter(req_data, queryset=base_tx_qs, request=request)
    filtered_tx_qs = filter_set.qs

    cleaned_data = filter_set.form.cleaned_data if filter_set.is_valid() else {}
    date_start = cleaned_data.get('date_start')
    date_end = cleaned_data.get('date_end')

    dashboard_service = SalesDashboardService(
        user=request.user,
        transactions_qs=filtered_tx_qs,
        cleaned_data=cleaned_data,
        date_start=date_start,
        date_end=date_end
    )

    # for htmx lookup
    selected_customer_ids = request.GET.getlist('customer')
    customers_service = CustomersService(user=request.user)
    cust_base = customers_service.read_customers()
    cust_selected = cust_base.filter(pk__in=selected_customer_ids) if selected_customer_ids else cust_base.none()
    cust_remaining = cust_base.exclude(pk__in=selected_customer_ids).order_by('name', 'id')[:20]
    initial_customers = list(cust_selected) + list(cust_remaining)

    try:
        kpis = dashboard_service.get_stats()
        timeline_data = dashboard_service.get_timeline()
        business_unit_chart_data = dashboard_service.get_business_unit_chart()
        product_class_chart_data = dashboard_service.get_product_class_chart()
        product_category_chart_data = dashboard_service.get_product_category_chart()

        route_table = dashboard_service.get_route_table()
        product_table = dashboard_service.get_top_products()
        customer_table = dashboard_service.get_top_customers()

        chart_data = {
            'timeline_data': json.dumps(timeline_data),
            'business_unit_chart_data': json.dumps(business_unit_chart_data),
            'product_class_chart_data': json.dumps(product_class_chart_data),
            'product_category_chart_data': json.dumps(product_category_chart_data),
        }

    except Exception as e:
        messages.error(request, f'Error al obtener los datos para las gráficas: {e}')
        return redirect(reverse('analytics:sales_dashboard_view'))

    context = {
        'filter': filter_set,
        'initial_customers': initial_customers,
        'selected_customer_ids': selected_customer_ids,
        'selected_date_start': date_start,
        'selected_date_end': date_end,
        'kpis': kpis,
        'chart_data': chart_data,
        'route_table': route_table,
        'product_table': product_table,
        'customer_table': customer_table,
    }

    return render(request, template, context)

@login_required
def customer_kpis_view(request):
    template = 'analytics/customer_kpis/customer_kpis.html'

    # base services
    customer_service = CustomersService(user=request.user)
    customer_qs = customer_service.read_customers()

    sale_transaction_service = SaleTransactionsService(user=request.user)
    tx_by_allowed_ctm = sale_transaction_service.read_transactions_by_allowed_customers()

    ar_service = AccountsReceivablesService(user=request.user)
    ar_allowed_ctm = ar_service.read_ars_by_allowed_customers()

    #default contrib period
    today = timezone.localdate()
    first_day_curr_month = today.replace(day=1)
    last_day_q = first_day_curr_month - relativedelta(days=1)
    first_day_q = last_day_q.replace(day=1) - relativedelta(months=2)

    req_data = request.GET.copy()
    if not req_data.get('start_contrib'):
        req_data['start_contrib'] = first_day_q.strftime('%Y-%m-%d')
    if not req_data.get('end_contrib'):
        req_data['end_contrib'] = last_day_q.strftime('%Y-%m-%d')

    #set filters
    filter_set = CustomerKpisFilter(req_data, queryset=customer_qs, request=request)
    filtered_customers_qs = filter_set.qs
    cleaned_data = filter_set.form.cleaned_data if filter_set.is_valid() else {}

    #set main service
    customer_kpis_service = CustomerKpisService(user=request.user, 
        customers_qs=filtered_customers_qs,
        transactions_qs=tx_by_allowed_ctm,
        ars_qs=ar_allowed_ctm,
        date_start=cleaned_data.get('start_contrib'),
        date_end=cleaned_data.get('end_contrib'),
        cleaned_data=cleaned_data,
    )

    customers_data = customer_kpis_service.read_customer_kpis()
    global_kpis = customer_kpis_service.get_stats()

    paginator = Paginator(customers_data, 100)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    query_dict = request.GET.copy()
    if 'page' in query_dict:
        del query_dict['page']

    context = {
        'filter': filter_set,
        'order_contrib': cleaned_data.get('order_contrib') or 'net_amount',
        'selected_start_contrib': customer_kpis_service.date_start,
        'selected_end_contrib': customer_kpis_service.date_end,
        'kpis': global_kpis,
        'customers': page_obj.object_list,
        'page_obj': page_obj,
        'query_string': query_dict.urlencode(),
        'month_headers': [date(today.year, m, 1) for m in range(1, 13)],
    }

    if request.htmx:
        return render(request, 'analytics/customer_kpis/partials/_customer_kpis_rows.html', context)

    return render(request, template, context)

@login_required
def product_kpis_view(request):
    pass

@login_required
def route_kpis_view(request):
    template = 'analytics/route_kpis/route_kpis.html'

    # base services
    customer_service = CustomersService(user=request.user)
    customer_qs = customer_service.read_customers()

    sale_transaction_service = SaleTransactionsService(user=request.user)
    tx_by_allowed_ctm = sale_transaction_service.read_transactions_by_allowed_customers()

    ar_service = AccountsReceivablesService(user=request.user)
    ar_allowed_ctm = ar_service.read_ars_by_allowed_customers()

    targets_service = SaleTargetsService(user=request.user)
    targets_qs = targets_service.read_sale_targets()

    routes_service = RoutesService(user=request.user)
    allowed_routes = routes_service.read_routes().order_by('id')
    first_route = allowed_routes.first()

    # default date range current month
    today = timezone.localdate()
    first_day_curr_month = today.replace(day=1)
    last_day_curr_month = (first_day_curr_month + relativedelta(months=1)) - timedelta(days=1)

    req_data = request.GET.copy()
    if not req_data.get('route') and first_route:
        req_data['route'] = str(first_route.id)
    if not req_data.get('date_start'):
        req_data['date_start'] = first_day_curr_month.strftime('%Y-%m-%d')
    if not req_data.get('date_end'):
        req_data['date_end'] = last_day_curr_month.strftime('%Y-%m-%d')

    # set filters
    filter_set = RouteKpisFilter(req_data, queryset=allowed_routes, request=request)
    cleaned_data = filter_set.form.cleaned_data if filter_set.is_valid() else {}

    selected_route = cleaned_data.get('route') or allowed_routes.filter(id=req_data.get('route')).first() or first_route
    date_start = cleaned_data.get('date_start') or req_data.get('date_start')
    date_end = cleaned_data.get('date_end') or req_data.get('date_end')

    # route service
    route_service = RouteKpisService(
        user=request.user,
        route=selected_route,
        customers_qs=customer_qs,
        transactions_qs=tx_by_allowed_ctm,
        ars_qs=ar_allowed_ctm,
        targets_qs=targets_qs,
        date_start=date_start,
        date_end=date_end,
        cleaned_data=cleaned_data,
    )
    route_data = route_service.read_route_kpis()
    kpis = route_service.stats()

    chart_data = {
        'achievement_by_month': json.dumps(route_data.get('achievement_by_month', {})) if route_data else '{}',
        'customer_churn': json.dumps(route_data.get('customer_churn', {})) if route_data else '{}',
        'sale_by_customer_category': json.dumps(route_data.get('sale_by_customer_category', [])) if route_data else '[]',
    }

    query_dict = request.GET.copy()

    context = {
        'filter': filter_set,
        'selected_route': selected_route,
        'allowed_routes': allowed_routes,
        'selected_date_start': route_service.date_start,
        'selected_date_end': route_service.date_end,
        'route': route_data,
        'kpis': kpis,
        'chart_data': chart_data,
        'query_string': query_dict.urlencode(),
    }
    return render(request, template, context)


@login_required
def collections_dashboard_view(request):
    template = 'analytics/collection_dashboard/collection_dashboard.html'
    service = AccountsReceivablesService(user=request.user)
    stats_service = AccountsReceivablesStats(accounts_receivables_service=service)

    perspective = request.GET.get('perspective', 'current_customers')
    if perspective == 'emitting_routes':
        ars_qs = service.read_ars_by_allowed_routes()
    else:
        ars_qs = service.read_ars_by_allowed_customers()

    filter_set = CollectionsDashboardFilter(request.GET or None, queryset=ars_qs, request=request)
    filtered_ars_qs = filter_set.qs

    # for htmx lookup in customer filter
    selected_customer_ids = request.GET.getlist('customer')
    customers_service = CustomersService(user=request.user)
    cust_base = customers_service.read_customers()
    cust_selected = cust_base.filter(pk__in=selected_customer_ids) if selected_customer_ids else cust_base.none()
    cust_remaining = cust_base.exclude(pk__in=selected_customer_ids).order_by('name', 'id')[:20]
    initial_customers = list(cust_selected) + list(cust_remaining)

    #general KPIs
    kpis = stats_service.stats(qs=filtered_ars_qs)

    #customer breakdown pagination
    customer_breakdown_qs = stats_service.customer_breakdown(qs=filtered_ars_qs)
    paginator = Paginator(customer_breakdown_qs, 100)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    query_dict = request.GET.copy()
    if 'page' in query_dict:
        del query_dict['page']

    context = {
        'filter': filter_set,
        'initial_customers': initial_customers,
        'selected_customer_ids': selected_customer_ids,
        'current_perspective': perspective,
        'selected_issue_date_start': request.GET.get('issue_date_start', ''),
        'selected_issue_date_end': request.GET.get('issue_date_end', ''),
        'kpis': kpis,
        'collections_by_customer': page_obj.object_list,
        'page_obj': page_obj,
        'query_string': query_dict.urlencode(),
    }

    if request.htmx:
        return render(request, 'analytics/collection_dashboard/partials/_collections_customer_rows.html', context)

    return render(request, template, context)

@login_required
def commercial_risk_view(request):
    pass

@login_required
def target_achievement_view(request):
    pass

@login_required
def annual_sale_breakdown_view(request):
    pass

@login_required
def monthly_sale_breakdown_view(request):
    pass

@login_required
def business_unit_sale_breakdown_view(request):
    pass

@login_required
def unique_customer_count_view(request):
    pass
