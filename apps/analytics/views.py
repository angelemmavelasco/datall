import json
from datetime import date
from django.shortcuts import render, redirect
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from .exports import *
from time import perf_counter

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
from apps.analytics.filters import SalesDashboardFilter, CustomerKpisFilter, RouteKpisFilter, CommercialRiskFilter, CollectionsDashboardFilter, TargetAchievementFilter, YearlySaleBreakdownFilter, MonthlySaleBreakdownFilter
from apps.analytics.services.sales_dashboard import SalesDashboardService
from apps.analytics.services.customer_kpis import CustomerKpisService
from apps.analytics.services.route_kpis import RouteKpisService
from apps.analytics.services.commercial_risk import CommercialRiskService
from apps.analytics.services.target_achievement import TargetAchievementService
from apps.analytics.services.yearly_sale_breakdown import YearlySaleBreakdownService
from apps.analytics.services.monthly_sale_breakdown import MonthlySaleBreakdownService

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

    from apps.customers.filters import AccountsReceivableFilter
    filter_set = AccountsReceivableFilter(request.GET or None, queryset=ars_qs, request=request)
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
        'selected_issue_date_start': request.GET.get('issue_date_from') or request.GET.get('issue_date_start', ''),
        'selected_issue_date_end': request.GET.get('issue_date_to') or request.GET.get('issue_date_end', ''),
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
    template = 'analytics/commercial_risk/commercial_risk.html'

    # base services
    customer_service = CustomersService(user=request.user)
    customer_qs = customer_service.read_customers()

    sale_transaction_service = SaleTransactionsService(user=request.user)
    tx_by_allowed_ctm = sale_transaction_service.read_transactions_by_allowed_customers()

    routes_service = RoutesService(user=request.user)
    allowed_routes = routes_service.read_routes().order_by('id')
    first_route = allowed_routes.first()

    # default date range from Jan 1 of previous year to last closed month
    today = timezone.localdate()
    end_q_date = today.replace(day=1) - relativedelta(days=1)
    default_start_date = date(today.year - 1, 1, 1)

    req_data = request.GET.copy()
    if not req_data.get('route') and first_route:
        req_data['route'] = str(first_route.id)
    if not req_data.get('date_start'):
        req_data['date_start'] = default_start_date.strftime('%Y-%m-%d')
    if not req_data.get('date_end'):
        req_data['date_end'] = end_q_date.strftime('%Y-%m-%d')

    # set filters
    filter_set = CommercialRiskFilter(req_data, queryset=allowed_routes, request=request)
    cleaned_data = filter_set.form.cleaned_data if filter_set.is_valid() else {}

    selected_route = cleaned_data.get('route') or allowed_routes.filter(id=req_data.get('route')).first() or first_route
    date_start = cleaned_data.get('date_start') or req_data.get('date_start')
    date_end = cleaned_data.get('date_end') or req_data.get('date_end')

    # commercial risk service
    risk_service = CommercialRiskService(
        user=request.user,
        route=selected_route,
        customers_qs=customer_qs,
        transactions_qs=tx_by_allowed_ctm,
        date_start=date_start,
        date_end=date_end,
        cleaned_data=cleaned_data,
    )
    kpis = risk_service.stats()
    timeline_chart = risk_service._get_timeline_chart()
    churn_data = risk_service._get_customer_churn()
    new_customers_data = risk_service._get_monthly_new_customers()
    coverage_data = risk_service._get_monthly_portafolio_coverage()
    volatility_data = risk_service._get_volatility_and_volume()
    momentum_bias_data = risk_service._get_momentum_and_bias()
    category_composition_data = risk_service._get_monthly_category_composition()
    monetary_contrib_data = risk_service._get_monetary_contrib_by_category()

    chart_data = {
        'timeline_chart': json.dumps(timeline_chart),
        'customer_churn': json.dumps(churn_data),
        'new_and_active_customers': json.dumps({
            'months': new_customers_data['months'],
            'new_customers': new_customers_data['new_customers'],
            'new_customer_ids': new_customers_data['new_customer_ids'],
            'portfolio_coverage': coverage_data['portfolio_coverage'],
            'active_customers': coverage_data['active_customers'],
            'active_customer_ids': coverage_data['active_customer_ids'],
            'total_portfolio': coverage_data['total_portfolio'],
        }),
        'volatility_and_volume': json.dumps(volatility_data),
        'momentum_and_bias': json.dumps(momentum_bias_data),
        'category_composition': json.dumps(category_composition_data),
        'monetary_contrib_by_category': json.dumps(monetary_contrib_data),
    }

    query_dict = request.GET.copy()

    context = {
        'filter': filter_set,
        'selected_route': selected_route,
        'allowed_routes': allowed_routes,
        'selected_date_start': risk_service.date_start,
        'selected_date_end': risk_service.date_end,
        'selected_start_q_date': risk_service.start_q_date,
        'selected_end_q_date': risk_service.end_q_date,
        'kpis': kpis,
        'chart_data': chart_data,
        'query_string': query_dict.urlencode(),
    }
    return render(request, template, context)

