from django.http import QueryDict
from django.core.files.base import ContentFile
from django.utils import timezone

from apps.core.models import User, GeneratedReport
from apps.human_resources.models import BusinessUnit
from apps.customers.services.customers import CustomersService
from apps.sales.services.sale_transactions import SaleTransactionsService
from apps.sales.services.sale_targets import SaleTargetsService
from apps.customers.services.accounts_receivables import AccountsReceivablesService
from apps.sales.services.routes import RoutesService
from apps.analytics.filters import CustomerKpisFilter, CommercialRiskFilter, MonthlySaleBreakdownFilter, TargetAchievementFilter
from apps.analytics.services.customer_kpis import CustomerKpisService, CustomerKpisExports
from apps.analytics.services.commercial_risk import CommercialRiskService, CommercialRiskExports
from apps.analytics.services.monthly_sale_breakdown import MonthlySaleBreakdownService, MonthlySaleBreakdownExports
from apps.analytics.services.target_achievement import TargetAchievementService, TargetAchievementExports



def generate_customer_kpis_report_task(user_id: int, req_data: dict | str, cleaned_data: dict, report_id: int | None = None):
    try:
        user = User.objects.get(id=user_id)

        customer_service = CustomersService(user=user)
        customer_qs = customer_service.read_customers()

        sale_transaction_service = SaleTransactionsService(user=user)
        tx_by_allowed_ctm = sale_transaction_service.read_transactions_by_allowed_customers()

        ar_service = AccountsReceivablesService(user=user)
        ar_allowed_ctm = ar_service.read_ars_by_allowed_customers()

        if isinstance(req_data, str):
            q_data = QueryDict(req_data)
        else:
            q_data = req_data

        filter_set = CustomerKpisFilter(q_data, queryset=customer_qs)
        filtered_customers_qs = filter_set.qs

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

        if report_id:
            report = GeneratedReport.objects.get(id=report_id)
            filename = f"reporte_kpis_clientes_{timezone.localdate().strftime('%Y%m%d_%H%M%S')}.xlsx"
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


def generate_commercial_risk_report_task(user_id: int, req_data: dict | str, cleaned_data: dict, report_id: int | None = None):
    try:
        user = User.objects.get(id=user_id)

        customer_service = CustomersService(user=user)
        customer_qs = customer_service.read_customers()

        sale_transaction_service = SaleTransactionsService(user=user)
        tx_by_allowed_ctm = sale_transaction_service.read_transactions_by_allowed_customers()

        routes_service = RoutesService(user=user)
        allowed_routes = routes_service.read_routes().order_by('id')
        first_route = allowed_routes.first()

        if isinstance(req_data, str):
            q_data = QueryDict(req_data)
        else:
            q_data = req_data

        filter_set = CommercialRiskFilter(q_data, queryset=allowed_routes)
        route_id_from_data = cleaned_data.get('route') or q_data.get('route')
        selected_route = allowed_routes.filter(id=route_id_from_data).first() if route_id_from_data else first_route

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

        if report_id:
            report = GeneratedReport.objects.get(id=report_id)
            route_str = selected_route.id if selected_route else 'general'
            filename = f"reporte_riesgo_comercial_ruta_{route_str}_{timezone.localdate().strftime('%Y%m%d_%H%M%S')}.xlsx"
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


def generate_monthly_sale_breakdown_report_task(user_id: int, req_data: dict | str, cleaned_data: dict, report_id: int | None = None):
    try:
        user = User.objects.get(id=user_id)

        today = timezone.localdate()
        if isinstance(req_data, str):
            q_data = QueryDict(req_data)
        else:
            q_data = req_data

        selected_year_val = cleaned_data.get('year') or q_data.get('year') or str(today.year)
        try:
            selected_year = int(selected_year_val)
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

        filter_set = MonthlySaleBreakdownFilter(q_data, queryset=base_tx_qs, request=user)
        filtered_tx_qs = filter_set.qs
        parsed_cleaned_data = filter_set.form.cleaned_data if filter_set.is_valid() else {}

        filter_dict = parsed_cleaned_data or cleaned_data

        breakdown_service = MonthlySaleBreakdownService(
            user=user,
            targets_qs=base_targets_qs,
            transactions_qs=filtered_tx_qs,
            customers_qs=base_customers_qs,
            ars_qs=base_ars_qs,
            routes_qs=allowed_routes_qs,
            year=selected_year,
            cleaned_data=filter_dict
        )

        exports_service = MonthlySaleBreakdownExports(monthly_sale_breakdown_service=breakdown_service)
        excel_file = exports_service.export_monthly_sale_breakdown_report()
        file_bytes = excel_file.getvalue()

        if report_id:
            report = GeneratedReport.objects.get(id=report_id)
            filename = f"reporte_desglose_mensual_ventas_{selected_year}_{timezone.localdate().strftime('%Y%m%d_%H%M%S')}.xlsx"
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


