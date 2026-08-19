import json
from django.shortcuts import render, redirect
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth.decorators import login_required

from datetime import timedelta
from dateutil.relativedelta import relativedelta
from django.core.paginator import Paginator
from django.utils import timezone

from apps.sales.services.sale_transactions import SaleTransactionsService
from apps.customers.services.customers import CustomersService
from apps.analytics.filters import SalesDashboardFilter, CustomerKpisFilter
from apps.analytics.services.sales_dashboard import SalesDashboardService
from apps.analytics.services.customer_kpis import CustomerKpisService

@login_required
def sales_dashboard_view(request):
    template = 'analytics/sales_dashboard/sales_dashboard.html'

    #base service
    tx_service = SaleTransactionsService(user=request.user)
    base_tx_qs = tx_service.read_transactions_by_allowed_routes()
    filter_set = SalesDashboardFilter(request.GET, queryset=base_tx_qs, request=request)
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

    customers_service = CustomersService(user=request.user)
    base_customers_qs = customers_service.read_customers()

    filter_set = CustomerKpisFilter(request.GET, queryset=base_customers_qs, request=request)
    filtered_customers_qs = filter_set.qs

    cleaned_data = filter_set.form.cleaned_data if filter_set.is_valid() else {}
    start_contrib = cleaned_data.get('start_contrib')
    end_contrib = cleaned_data.get('end_contrib')

    kpis_service = CustomerKpisService(
        user=request.user,
        customers_qs=filtered_customers_qs,
        cleaned_data=cleaned_data,
        date_start=start_contrib,
        date_end=end_contrib,
    )

    try:
        customers_data = kpis_service.get_table_records()
        global_kpis = kpis_service.get_stats()
        months_headers = kpis_service.get_months_headers()
    except Exception as e:
        messages.error(request, f'Error al obtener los KPIs de clientes: {e}')
        return redirect(reverse('analytics:customer_kpis_view'))

    paginator = Paginator(customers_data, 100)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    paginated_customers = page_obj.object_list

    query_dict = request.GET.copy()
    if 'page' in query_dict:
        del query_dict['page']
    query_string = query_dict.urlencode()

    today = timezone.now().date()

    context = {
        'filter': filter_set,
        'customers': paginated_customers,
        'page_obj': page_obj,
        'query_string': query_string,
        'global_kpis': global_kpis,
        'months_headers': months_headers,
        'order_contrib': cleaned_data.get('order_contrib', 'net_amount'),
        'selected_start_contrib': kpis_service.date_start,
        'selected_end_contrib': kpis_service.date_end,
        'today': today,
        'end_last_q': today.replace(day=1) - timedelta(days=1),
        'start_last_q': today.replace(day=1) - relativedelta(months=3),
    }

    if request.htmx:
        hx_target = request.headers.get('HX-Target')
        if hx_target == 'customer-kpis-content':
            return render(request, 'analytics/customer_kpis/partials/_customer_kpis_content.html', context)
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
