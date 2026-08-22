from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from dateutil.relativedelta import relativedelta

from apps.customers.services.customers import CustomersService
from apps.sales.services.sale_transactions import SaleTransactionsService
from apps.customers.services.accounts_receivables import AccountsReceivablesService
from apps.analytics.filters import CustomerKpisFilter
from apps.analytics.services.customer_kpis import CustomerKpisService, CustomerKpisExports


@login_required
def customer_kpis_export_view(request):
    # base services
    customer_service = CustomersService(user=request.user)
    customer_qs = customer_service.read_customers()

    sale_transaction_service = SaleTransactionsService(user=request.user)
    tx_by_allowed_ctm = sale_transaction_service.read_transactions_by_allowed_customers()

    ar_service = AccountsReceivablesService(user=request.user)
    ar_allowed_ctm = ar_service.read_ars_by_allowed_customers()

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
    filtered_customers_qs = filter_set.qs
    cleaned_data = filter_set.form.cleaned_data if filter_set.is_valid() else {}

    # main service
    customer_kpis_service = CustomerKpisService(
        user=request.user, 
        customers_qs=filtered_customers_qs,
        transactions_qs=tx_by_allowed_ctm,
        ars_qs=ar_allowed_ctm,
        date_start=cleaned_data.get('start_contrib'),
        date_end=cleaned_data.get('end_contrib'),
        cleaned_data=cleaned_data,
    )

    exports_service = CustomerKpisExports(customer_kpis_service=customer_kpis_service)
    excel_file = exports_service.export_customer_kpis_report()

    filename = f"reporte_kpis_clientes_{timezone.localdate().strftime('%Y%m%d')}.xlsx"
    response = HttpResponse(
        excel_file.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response