from datetime import date, timedelta
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.shortcuts import redirect
from django.urls import reverse
from django.contrib import messages
from django_q.tasks import async_task
from time import perf_counter

from apps.core.models import GeneratedReport


@login_required
def export_sale_targets_calculator_data(request):
    start = perf_counter()

    origin_route_id = request.GET.get('origin_route', '')
    target_year = request.GET.get('target_year', str(timezone.localdate().year))

    serializable_cleaned_data = {}
    for k, v in request.GET.lists():
        if len(v) == 1:
            serializable_cleaned_data[k] = v[0]
        else:
            serializable_cleaned_data[k] = v

    route_label = f"Ruta {origin_route_id}" if origin_route_id else "General"

    report = GeneratedReport.objects.create(
        user=request.user,
        title=f"Reporte de Simulación de Objetivos - {route_label} ({target_year})",
        module_name="sale_targets_calculator",
        status=GeneratedReport.Status.PENDING,
        filters=serializable_cleaned_data,
    )

    async_task(
        'apps.sales.tasks.generate_sale_targets_calculator_report_task',
        request.user.id,
        request.GET.urlencode(),
        serializable_cleaned_data,
        report.id,
    )

    messages.info(
        request,
        "Tu reporte de simulación de objetivos se está generando en segundo plano. Aparecerá en tus archivos cuando esté listo. Puedes seguir navegando por la web sin problemas."
    )

    query_str = request.GET.urlencode()
    redirect_url = reverse('sales:sale_target_calculator_view')
    if query_str:
        redirect_url += f"?{query_str}"

    end = perf_counter()
    print(f"Sale Target Calculator export took {end - start} seconds")

    return redirect(redirect_url)
