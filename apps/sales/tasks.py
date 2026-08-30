from django.http import QueryDict
from django.core.files.base import ContentFile
from django.utils import timezone

from apps.core.models import User, GeneratedReport
from apps.sales.services.sale_targets_calculator import (
    SaleTargetCalculatorService,
    SaleTargetCalculatorExports,
)


def generate_sale_targets_calculator_report_task(user_id: int, req_data: dict | str, cleaned_data: dict, report_id: int | None = None):
    try:
        user = User.objects.get(id=user_id)
        calculator_service = SaleTargetCalculatorService(user=user)

        if isinstance(req_data, str):
            q_data = QueryDict(req_data)
        else:
            q_data = req_data

        mode = q_data.get('mode', 'transfer')
        calc_method = q_data.get('calc_method', 'average')
        origin_route_id = q_data.get('origin_route')
        destination_route_id = q_data.get('destination_route')
        adjustment_direction = q_data.get('adjustment_direction', 'remove')
        transfer_growth_rule = q_data.get('transfer_growth_rule', 'exact')
        target_year = q_data.get('target_year')
        effective_month = q_data.get('effective_month')
        eval_customer_start = q_data.get('eval_customer_start')
        eval_customer_end = q_data.get('eval_customer_end')
        eval_route_start = q_data.get('eval_route_start')
        eval_route_end = q_data.get('eval_route_end')
        product_classes_selected = q_data.getlist('product_classes') if hasattr(q_data, 'getlist') else q_data.get('product_classes', [])
        selected_customers = q_data.getlist('selected_customers') if hasattr(q_data, 'getlist') else q_data.get('selected_customers', [])

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
        )

        exports_service = SaleTargetCalculatorExports(calculator_service=calculator_service)
        excel_file = exports_service.export_simulation_report(results)
        file_bytes = excel_file.getvalue()

        if report_id:
            report = GeneratedReport.objects.get(id=report_id)
            filename = f"simulacion_objetivos_{origin_route_id}_{target_year}_{timezone.localdate().strftime('%Y%m%d_%H%M%S')}.xlsx"
            report.file.save(filename, ContentFile(file_bytes), save=False)
            report.file_size = len(file_bytes)
            report.status = GeneratedReport.Status.COMPLETED
            report.completed_at = timezone.now()
            report.save()

        return True
    except Exception as e:
        if report_id:
            try:
                report = GeneratedReport.objects.get(id=report_id)
                report.status = GeneratedReport.Status.FAILED
                report.error_message = str(e)
                report.save()
            except Exception:
                pass
        raise e
