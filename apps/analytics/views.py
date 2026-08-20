from apps.customers.services.accounts_receivables import AccountsReceivablesService
import json
from datetime import date
from django.shortcuts import render, redirect
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth.decorators import login_required

from datetime import timedelta
from dateutil.relativedelta import relativedelta
from django.core.paginator import Paginator
from django.utils import timezone

from decimal import Decimal

from apps.sales.services.sale_transactions import SaleTransactionsService
from apps.customers.services.customers import CustomersService
from apps.analytics.filters import SalesDashboardFilter, CustomerKpisFilter
from apps.analytics.services.sales_dashboard import SalesDashboardService
from apps.analytics.services.customer_kpis import CustomerKpisService

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
        warehouse_chart_data = dashboard_service.get_warehouse_chart()
        product_class_chart_data = dashboard_service.get_product_class_chart()
        product_category_chart_data = dashboard_service.get_product_category_chart()

        route_table = dashboard_service.get_route_table()
        product_table = dashboard_service.get_top_products()
        customer_table = dashboard_service.get_top_customers()

        chart_data = {
            'timeline_data': json.dumps(timeline_data),
            'warehouse_chart_data': json.dumps(warehouse_chart_data),
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

    customers_data = customer_kpis_service.get_table_records()

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
        'kpis': customer_kpis_service.get_stats(),
        'customers': page_obj.object_list,
        'page_obj': page_obj,
        'query_string': query_dict.urlencode(),
        'month_headers': [date(timezone.now().year, m, 1) for m in range(1, 13)],
    }

    if request.htmx:
        hx_target = request.headers.get('HX-Target')
        return render(request, 'analytics/customer_kpis/partials/_customer_kpis_rows.html', context)

    return render(request, template, context)

@login_required
def product_kpis_view(request):
    pass

@login_required
def route_kpis_view(request, pk: str = None):
    pass

@login_required
def collections_dashboard_view(request):
    pass

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
