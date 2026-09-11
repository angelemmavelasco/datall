import os
import uuid
from datetime import date, timedelta
from django.conf import settings
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
from apps.sales.services.sale_targets import SaleTargetsService
from apps.human_resources.models import BusinessUnit
from apps.customers.services.accounts_receivables import AccountsReceivablesService
from apps.analytics.filters import CustomerKpisFilter, CommercialRiskFilter, MonthlySaleBreakdownFilter, TargetAchievementFilter, YearlySaleBreakdownFilter
from apps.analytics.services.customer_kpis import CustomerKpisService, CustomerKpisExports
from apps.analytics.services.commercial_risk import CommercialRiskService, CommercialRiskExports
from apps.analytics.services.monthly_sale_breakdown import MonthlySaleBreakdownService, MonthlySaleBreakdownExports
from apps.analytics.services.yearly_sale_breakdown import YearlySaleBreakdownService, YearlySaleBreakdownExports
from apps.analytics.services.target_achievement import TargetAchievementService, TargetAchievementExports


from time import perf_counter


def _make_serializable(val):
    if val is None or isinstance(val, (int, float, bool, str)):
        return val
    if isinstance(val, (date, timezone.datetime)):
        return val.strftime('%Y-%m-%d')
    if hasattr(val, 'pk'):
        return val.pk
    if hasattr(val, 'id'):
        return val.id
    if isinstance(val, dict):
        return {k: _make_serializable(v) for k, v in val.items()}
    if hasattr(val, '__iter__') and not isinstance(val, (str, bytes)):
        return [_make_serializable(item) for item in val]
    return str(val)


