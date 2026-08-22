from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.utils import timezone

from apps.customers.services import (
    AccountsReceivablesService,
    AccountsReceivablesExports,
)
from apps.analytics.filters import CollectionsDashboardFilter


@login_required
def export_ars_view(request):
    service = AccountsReceivablesService(user=request.user)
    exports_service = AccountsReceivablesExports(accounts_receivables_service=service)

    perspective = request.GET.get('perspective', 'current_customers')
    if perspective == 'emitting_routes':
        ars_qs = service.read_ars_by_allowed_routes()
    else:
        ars_qs = service.read_ars_by_allowed_customers()

    filter_set = CollectionsDashboardFilter(request.GET or None, queryset=ars_qs, request=request)
    filtered_ars_qs = filter_set.qs

    excel_file = exports_service.export_collections_report(qs=filtered_ars_qs, perspective=perspective)

    filename = f"reporte_cobranza_{timezone.localdate().strftime('%Y%m%d')}.xlsx"
    response = HttpResponse(
        excel_file.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response