def generate_target_achievement_report_task(user_id: int, req_data: dict | str, cleaned_data: dict, report_id: int | None = None):
    try:
        user = User.objects.get(id=user_id)

        targets_service = SaleTargetsService(user=user)
        base_targets_qs = targets_service.read_sale_targets()

        tx_service = SaleTransactionsService(user=user)
        base_tx_qs = tx_service.read_transactions_by_allowed_routes()

        customers_service = CustomersService(user=user)
        base_customers_qs = customers_service.read_customers()

        routes_service = RoutesService(user=user)
        allowed_routes_qs = routes_service.get_allowed_routes(can_view=True, can_edit=False)

        if isinstance(req_data, str):
            q_data = QueryDict(req_data)
        else:
            q_data = req_data

        filter_set = TargetAchievementFilter(q_data, queryset=base_targets_qs, request=user)
        filtered_targets_qs = filter_set.qs
        parsed_cleaned_data = filter_set.form.cleaned_data if filter_set.is_valid() else {}
        filter_dict = parsed_cleaned_data or cleaned_data

        filtered_tx_qs = base_tx_qs
        filtered_routes_qs = allowed_routes_qs
        filtered_customers_qs = base_customers_qs

        if filter_dict.get('region'):
            selected_region_ids = set(r.pk if hasattr(r, 'pk') else r for r in filter_dict['region'])
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

        if filter_dict.get('business_unit'):
            bu_ids = [bu.pk if hasattr(bu, 'pk') else bu for bu in filter_dict['business_unit']]
            filtered_tx_qs = filtered_tx_qs.filter(route__business_unit_id__in=bu_ids)
            filtered_routes_qs = filtered_routes_qs.filter(business_unit_id__in=bu_ids)
            filtered_customers_qs = filtered_customers_qs.filter(
                assignments__route__business_unit_id__in=bu_ids
            )

        if filter_dict.get('route'):
            route_ids = [r.pk if hasattr(r, 'pk') else r for r in filter_dict['route']]
            filtered_tx_qs = filtered_tx_qs.filter(route_id__in=route_ids)
            filtered_routes_qs = filtered_routes_qs.filter(id__in=route_ids)
            filtered_customers_qs = filtered_customers_qs.filter(
                assignments__route_id__in=route_ids
            )

        if filter_dict.get('product_category'):
            filtered_tx_qs = filtered_tx_qs.filter(product_class__product_category__in=filter_dict['product_category'])

        if filter_dict.get('product_class'):
            filtered_tx_qs = filtered_tx_qs.filter(product_class__in=filter_dict['product_class'])

        achievement_service = TargetAchievementService(
            user=user,
            targets_qs=filtered_targets_qs,
            transactions_qs=filtered_tx_qs,
            customers_qs=filtered_customers_qs,
            routes_qs=filtered_routes_qs,
            date_start=filter_dict.get('date_start'),
            date_end=filter_dict.get('date_end'),
            cleaned_data=filter_dict
        )

        exports_service = TargetAchievementExports(target_achievement_service=achievement_service)
        excel_file = exports_service.export_target_achievement_report()
        file_bytes = excel_file.getvalue()

        if report_id:
            report = GeneratedReport.objects.get(id=report_id)
            d_start_str = achievement_service.date_start_dt.strftime('%Y%m%d')
            d_end_str = achievement_service.date_end_dt.strftime('%Y%m%d')
            filename = f"reporte_alcance_objetivos_{d_start_str}_{d_end_str}_{timezone.localdate().strftime('%Y%m%d_%H%M%S')}.xlsx"
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


