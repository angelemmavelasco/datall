from datetime import date
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from dateutil.relativedelta import relativedelta
from django.shortcuts import redirect
from django.urls import reverse
from django.contrib import messages
from django_q.tasks import async_task

from apps.core.models import GeneratedReport
from apps.customers.services.customers import CustomersService
from apps.sales.services.routes import RoutesService
from apps.sales.services.sale_transactions import SaleTransactionsService
from apps.analytics.filters import CustomerKpisFilter, CommercialRiskFilter, MonthlySaleBreakdownFilter

from time import perf_counter

@login_required
def customer_kpis_export_view(request):
    start = perf_counter()
    # base services
    customer_service = CustomersService(user=request.user)
    customer_qs = customer_service.read_customers()

    # default contrib period
    today = timezone.localdate()
    first_day_curr_month = today.replace(day=1)
    last_day_q = first_day_curr_month - relativedelta(days=1)
    first_day_q = last_day_q.replace(day=1) - relativedelta(months=2)

    req_data = request.GET.copy()
    if not req_data.get('start_contrib'):
        req_data['start_contrib'] = first_day_q.strftime('%Y-%m-%d')
    if not req_data.get('end_contrib'):
        req_data['end_contrib'] = last_day_q.strftime('%Y-%m-%d')

    # set filters
    filter_set = CustomerKpisFilter(req_data, queryset=customer_qs, request=request)
    cleaned_data = filter_set.form.cleaned_data if filter_set.is_valid() else {}

    # serializable cleaned_data dict
    serializable_cleaned_data = {}
    for k, v in cleaned_data.items():
        if isinstance(v, (date, timezone.datetime)):
            serializable_cleaned_data[k] = v.strftime('%Y-%m-%d')
        elif hasattr(v, 'id'):
            serializable_cleaned_data[k] = v.id
        elif isinstance(v, (str, int, float, bool, list, dict)) or v is None:
            serializable_cleaned_data[k] = v
        else:
            serializable_cleaned_data[k] = str(v)

    # create database record for user downloads
    report = GeneratedReport.objects.create(
        user=request.user,
        title="Reporte de KPIs de Clientes",
        module_name="customer_kpis",
        status=GeneratedReport.Status.PENDING,
        filters=serializable_cleaned_data,
    )

    # dispatch async task to Django Q worker
    async_task(
        'apps.analytics.tasks.generate_customer_kpis_report_task',
        request.user.id,
        request.GET.urlencode(),
        serializable_cleaned_data,
        report.id,
    )

    messages.info(request, "Tu reporte de KPIs de clientes se está generando en segundo plano. Aparecerá en tus archivos cuando esté listo. Puedes seguir navegando por la web sin problemas.")
    
    query_str = request.GET.urlencode()
    redirect_url = reverse('analytics:customer_kpis_view')
    if query_str:
        redirect_url += f"?{query_str}"

    end = perf_counter()
    print(f"Customer KPIs export took {end - start} seconds")

    return redirect(redirect_url)


@login_required
def commercial_risk_export_view(request):
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

    serializable_cleaned_data = {}
    for k, v in cleaned_data.items():
        if isinstance(v, (date, timezone.datetime)):
            serializable_cleaned_data[k] = v.strftime('%Y-%m-%d')
        elif hasattr(v, 'id'):
            serializable_cleaned_data[k] = v.id
        elif isinstance(v, (str, int, float, bool, list, dict)) or v is None:
            serializable_cleaned_data[k] = v
        else:
            serializable_cleaned_data[k] = str(v)

    route_name = f"Ruta {selected_route.id}" if selected_route else "General"
    if selected_route and hasattr(selected_route, 'name') and selected_route.name:
        route_name += f" - {selected_route.name.title()}"

    # create database record for user downloads
    report = GeneratedReport.objects.create(
        user=request.user,
        title=f"Reporte de Riesgo Comercial - {route_name}",
        module_name="commercial_risk",
        status=GeneratedReport.Status.PENDING,
        filters=serializable_cleaned_data,
    )

    # dispatch async task to Django Q worker
    async_task(
        'apps.analytics.tasks.generate_commercial_risk_report_task',
        request.user.id,
        request.GET.urlencode(),
        serializable_cleaned_data,
        report.id,
    )

    messages.info(request, "Tu reporte de riesgo comercial se está generando en segundo plano. Aparecerá en tus archivos cuando esté listo. Puedes seguir navegando por la web sin problemas.")

    query_str = request.GET.urlencode()
    redirect_url = reverse('analytics:commercial_risk_view')
    if query_str:
        redirect_url += f"?{query_str}"

    return redirect(redirect_url)


@login_required
def monthly_sale_breakdown_export_view(request):
    start = perf_counter()

    today = timezone.localdate()
    req_data = request.GET.copy()
    if not req_data.get('year'):
        req_data['year'] = str(today.year)

    selected_year = int(req_data.get('year', today.year))

    # base services
    sale_transaction_service = SaleTransactionsService(user=request.user)
    base_tx_qs = sale_transaction_service.read_transactions_by_allowed_routes()

    # set filters
    filter_set = MonthlySaleBreakdownFilter(req_data, queryset=base_tx_qs, request=request)
    cleaned_data = filter_set.form.cleaned_data if filter_set.is_valid() else {}

    # serializable cleaned_data dict
    serializable_cleaned_data = {}
    for k, v in cleaned_data.items():
        if isinstance(v, (date, timezone.datetime)):
            serializable_cleaned_data[k] = v.strftime('%Y-%m-%d')
        elif hasattr(v, 'id'):
            serializable_cleaned_data[k] = v.id
        elif isinstance(v, (str, int, float, bool, list, dict)) or v is None:
            serializable_cleaned_data[k] = v
        elif hasattr(v, '__iter__'):
            serializable_cleaned_data[k] = [item.id if hasattr(item, 'id') else str(item) for item in v]
        else:
            serializable_cleaned_data[k] = str(v)

    # create database record for user downloads
    report = GeneratedReport.objects.create(
        user=request.user,
        title=f"Reporte de Desglose Mensual de Ventas - {selected_year}",
        module_name="monthly_sale_breakdown",
        status=GeneratedReport.Status.PENDING,
        filters=serializable_cleaned_data,
    )

    # dispatch async task to Django Q worker
    async_task(
        'apps.analytics.tasks.generate_monthly_sale_breakdown_report_task',
        request.user.id,
        request.GET.urlencode(),
        serializable_cleaned_data,
        report.id,
    )

    messages.info(request, "Tu reporte de desglose mensual de ventas se está generando en segundo plano. Aparecerá en tus archivos cuando esté listo. Puedes seguir navegando por la web sin problemas.")

    query_str = request.GET.urlencode()
    redirect_url = reverse('analytics:monthly_sale_breakdown_view')
    if query_str:
        redirect_url += f"?{query_str}"

    end = perf_counter()
    print(f"Monthly Sale Breakdown export took {end - start} seconds")

    return redirect(redirect_url)