@login_required
def target_achievement_view(request):
    template = 'analytics/target_achievement/target_achievement.html'

    #default current month
    today = timezone.localdate()
    first_day_curr_month = today.replace(day=1)
    if today.month == 12:
        last_day_curr_month = date(today.year, 12, 31)
    else:
        last_day_curr_month = date(today.year, today.month + 1, 1) - timedelta(days=1)

    req_data = request.GET.copy()
    if 'date_start' not in req_data:
        req_data['date_start'] = first_day_curr_month.strftime('%Y-%m-%d')
    if 'date_end' not in req_data:
        req_data['date_end'] = last_day_curr_month.strftime('%Y-%m-%d')

    #base services
    targets_service = SaleTargetsService(user=request.user)
    base_targets_qs = targets_service.read_sale_targets()

    tx_service = SaleTransactionsService(user=request.user)
    base_tx_qs = tx_service.read_transactions_by_allowed_routes()

    customers_service = CustomersService(user=request.user)
    base_customers_qs = customers_service.read_customers()

    routes_service = RoutesService(user=request.user)
    allowed_routes_qs = routes_service.get_allowed_routes(can_view=True, can_edit=False)

    filter_set = TargetAchievementFilter(req_data, queryset=base_targets_qs, request=request)
    filtered_targets_qs = filter_set.qs

    cleaned_data = filter_set.form.cleaned_data if filter_set.is_valid() else {}
    date_start = cleaned_data.get('date_start') or req_data.get('date_start')
    date_end = cleaned_data.get('date_end') or req_data.get('date_end')

    #apply filters
    filtered_tx_qs = base_tx_qs
    if cleaned_data.get('route'):
        filtered_tx_qs = filtered_tx_qs.filter(route__in=cleaned_data['route'])
    if cleaned_data.get('product_class'):
        filtered_tx_qs = filtered_tx_qs.filter(product_class__in=cleaned_data['product_class'])
    if cleaned_data.get('product_category'):
        filtered_tx_qs = filtered_tx_qs.filter(product_class__product_category__in=cleaned_data['product_category'])
    if cleaned_data.get('business_unit'):
        filtered_tx_qs = filtered_tx_qs.filter(route__business_unit__in=cleaned_data['business_unit'])

    achievement_service = TargetAchievementService(
        user=request.user,
        targets_qs=filtered_targets_qs,
        transactions_qs=filtered_tx_qs,
        customers_qs=base_customers_qs,
        routes_qs=allowed_routes_qs,
        date_start=date_start,
        date_end=date_end,
        cleaned_data=cleaned_data
    )

    data = achievement_service.get_target_achievement_data()

    context = {
        'filter': filter_set,
        'data': data,
        'selected_date_start': achievement_service.date_start_dt.strftime('%Y-%m-%d'),
        'selected_date_end': achievement_service.date_end_dt.strftime('%Y-%m-%d'),
        'total_b_days': achievement_service.total_b_days,
        'elapsed_b_days': achievement_service.elapsed_b_days,
        'query_string': req_data.urlencode(),
    }
    return render(request, template, context)

