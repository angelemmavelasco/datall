import os
import uuid
import datetime
from datetime import date, timedelta
from decimal import Decimal
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import models
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django_q.tasks import async_task
from time import perf_counter

from apps.core.models import GeneratedReport
from apps.sales.filters import SaleTransactionFilter
from apps.sales.services.sale_transactions import (
    SaleTransactionsService,
    SaleTransactionsExports,
)
from apps.sales.services.sale_targets_calculator import (
    SaleTargetCalculatorService,
    SaleTargetCalculatorExports,
    TargetCalculatorError,
)


def _make_serializable(val):
    if isinstance(val, dict):
        return {k: _make_serializable(v) for k, v in val.items()}
    elif isinstance(val, (list, tuple, set, models.QuerySet)):
        return [_make_serializable(x) for x in val]
    elif isinstance(val, models.Model):
        return val.pk
    elif isinstance(val, (datetime.datetime, datetime.date, date)):
        return val.isoformat()
    elif isinstance(val, Decimal):
        return float(val)
    return val


@login_required
def export_sale_targets_calculator_data(request):
    start = perf_counter()
    user = request.user
    q_data = request.GET

    origin_route_id = q_data.get('origin_route', '')
    target_year = q_data.get('target_year', str(timezone.localdate().year))

    serializable_cleaned_data = {}
    for k, v in q_data.lists():
        if len(v) == 1:
            serializable_cleaned_data[k] = v[0]
        else:
            serializable_cleaned_data[k] = v

    route_label = f"Ruta {origin_route_id}" if origin_route_id else "General"

    calculator_service = SaleTargetCalculatorService(user=user)

    mode = q_data.get('mode', 'transfer')
    calc_method = q_data.get('calc_method', 'average')
    destination_route_id = q_data.get('destination_route')
    adjustment_direction = q_data.get('adjustment_direction', 'remove')
    transfer_growth_rule = q_data.get('transfer_growth_rule', 'exact')
    effective_month = q_data.get('effective_month')
    eval_customer_start = q_data.get('eval_customer_start')
    eval_customer_end = q_data.get('eval_customer_end')
    eval_route_start = q_data.get('eval_route_start')
    eval_route_end = q_data.get('eval_route_end')
    product_classes_selected = q_data.getlist('product_classes') if hasattr(q_data, 'getlist') else q_data.get('product_classes', [])
    selected_customers = q_data.getlist('selected_customers') if hasattr(q_data, 'getlist') else q_data.get('selected_customers', [])

    custom_growths = {}
    custom_bases = {}
    for key in (q_data.keys() if hasattr(q_data, 'keys') else []):
        if key.startswith('growth_pc_'):
            parts = key.split('_')
            if len(parts) == 4:
                _, _, pc_id, m_num = parts
                if pc_id not in custom_growths:
                    custom_growths[pc_id] = {}
                val = q_data.get(key)
                if val != '' and val is not None:
                    try:
                        custom_growths[pc_id][int(m_num)] = float(val)
                    except (ValueError, TypeError):
                        pass
        elif key.startswith('base_pc_'):
            parts = key.split('_')
            if len(parts) == 3:
                _, _, pc_id = parts
                val = q_data.get(key)
                if val != '' and val is not None:
                    try:
                        custom_bases[pc_id] = float(val)
                    except (ValueError, TypeError):
                        pass

    try:
        results = calculator_service.calculate_simulation(
            mode=mode,
            calc_method=calc_method,
            origin_route_id=origin_route_id,
            destination_route_id=destination_route_id,
            customer_ids=selected_customers,
            adjustment_direction=adjustment_direction,
            transfer_growth_rule=transfer_growth_rule,
            target_year=int(target_year) if target_year else timezone.localdate().year,
            effective_month=effective_month,
            eval_customer_start=eval_customer_start,
            eval_customer_end=eval_customer_end,
            eval_route_start=eval_route_start,
            eval_route_end=eval_route_end,
            product_class_ids=product_classes_selected,
            custom_growths=custom_growths,
            custom_bases=custom_bases,
        )
    except TargetCalculatorError as err:
        try:
            messages.error(request, str(err))
        except Exception:
            pass
        query_str = q_data.urlencode()
        redirect_url = reverse('sales:sale_target_calculator_view')
        if query_str:
            redirect_url += f"?{query_str}"
        return redirect(redirect_url)

    exports_service = SaleTargetCalculatorExports(calculator_service=calculator_service)
    excel_file = exports_service.export_simulation_report(results)
    file_bytes = excel_file.getvalue()

    timestamp_str = timezone.localdate().strftime('%Y%m%d_%H%M%S')
    filename = f"simulacion_objetivos_{origin_route_id or 'general'}_{target_year}_{timestamp_str}.xlsx"

    try:
        temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp_reports')
        os.makedirs(temp_dir, exist_ok=True)
        temp_filename = f"{uuid.uuid4().hex}.xlsx"
        temp_file_path = os.path.join(temp_dir, temp_filename)
        with open(temp_file_path, 'wb') as f:
            f.write(file_bytes)

        report = GeneratedReport.objects.create(
            user=user,
            title=f"Reporte de Simulación de Objetivos - {route_label} ({target_year})",
            module_name="sale_targets_calculator",
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
        print(f"[SALE TARGETS CALCULATOR EXPORT] Error queuing background persistence: {bg_err}", flush=True)

    end = perf_counter()
    print(f"Sale Target Calculator direct export took {end - start:.2f} seconds")

    response = HttpResponse(
        file_bytes,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Content-Length"] = len(file_bytes)
    return response




@login_required
def sale_transaction_export_view(request):
    user = request.user
    service = SaleTransactionsService(user=user)

    today = timezone.localdate()
    first_day_curr_month = today.replace(day=1)
    last_day_curr_month = (first_day_curr_month + relativedelta(months=1)) - datetime.timedelta(days=1)

    req_data = request.GET.copy()
    if not req_data.get('date_from') and not req_data.get('date_start'):
        req_data['date_from'] = first_day_curr_month.strftime('%Y-%m-%d')
    if not req_data.get('date_to') and not req_data.get('date_end'):
        req_data['date_to'] = last_day_curr_month.strftime('%Y-%m-%d')

    transactions_qs = service.read_transactions()
    transaction_filter = SaleTransactionFilter(req_data, queryset=transactions_qs, request=request)
    filtered_transactions_qs = transaction_filter.qs

    cleaned_data = {}
    if transaction_filter.form.is_valid():
        cleaned_data = transaction_filter.form.cleaned_data
    else:
        for k, v in req_data.items():
            if k != 'page' and v:
                cleaned_data[k] = v

    date_from_val = cleaned_data.get('date_from') or req_data.get('date_from') or req_data.get('date_start') or ''
    date_to_val = cleaned_data.get('date_to') or req_data.get('date_to') or req_data.get('date_end') or ''
    date_start_str = date_from_val.strftime('%Y-%m-%d') if hasattr(date_from_val, 'strftime') else str(date_from_val)
    date_end_str = date_to_val.strftime('%Y-%m-%d') if hasattr(date_to_val, 'strftime') else str(date_to_val)

    exports_service = SaleTransactionsExports(sale_transactions_service=service)
    excel_file = exports_service.export_sale_transactions_report(
        qs=filtered_transactions_qs,
        date_start=date_start_str,
        date_end=date_end_str,
    )
    file_bytes = excel_file.getvalue()

    timestamp_str = timezone.localtime().strftime('%Y%m%d_%H%M%S')
    filename = f"transacciones_venta_{timestamp_str}.xlsx"

    try:
        temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp_reports')
        os.makedirs(temp_dir, exist_ok=True)
        temp_filename = f"{uuid.uuid4().hex}.xlsx"
        temp_file_path = os.path.join(temp_dir, temp_filename)
        with open(temp_file_path, 'wb') as f:
            f.write(file_bytes)

        serializable_cleaned_data = _make_serializable(cleaned_data)
        report = GeneratedReport.objects.create(
            user=user,
            title="Reporte de Transacciones de Venta",
            module_name="sale_transactions",
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
        print(f"[SALE TRANSACTIONS EXPORT] Error queuing background persistence: {bg_err}", flush=True)

    response = HttpResponse(
        file_bytes,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Content-Length"] = len(file_bytes)
    return response