@login_required
def customer_kpis_export_view(request):
    start = perf_counter()
    user = request.user

    customer_service = CustomersService(user=user)
    customer_qs = customer_service.read_customers()

    sale_transaction_service = SaleTransactionsService(user=user)
    tx_by_allowed_ctm = sale_transaction_service.read_transactions_by_allowed_customers()

    ar_service = AccountsReceivablesService(user=user)
    ar_allowed_ctm = ar_service.read_ars_by_allowed_customers()

    today = timezone.localdate()
    first_day_curr_month = today.replace(day=1)
    last_day_q = first_day_curr_month - relativedelta(days=1)
    first_day_q = last_day_q.replace(day=1) - relativedelta(months=2)

    req_data = request.GET.copy()
    if not req_data.get('start_contrib'):
        req_data['start_contrib'] = first_day_q.strftime('%Y-%m-%d')
    if not req_data.get('end_contrib'):
        req_data['end_contrib'] = last_day_q.strftime('%Y-%m-%d')

    filter_set = CustomerKpisFilter(req_data, queryset=customer_qs, request=request)
    filtered_customers_qs = filter_set.qs
    cleaned_data = filter_set.form.cleaned_data if filter_set.is_valid() else {}
    serializable_cleaned_data = {k: _make_serializable(v) for k, v in cleaned_data.items()}

    customer_kpis_service = CustomerKpisService(
        user=user,
        customers_qs=filtered_customers_qs,
        transactions_qs=tx_by_allowed_ctm,
        ars_qs=ar_allowed_ctm,
        date_start=cleaned_data.get('start_contrib'),
        date_end=cleaned_data.get('end_contrib'),
        cleaned_data=cleaned_data,
    )

    exports_service = CustomerKpisExports(customer_kpis_service=customer_kpis_service)
    excel_file = exports_service.export_customer_kpis_report()
    file_bytes = excel_file.getvalue()

    timestamp_str = timezone.localdate().strftime('%Y%m%d_%H%M%S')
    filename = f"reporte_kpis_clientes_{timestamp_str}.xlsx"

    try:
        temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp_reports')
        os.makedirs(temp_dir, exist_ok=True)
        temp_filename = f"{uuid.uuid4().hex}.xlsx"
        temp_file_path = os.path.join(temp_dir, temp_filename)
        with open(temp_file_path, 'wb') as f:
            f.write(file_bytes)

        report = GeneratedReport.objects.create(
            user=user,
            title="Reporte de KPIs de Clientes",
            module_name="customer_kpis",
            status=GeneratedReport.Status.PENDING,
            filters=serializable_cleaned_data,
            file_size=len(file_bytes),
        )

        async_task(
            'apps.core.tasks.save_generated_report_file_task',
            report.id,
            temp_file_path,
            filename,
        )
    except Exception as bg_err:
        print(f"[CUSTOMER KPIS EXPORT] Error queuing background persistence: {bg_err}", flush=True)

    end = perf_counter()
    print(f"Customer KPIs direct export took {end - start:.2f} seconds")

    response = HttpResponse(
        file_bytes,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Content-Length"] = len(file_bytes)
    return response


@login_required
def commercial_risk_export_view(request):
    start = perf_counter()
    user = request.user

    routes_service = RoutesService(user=user)
    allowed_routes = routes_service.read_routes().order_by('id')
    first_route = allowed_routes.first()

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

    filter_set = CommercialRiskFilter(req_data, queryset=allowed_routes, request=request)
    cleaned_data = filter_set.form.cleaned_data if filter_set.is_valid() else {}

    selected_route = cleaned_data.get('route') or allowed_routes.filter(id=req_data.get('route')).first() or first_route

    customer_service = CustomersService(user=user)
    customer_qs = customer_service.read_customers()

    sale_transaction_service = SaleTransactionsService(user=user)
    tx_by_allowed_ctm = sale_transaction_service.read_transactions_by_allowed_customers()

    risk_service = CommercialRiskService(
        user=user,
        route=selected_route,
        customers_qs=customer_qs,
        transactions_qs=tx_by_allowed_ctm,
        date_start=cleaned_data.get('date_start'),
        date_end=cleaned_data.get('date_end'),
        cleaned_data=cleaned_data,
    )

    exports_service = CommercialRiskExports(commercial_risk_service=risk_service)
    excel_file = exports_service.export_commercial_risk_report()
    file_bytes = excel_file.getvalue()

    route_str = selected_route.id if selected_route else 'general'
    timestamp_str = timezone.localdate().strftime('%Y%m%d_%H%M%S')
    filename = f"reporte_riesgo_comercial_ruta_{route_str}_{timestamp_str}.xlsx"

    serializable_cleaned_data = {k: _make_serializable(v) for k, v in cleaned_data.items()}
    route_name = f"Ruta {selected_route.id}" if selected_route else "General"
    if selected_route and hasattr(selected_route, 'name') and selected_route.name:
        route_name += f" - {selected_route.name.title()}"

    try:
        temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp_reports')
        os.makedirs(temp_dir, exist_ok=True)
        temp_filename = f"{uuid.uuid4().hex}.xlsx"
        temp_file_path = os.path.join(temp_dir, temp_filename)
        with open(temp_file_path, 'wb') as f:
            f.write(file_bytes)

        report = GeneratedReport.objects.create(
            user=user,
            title=f"Reporte de Riesgo Comercial - {route_name}",
            module_name="commercial_risk",
            status=GeneratedReport.Status.PENDING,
            filters=serializable_cleaned_data,
            file_size=len(file_bytes),
        )

        async_task(
            'apps.core.tasks.save_generated_report_file_task',
            report.id,
            temp_file_path,
            filename,
        )
    except Exception as bg_err:
        print(f"[COMMERCIAL RISK EXPORT] Error queuing background persistence: {bg_err}", flush=True)

    end = perf_counter()
    print(f"Commercial risk direct export took {end - start:.2f} seconds")

    response = HttpResponse(
        file_bytes,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Content-Length"] = len(file_bytes)
    return response


@login_required
def monthly_sale_breakdown_export_view(request):
    start = perf_counter()
    user = request.user

    today = timezone.localdate()
    req_data = request.GET.copy()
    if not req_data.get('year'):
        req_data['year'] = str(today.year)

    try:
        selected_year = int(req_data.get('year', today.year))
    except (ValueError, TypeError):
        selected_year = today.year

    sale_transaction_service = SaleTransactionsService(user=user)
    base_tx_qs = sale_transaction_service.read_transactions_by_allowed_routes()

    targets_service = SaleTargetsService(user=user)
    base_targets_qs = targets_service.read_sale_targets()

    customers_service = CustomersService(user=user)
    base_customers_qs = customers_service.read_customers()

    ar_service = AccountsReceivablesService(user=user)
    base_ars_qs = ar_service.read_ars_by_allowed_customers()

    routes_service = RoutesService(user=user)
    allowed_routes_qs = routes_service.read_routes().order_by('id')

    filter_set = MonthlySaleBreakdownFilter(req_data, queryset=base_tx_qs, request=request)
    filtered_tx_qs = filter_set.qs
    cleaned_data = filter_set.form.cleaned_data if filter_set.is_valid() else {}
    serializable_cleaned_data = {k: _make_serializable(v) for k, v in cleaned_data.items()}

    breakdown_service = MonthlySaleBreakdownService(
        user=user,
        targets_qs=base_targets_qs,
        transactions_qs=filtered_tx_qs,
        customers_qs=base_customers_qs,
        ars_qs=base_ars_qs,
        routes_qs=allowed_routes_qs,
        year=selected_year,
        cleaned_data=cleaned_data,
    )

    exports_service = MonthlySaleBreakdownExports(monthly_sale_breakdown_service=breakdown_service)
    excel_file = exports_service.export_monthly_sale_breakdown_report()
    file_bytes = excel_file.getvalue()

    timestamp_str = timezone.localdate().strftime('%Y%m%d_%H%M%S')
    filename = f"reporte_desglose_mensual_ventas_{selected_year}_{timestamp_str}.xlsx"

    try:
        temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp_reports')
        os.makedirs(temp_dir, exist_ok=True)
        temp_filename = f"{uuid.uuid4().hex}.xlsx"
        temp_file_path = os.path.join(temp_dir, temp_filename)
        with open(temp_file_path, 'wb') as f:
            f.write(file_bytes)

        report = GeneratedReport.objects.create(
            user=user,
            title=f"Reporte de Desglose Mensual de Ventas - {selected_year}",
            module_name="monthly_sale_breakdown",
            status=GeneratedReport.Status.PENDING,
            filters=serializable_cleaned_data,
            file_size=len(file_bytes),
        )

        async_task(
            'apps.core.tasks.save_generated_report_file_task',
            report.id,
            temp_file_path,
            filename,
        )
    except Exception as bg_err:
        print(f"[MONTHLY BREAKDOWN EXPORT] Error queuing background persistence: {bg_err}", flush=True)

    end = perf_counter()
    print(f"Monthly Sale Breakdown direct export took {end - start:.2f} seconds")

    response = HttpResponse(
        file_bytes,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Content-Length"] = len(file_bytes)
    return response


@login_required
def target_achievement_export_view(request):
    start = perf_counter()

    today = timezone.localdate()
    first_day_curr_month = today.replace(day=1)
    if today.month == 12:
        last_day_curr_month = date(today.year, 12, 31)
    else:
        last_day_curr_month = date(today.year, today.month + 1, 1) - timedelta(days=1)

    req_data = request.GET.copy()
    if not req_data.get('date_start'):
        req_data['date_start'] = first_day_curr_month.strftime('%Y-%m-%d')
    if not req_data.get('date_end'):
        req_data['date_end'] = last_day_curr_month.strftime('%Y-%m-%d')

    user = request.user

    targets_service = SaleTargetsService(user=user)
    base_targets_qs = targets_service.read_sale_targets()

    tx_service = SaleTransactionsService(user=user)
    base_tx_qs = tx_service.read_transactions_by_allowed_routes()

    customers_service = CustomersService(user=user)
    base_customers_qs = customers_service.read_customers()

    routes_service = RoutesService(user=user)
    allowed_routes_qs = routes_service.get_allowed_routes(can_view=True, can_edit=False)

    filter_set = TargetAchievementFilter(req_data, queryset=base_targets_qs, request=user)
    filtered_targets_qs = filter_set.qs
    parsed_cleaned_data = filter_set.form.cleaned_data if filter_set.is_valid() else {}
    cleaned_data = parsed_cleaned_data
    serializable_cleaned_data = {k: _make_serializable(v) for k, v in cleaned_data.items()}

    filtered_tx_qs = base_tx_qs
    filtered_routes_qs = allowed_routes_qs
    filtered_customers_qs = base_customers_qs

    if cleaned_data.get('region'):
        selected_region_ids = set(r.pk if hasattr(r, 'pk') else r for r in cleaned_data['region'])
        all_bu_ids = set(selected_region_ids)
        current_parents = set(selected_region_ids)
        while current_parents:
            child_ids = set(
                BusinessUnit.objects.filter(parent_id__in=current_parents).values_list('id', flat=True)
            )
            new_ids = child_ids - all_bu_ids
            if not new_ids:
                break
            all_bu_ids.update(new_ids)
            current_parents = new_ids

        filtered_tx_qs = filtered_tx_qs.filter(route__business_unit_id__in=all_bu_ids)
        filtered_routes_qs = filtered_routes_qs.filter(business_unit_id__in=all_bu_ids)
        filtered_customers_qs = filtered_customers_qs.filter(
            assignments__route__business_unit_id__in=all_bu_ids
        )

    if cleaned_data.get('business_unit'):
        bu_ids = [bu.pk if hasattr(bu, 'pk') else bu for bu in cleaned_data['business_unit']]
        filtered_tx_qs = filtered_tx_qs.filter(route__business_unit_id__in=bu_ids)
        filtered_routes_qs = filtered_routes_qs.filter(business_unit_id__in=bu_ids)
        filtered_customers_qs = filtered_customers_qs.filter(
            assignments__route__business_unit_id__in=bu_ids
        )

    if cleaned_data.get('route'):
        route_ids = [r.pk if hasattr(r, 'pk') else r for r in cleaned_data['route']]
        filtered_tx_qs = filtered_tx_qs.filter(route_id__in=route_ids)
        filtered_routes_qs = filtered_routes_qs.filter(id__in=route_ids)
        filtered_customers_qs = filtered_customers_qs.filter(
            assignments__route_id__in=route_ids
        )

    if cleaned_data.get('product_category'):
        filtered_tx_qs = filtered_tx_qs.filter(product_class__product_category__in=cleaned_data['product_category'])

    if cleaned_data.get('product_class'):
        filtered_tx_qs = filtered_tx_qs.filter(product_class__in=cleaned_data['product_class'])

    achievement_service = TargetAchievementService(
        user=user,
        targets_qs=filtered_targets_qs,
        transactions_qs=filtered_tx_qs,
        customers_qs=filtered_customers_qs,
        routes_qs=filtered_routes_qs,
        date_start=cleaned_data.get('date_start'),
        date_end=cleaned_data.get('date_end'),
        cleaned_data=cleaned_data
    )

    exports_service = TargetAchievementExports(target_achievement_service=achievement_service)
    excel_file = exports_service.export_target_achievement_report()
    file_bytes = excel_file.getvalue()

    d_start_str = achievement_service.date_start_dt.strftime('%Y%m%d')
    d_end_str = achievement_service.date_end_dt.strftime('%Y%m%d')
    timestamp_str = timezone.localdate().strftime('%Y%m%d_%H%M%S')
    filename = f"reporte_alcance_objetivos_{d_start_str}_{d_end_str}_{timestamp_str}.xlsx"

    try:
        temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp_reports')
        os.makedirs(temp_dir, exist_ok=True)
        temp_filename = f"{uuid.uuid4().hex}.xlsx"
        temp_file_path = os.path.join(temp_dir, temp_filename)
        with open(temp_file_path, 'wb') as f:
            f.write(file_bytes)

        report = GeneratedReport.objects.create(
            user=user,
            title="Reporte de Alcance de Objetivos",
            module_name="target_achievement",
            status=GeneratedReport.Status.PENDING,
            filters=serializable_cleaned_data,
            file_size=len(file_bytes),
        )

        async_task(
            'apps.core.tasks.save_generated_report_file_task',
            report.id,
            temp_file_path,
            filename,
        )
    except Exception as bg_err:
        print(f"[TARGET ACHIEVEMENT EXPORT] Error queuing background persistence: {bg_err}", flush=True)

    end = perf_counter()
    print(f"Target achievement direct export took {end - start:.2f} seconds")

    response = HttpResponse(
        file_bytes,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Content-Length"] = len(file_bytes)
    return response


@login_required
def yearly_sale_breakdown_export_view(request):
    start = perf_counter()
    user = request.user

    req_data = request.GET.copy()
    if not req_data.get('dimension'):
        req_data['dimension'] = 'customer_productclass_product'

    dimension = req_data.get('dimension', 'customer_productclass_product')

    sale_transaction_service = SaleTransactionsService(user=user)
    perspective = YearlySaleBreakdownService.get_perspective(dimension)
    if perspective == 'customers':
        tx_qs = sale_transaction_service.read_transactions_by_allowed_customers()
    else:
        tx_qs = sale_transaction_service.read_transactions_by_allowed_routes()

    filter_set = YearlySaleBreakdownFilter(req_data, queryset=tx_qs, request=request)
    filtered_tx_qs = filter_set.qs
    cleaned_data = filter_set.form.cleaned_data if filter_set.is_valid() else {}

    serializable_cleaned_data = {k: _make_serializable(v) for k, v in cleaned_data.items()}
    serializable_cleaned_data['dimension'] = dimension

    dim_label = YearlySaleBreakdownService.DIMENSION_CONFIG.get(dimension, {}).get('label', dimension)

    is_seller = user.groups.filter(name='vendedor').exists()

    breakdown_service = YearlySaleBreakdownService(
        queryset=filtered_tx_qs,
        dimension=dimension,
        user=user,
        cleaned_data=cleaned_data,
    )

    exports_service = YearlySaleBreakdownExports(breakdown_service=breakdown_service)
    csv_file = exports_service.export_yearly_sale_breakdown_csv(is_seller=is_seller)
    file_bytes = csv_file.getvalue()

    timestamp_str = timezone.localdate().strftime('%Y%m%d_%H%M%S')
    filename = f"reporte_desglose_anual_ventas_{dimension}_{timestamp_str}.csv"

    try:
        temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp_reports')
        os.makedirs(temp_dir, exist_ok=True)
        temp_filename = f"{uuid.uuid4().hex}.csv"
        temp_file_path = os.path.join(temp_dir, temp_filename)
        with open(temp_file_path, 'wb') as f:
            f.write(file_bytes)

        report = GeneratedReport.objects.create(
            user=user,
            title=f"Reporte de Desglose Anual de Ventas - {dim_label}",
            module_name="yearly_sale_breakdown",
            status=GeneratedReport.Status.PENDING,
            filters=serializable_cleaned_data,
            file_size=len(file_bytes),
        )

        async_task(
            'apps.core.tasks.save_generated_report_file_task',
            report.id,
            temp_file_path,
            filename,
        )
    except Exception as bg_err:
        print(f"[YEARLY BREAKDOWN EXPORT] Error queuing background persistence: {bg_err}", flush=True)

    end = perf_counter()
    print(f"Yearly Sale Breakdown direct export took {end - start:.2f} seconds")

    response = HttpResponse(
        file_bytes,
        content_type="text/csv; charset=utf-8"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Content-Length"] = len(file_bytes)
    return response