@login_required
def yearly_sale_breakdown_view(request):
    init = perf_counter()
    template = 'analytics/yearly_sale_breakdown/yearly_sale_breakdown.html'

    req_data = request.GET.copy()
    if not req_data.get('dimension'):
        req_data['dimension'] = 'customer_productclass_product'

    dimension = req_data.get('dimension', 'customer_productclass_product')

    # perspective determination
    sale_transaction_service = SaleTransactionsService(user=request.user)
    perspective = YearlySaleBreakdownService.get_perspective(dimension)
    if perspective == 'customers':
        tx_qs = sale_transaction_service.read_transactions_by_allowed_customers()
    else:
        tx_qs = sale_transaction_service.read_transactions_by_allowed_routes()

    # filters
    filter_set = YearlySaleBreakdownFilter(req_data, queryset=tx_qs, request=request)
    filtered_tx_qs = filter_set.qs

    # service initialization
    breakdown_service = YearlySaleBreakdownService(
        queryset=filtered_tx_qs,
        dimension=dimension,
        user=request.user,
    )

    # level 1 pagination
    l1_qs = breakdown_service.get_level_1_queryset()
    paginator = Paginator(l1_qs, 50)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # level 1 ids for the current page
    l1_id_field = breakdown_service.l1_id_field
    top_l1_ids = [
        item[l1_id_field] for item in page_obj.object_list if item.get(l1_id_field) is not None
    ]

    # aggregated calculation for the page data
    pivot_data = breakdown_service.get_pivot_data(top_l1_ids)

    query_dict = req_data.copy()
    if 'page' in query_dict:
        del query_dict['page']
    
    end = perf_counter()
    perf = end - init
    
    print(f'yearly_sale_breakdown_view: {perf} seconds')

    context = {
        'filter': filter_set,
        'dimension': dimension,
        'dimension_label': breakdown_service.dimension_config.get('label', ''),
        'available_years': breakdown_service.sorted_years,
        'years': breakdown_service.sorted_years,
        'pivot_data': pivot_data,
        'page_obj': page_obj,
        'query_string': query_dict.urlencode(),
        'perf': perf,
    }

    if request.htmx:
        return render(
            request,
            'analytics/yearly_sale_breakdown/partials/_yearly_sale_breakdown_rows.html',
            context,
        )

    return render(request, template, context)

@login_required
def monthly_sale_breakdown_view(request):
    template = 'analytics/monthly_sale_breakdown/monthly_sale_breakdown.html'

    today = timezone.localdate()
    req_data = request.GET.copy()
    if not req_data.get('year'):
        req_data['year'] = str(today.year)

    selected_year = int(req_data.get('year', today.year))

    #base services
    sale_transaction_service = SaleTransactionsService(user=request.user)
    base_tx_qs = sale_transaction_service.read_transactions_by_allowed_routes()

    targets_service = SaleTargetsService(user=request.user)
    base_targets_qs = targets_service.read_sale_targets()

    customers_service = CustomersService(user=request.user)
    base_customers_qs = customers_service.read_customers()

    ar_service = AccountsReceivablesService(user=request.user)
    base_ars_qs = ar_service.read_ars_by_allowed_customers()

    routes_service = RoutesService(user=request.user)
    allowed_routes_qs = routes_service.read_routes().order_by('id')

    #filter
    filter_set = MonthlySaleBreakdownFilter(req_data, queryset=base_tx_qs, request=request)
    filtered_tx_qs = filter_set.qs
    cleaned_data = filter_set.form.cleaned_data if filter_set.is_valid() else {}

    breakdown_service = MonthlySaleBreakdownService(
        user=request.user,
        targets_qs=base_targets_qs,
        transactions_qs=filtered_tx_qs,
        customers_qs=base_customers_qs,
        ars_qs=base_ars_qs,
        routes_qs=allowed_routes_qs,
        year=selected_year,
        cleaned_data=cleaned_data
    )

    breakdown_data = breakdown_service.get_data()

    query_dict = req_data.copy()

    context = {
        'filter': filter_set,
        'selected_year': selected_year,
        'breakdown_data': breakdown_data,
        'query_string': query_dict.urlencode(),
    }

    return render(request, template, context)

@login_required
def business_unit_sale_breakdown_view(request):
    pass

@login_required
def unique_customer_count_view(request):
    pass
