import os
import uuid
from django.conf import settings
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django_q.tasks import async_task

from apps.core.models import GeneratedReport
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
    cleaned_data = filter_set.form.cleaned_data if filter_set.is_valid() else {}
    serializable_filters = {}
    for k, v in cleaned_data.items():
        if v is not None:
            if hasattr(v, 'pk'):
                serializable_filters[k] = v.pk
            elif hasattr(v, '__iter__') and not isinstance(v, (str, bytes)):
                serializable_filters[k] = [getattr(i, 'pk', i) for i in v]
            else:
                serializable_filters[k] = str(v)
    serializable_filters['perspective'] = perspective

    excel_file = exports_service.export_collections_report(qs=filtered_ars_qs, perspective=perspective)
    file_bytes = excel_file.getvalue()

    filename = f"reporte_cobranza_{timezone.localdate().strftime('%Y%m%d_%H%M%S')}.xlsx"

    try:
        temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp_reports')
        os.makedirs(temp_dir, exist_ok=True)
        temp_filename = f"{uuid.uuid4().hex}.xlsx"
        temp_file_path = os.path.join(temp_dir, temp_filename)
        with open(temp_file_path, 'wb') as f:
            f.write(file_bytes)

        persp_label = "Clientes Asignados" if perspective != 'emitting_routes' else "Ruta Emisora"
        report = GeneratedReport.objects.create(
            user=request.user,
            title=f"Reporte Ejecutivo de Cobranza ({persp_label})",
            module_name="accounts_receivables",
            status=GeneratedReport.Status.PENDING,
            filters=serializable_filters,
            file_size=len(file_bytes),
        )

        async_task(
            'apps.core.tasks.save_generated_report_file_task',
            report.id,
            temp_file_path,
            filename,
        )
    except Exception as bg_err:
        print(f"[AR EXPORT] Error queuing background persistence: {bg_err}", flush=True)

    response = HttpResponse(
        file_bytes,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Content-Length"] = len(file_bytes)
    return response