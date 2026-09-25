import calendar
import random
import string
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import ClassVar, Optional, Any
from dateutil.relativedelta import relativedelta

from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from django.db.models import (
    Q,
    F,
    QuerySet,
    Sum,
    Count,
    Avg,
    Case,
    When,
    Value,
    BooleanField,
    Prefetch,
)
from django.utils import timezone

from apps.core.models import PeriodicityChoices, Reference
from apps.core.services.users import UsersService
from apps.customers.models import (
    Customer,
    CustomerAssignment,
    CustomerClassMargin,
    CommercialBenefit,
    CustomerAgreement,
    AgreementClassTarget,
    AgreementEvaluationPeriod,
    AgreementPeriodClassResult,
    PeriodStatusChoices,
    AgreementTypeChoices,
)
from apps.customers.services.customers import CustomersService
from apps.products.models import ProductClass
from apps.sales.models import Route, SaleTransaction, RouteAssignment
from apps.sales.services.routes import RoutesService


class ServiceError(Exception):
    pass


class PermissionsError(ServiceError):
    pass


class CustomerAgreementNotFound(ServiceError):
    pass


class CommercialBenefitNotFound(ServiceError):
    pass


class MarginValidationException(ServiceError):
    def __init__(self, message, simulated_margin, min_margin):
        self.message = message
        self.simulated_margin = simulated_margin
        self.min_margin = min_margin
        super().__init__(self.message)


def parse_month_input(date_str: str | date | None, is_end: bool = False) -> Optional[date]:
    """
    parses a string in format 'YYYY-MM' or 'YYYY-MM-DD' or a date object.
    always snaps to the 1st of the month (if is_end=False) or the last day
    of that month (if is_end=True) to enforce complete monthly periods.
    """
    if not date_str:
        return None
    if isinstance(date_str, date):
        if is_end:
            last_day = calendar.monthrange(date_str.year, date_str.month)[1]
            return date(date_str.year, date_str.month, last_day)
        return date(date_str.year, date_str.month, 1)

    clean_str = str(date_str).strip()
    if len(clean_str) == 7 and '-' in clean_str:
        try:
            y, m = map(int, clean_str.split('-'))
            if is_end:
                last_day = calendar.monthrange(y, m)[1]
                return date(y, m, last_day)
            return date(y, m, 1)
        except Exception:
            return None
    try:
        parsed = date.fromisoformat(clean_str)
        if is_end:
            last_day = calendar.monthrange(parsed.year, parsed.month)[1]
            return date(parsed.year, parsed.month, last_day)
        return date(parsed.year, parsed.month, 1)
    except ValueError:
        return None


def get_periods_count(start_date: date, end_date: Optional[date], freq_val: str) -> int:
    """
    calculates how many evaluation periods occur between start_date and end_date
    according to the specified PeriodicityChoices.
    """
    if not end_date or start_date > end_date:
        return 1
    if freq_val in (PeriodicityChoices.AT_END, 'end'):
        return 1
    try:
        delta = PeriodicityChoices(freq_val).get_relativedelta()
    except (ValueError, KeyError):
        delta = relativedelta(months=1)

    count = 0
    current = start_date
    while current <= end_date:
        count += 1
        current += delta
    return count if count > 0 else 1


def get_traffic_light_status(margin: Decimal | float | None) -> dict:
    """
    standard qualitative traffic light representation for seller role.
    """
    if margin is None:
        return {'label': 'Sin datos', 'color_class': 'text-secondary'}
    val = float(margin)
    if val >= 43.0:
        return {'label': 'Excelente', 'color_class': 'text-emerald-600 dark:text-emerald-400'}
    elif val >= 40.0:
        return {'label': 'Óptimo', 'color_class': 'text-emerald-500 dark:text-emerald-300'}
    elif val >= 37.0:
        return {'label': 'Regular', 'color_class': 'text-yellow-500 dark:text-yellow-400'}
    elif val >= 35.0:
        return {'label': 'Malo', 'color_class': 'text-red-500 dark:text-red-400'}
    else:
        return {'label': 'Muy malo', 'color_class': 'text-red-600 dark:text-red-500'}


@dataclass
class CustomerAgreementsService(UsersService):
    agreement_model: type = CustomerAgreement
    benefit_model: type = CommercialBenefit
    class_target_model: type = AgreementClassTarget
    evaluation_period_model: type = AgreementEvaluationPeriod
    period_class_result_model: type = AgreementPeriodClassResult
    customer_margin_model: type = CustomerClassMargin
    sale_transaction_model: type = SaleTransaction
    product_class_model: type = ProductClass
    ACCESS_CONTEXTS: ClassVar[tuple[str, ...]] = (
        'acceso_total_clientes',
        'clientes',
        'acceso_total_ventas',
        'acceso_total',
    )

    @property
    def is_seller(self) -> bool:
        return self.user.groups.filter(name='vendedor').exists()

    @property
    def can_edit_agreement(self) -> bool:
        """
        determines whether the user has permission to modify the agreement's
        execution parameters (signed, benefit_already_provided, and related_doc).
        allowed users are those with full access (superuser, staff, or configured
        full-access groups) or users belonging to any group defined in Reference
        with key='can_edit_customer_agreement'.
        """
        if self.has_full_access:
            return True
        allowed_groups = list(Reference.objects.filter(key='can_edit_customer_agreement').values_list('value', flat=True))
        if not allowed_groups:
            return False
        return self.user.groups.filter(name__in=allowed_groups).exists()

    def get_allowed_agreements(self) -> QuerySet:
        """
        agreements visible to a user are those whose customers are currently
        assigned to routes the user has permission to view (or if user has full access).
        the agreement itself still records the originating route.
        """
        if self.has_full_access:
            return self.agreement_model.objects.all()

        customers_service = CustomersService(user=self.user)
        allowed_customers_qs = customers_service.get_allowed_customers(can_view=True)
        return self.agreement_model.objects.filter(customer__in=allowed_customers_qs)

    def read_agreements(self) -> QuerySet:
        """
        Returns the queryset of allowed agreements annotated and optimized for listing.
        """
        today = timezone.localdate()
        base_qs = self.get_allowed_agreements().select_related(
            'customer',
            'customer__customer_type',
            'route',
            'route__business_unit',
            'benefit',
            'created_by'
        ).prefetch_related(
            'class_targets',
            'class_targets__product_class',
            'evaluation_periods'
        ).annotate(
            is_active_now=Case(
                When(
                    Q(start_date__lte=today) & (Q(end_date__isnull=True) | Q(end_date__gte=today)),
                    then=Value(True)
                ),
                default=Value(False),
                output_field=BooleanField()
            )
        ).order_by('-start_date', '-created_at')

        return base_qs

    def read_agreement(self, pk: int | str) -> CustomerAgreement:
        """
        retrieves a single agreement enforcing permissions.
        """
        agreement = self.read_agreements().filter(pk=pk).first()
        if agreement:
            return agreement

        if self.agreement_model.objects.filter(pk=pk).exists():
            raise PermissionsError(f'No tienes permiso para acceder al convenio con ID "{pk}".')

        raise CustomerAgreementNotFound(f'No se encontró ningún convenio con el ID "{pk}".')

    def read_agreement_details(self, pk: int | str) -> dict[str, Any]:
        """
        prepares complete agreement details for presentation.
        """
        agreement = self.read_agreement(pk)
        customer = agreement.customer
        is_seller_user = self.is_seller

        class_margins = self.customer_margin_model.objects.filter(
            customer=customer
        ).select_related('product_class')

        eval_periods = list(
            self.evaluation_period_model.objects.filter(
                agreement=agreement
            ).prefetch_related('class_results__product_class').order_by('period_number')
        )

        for period in eval_periods:
            period.penalty_amount_applied = agreement.penalty_amount if period.penalty_applied else Decimal('0.00')
            if period.penalty_applied:
                period.gross_profit = period.period_profit
            else:
                period.gross_profit = period.period_profit + period.amortized_benefit_cost

            
            period.traffic_light = get_traffic_light_status(period.period_margin)

        return {
            'agreement': agreement,
            'customer': customer,
            'class_margins': class_margins,
            'eval_periods': eval_periods,
            'is_seller': is_seller_user,
            'can_edit': self.can_edit_agreement,
        }

    def validate_agreement_margin(
        self,
        *,
        customer_id: str,
        benefit_id: int | str,
        participating_classes_data: list[dict],
        eval_start: str | date,
        eval_end: str | date,
        agreement_start: str | date | None = None,
        agreement_end: str | date | None = None,
        agreement_start_date: str | date | None = None,
        agreement_end_date: str | date | None = None,
        target_frequency: str,
        global_target: Decimal | float | str | None = None,
        global_target_amount: Decimal | float | str | None = None,
        growth_value: Decimal | float | str = Decimal('0.00'),
        growth_frequency: str = '',
    ) -> tuple[bool, Decimal, Decimal, bool, dict[str, Any]]:
        """
        calculates historical margin, simulates amortized benefit impact and compound growth,
        and evaluates biconditionally against CustomerClassMargin.
        strict business rule: only participating classes are included. non-participating classes
        are completely excluded from the sales evaluation and margin minimum checks.
        """
        agr_start_val = agreement_start or agreement_start_date
        agr_end_val = agreement_end or agreement_end_date
        global_tgt_val = global_target if global_target is not None else (global_target_amount or Decimal('0.00'))

        start_date = parse_month_input(eval_start)
        end_date = parse_month_input(eval_end, is_end=True)
        agr_start = parse_month_input(agr_start_val)
        agr_end = parse_month_input(agr_end_val, is_end=True)

        if not start_date or not end_date or not agr_start or not agr_end:
            raise ServiceError("Fechas de evaluación o vigencia inválidas.")

        benefit = self.benefit_model.objects.filter(pk=benefit_id).first()
        if not benefit:
            raise CommercialBenefitNotFound("El beneficio comercial seleccionado no existe.")

        try:
            global_target_dec = Decimal(str(global_tgt_val or '0'))
            growth_val_dec = Decimal(str(growth_value or '0'))
        except Exception:
            global_target_dec = Decimal('0.00')
            growth_val_dec = Decimal('0.00')

        participating_class_ids = [
            str(c.get('product_class_id')) for c in participating_classes_data if c.get('product_class_id')
        ]

        
        delta_hist = relativedelta(end_date + timedelta(days=1), start_date)
        hist_months = delta_hist.years * 12 + delta_hist.months
        if hist_months <= 0:
            hist_months = 1

        
        sales = self.sale_transaction_model.objects.filter(
            customer_id=customer_id,
            sale_date__gte=start_date,
            sale_date__lte=end_date
        )
        if participating_class_ids:
            sales = sales.filter(product_class_id__in=participating_class_ids)

        totals = sales.aggregate(
            total_net=Sum('net_amount'),
            total_profit=Sum('profit')
        )
        total_net = totals['total_net'] or Decimal('0.00')
        total_profit = totals['total_profit'] or Decimal('0.00')

        
        total_agreement_periods = get_periods_count(agr_start, agr_end, target_frequency)
        cme = benefit.cost / Decimal(str(total_agreement_periods)) if total_agreement_periods > 0 else benefit.cost

        
        delta_agr = relativedelta(agr_end + timedelta(days=1), agr_start)
        agr_duration_months = delta_agr.years * 12 + delta_agr.months

        if target_frequency in (PeriodicityChoices.AT_END, 'end'):
            freq_delta = relativedelta(end_date + timedelta(days=1), start_date)
            periodicity_months = hist_months
        else:
            try:
                freq_delta = PeriodicityChoices(target_frequency).get_relativedelta()
                periodicity_months = freq_delta.months + (freq_delta.years * 12) if (freq_delta.months or freq_delta.years) else 1
            except Exception:
                freq_delta = relativedelta(months=1)
                periodicity_months = 1

        has_partial_periods = (hist_months % periodicity_months != 0)

        hist_periods_count = get_periods_count(start_date, end_date, target_frequency)
        past_cost = cme * Decimal(str(hist_periods_count))

        
        if total_net > 0:
            simulated_net_margin = ((total_profit - past_cost) / total_net) * Decimal('100.0')
            historic_margin = (total_profit / total_net) * Decimal('100.0')
        else:
            simulated_net_margin = Decimal('0.00')
            historic_margin = Decimal('0.00')

        
        current_start = start_date
        period_margins = []
        hist_period_margins = []

        while current_start <= end_date:
            current_end = current_start + freq_delta - relativedelta(days=1)
            if current_end > end_date:
                current_end = end_date

            p_sales = sales.filter(sale_date__gte=current_start, sale_date__lte=current_end)
            p_agg = p_sales.aggregate(p_net=Sum('net_amount'), p_profit=Sum('profit'))
            p_net = p_agg['p_net'] or Decimal('0.00')
            p_profit = p_agg['p_profit'] or Decimal('0.00')

            if p_net > 0:
                p_margin = ((p_profit - cme) / p_net) * Decimal('100.0')
                p_hist = (p_profit / p_net) * Decimal('100.0')
                period_margins.append(p_margin)
                hist_period_margins.append(p_hist)

            current_start = current_start + freq_delta

        avg_period_margin = sum(period_margins) / len(period_margins) if period_margins else Decimal('0.00')
        avg_hist_period_margin = sum(hist_period_margins) / len(hist_period_margins) if hist_period_margins else Decimal('0.00')

        min_margins = self.customer_margin_model.objects.filter(customer_id=customer_id)
        if participating_class_ids:
            min_margins = min_margins.filter(product_class_id__in=participating_class_ids)

        max_required_margin = Decimal('0.00')
        if min_margins.exists():
            max_required_margin = max(m.min_margin_percentage for m in min_margins)

        classes_qs = self.product_class_model.objects.filter(id__in=participating_class_ids)
        classes_map = {c.id: c for c in classes_qs}
        customer_margins_map = {
            m.product_class_id: m.min_margin_percentage
            for m in min_margins
        }

        sub_periods = []
        cur_s = start_date
        while cur_s <= end_date:
            cur_e = cur_s + freq_delta - relativedelta(days=1)
            if cur_e > end_date:
                cur_e = end_date
            sub_periods.append((cur_s, cur_e))
            cur_s = cur_s + freq_delta

        mandatory_items = [c for c in participating_classes_data if c.get('is_mandatory')]
        complementary_items = [c for c in participating_classes_data if not c.get('is_mandatory')]

        mandatory_breakdown = []
        for item in mandatory_items:
            cid = str(item.get('product_class_id'))
            pc = classes_map.get(cid)
            pc_name = (pc.name if pc and pc.name else cid).title()
            req_tgt = Decimal(str(item.get('required_target') or '0'))
            min_m = customer_margins_map.get(cid, Decimal('0.00'))

            c_sales = sales.filter(product_class_id=cid)
            c_totals = c_sales.aggregate(net=Sum('net_amount'), profit=Sum('profit'))
            c_net = c_totals['net'] or Decimal('0.00')
            c_profit = c_totals['profit'] or Decimal('0.00')
            c_period_margin = (c_profit / c_net * Decimal('100.0')) if c_net > 0 else Decimal('0.00')

            c_sub_margins = []
            for p_start, p_end in sub_periods:
                p_c_sales = c_sales.filter(sale_date__gte=p_start, sale_date__lte=p_end)
                p_c_totals = p_c_sales.aggregate(net=Sum('net_amount'), profit=Sum('profit'))
                p_c_net = p_c_totals['net'] or Decimal('0.00')
                p_c_profit = p_c_totals['profit'] or Decimal('0.00')
                if p_c_net > 0:
                    c_sub_margins.append((p_c_profit / p_c_net) * Decimal('100.0'))

            c_avg_period_margin = (sum(c_sub_margins) / len(c_sub_margins)) if c_sub_margins else Decimal('0.00')

            c_is_valid = True
            c_volatility = False
            if c_net > 0 and min_m > 0:
                if c_period_margin >= min_m:
                    c_is_valid = True
                elif c_avg_period_margin >= min_m:
                    c_is_valid = False
                    c_volatility = True
                else:
                    c_is_valid = False

            mandatory_breakdown.append({
                'product_class_id': cid,
                'product_class_name': pc_name,
                'is_mandatory': True,
                'required_target': req_tgt,
                'min_margin': min_m,
                'total_net': c_net,
                'total_profit': c_profit,
                'period_margin': c_period_margin,
                'avg_period_margin': c_avg_period_margin,
                'has_sales': (c_net > 0),
                'is_valid': c_is_valid,
                'volatility_alert': c_volatility,
            })

        complementary_breakdown = []
        comp_class_ids = [str(item.get('product_class_id')) for item in complementary_items if item.get('product_class_id')]

        for item in complementary_items:
            cid = str(item.get('product_class_id'))
            pc = classes_map.get(cid)
            pc_name = (pc.name if pc and pc.name else cid).title()
            min_m = customer_margins_map.get(cid, Decimal('0.00'))

            c_sales = sales.filter(product_class_id=cid)
            c_totals = c_sales.aggregate(net=Sum('net_amount'), profit=Sum('profit'))
            c_net = c_totals['net'] or Decimal('0.00')
            c_profit = c_totals['profit'] or Decimal('0.00')
            c_period_margin = (c_profit / c_net * Decimal('100.0')) if c_net > 0 else Decimal('0.00')

            c_sub_margins = []
            for p_start, p_end in sub_periods:
                p_c_sales = c_sales.filter(sale_date__gte=p_start, sale_date__lte=p_end)
                p_c_totals = p_c_sales.aggregate(net=Sum('net_amount'), profit=Sum('profit'))
                p_c_net = p_c_totals['net'] or Decimal('0.00')
                p_c_profit = p_c_totals['profit'] or Decimal('0.00')
                if p_c_net > 0:
                    c_sub_margins.append((p_c_profit / p_c_net) * Decimal('100.0'))

            c_avg_period_margin = (sum(c_sub_margins) / len(c_sub_margins)) if c_sub_margins else Decimal('0.00')

            complementary_breakdown.append({
                'product_class_id': cid,
                'product_class_name': pc_name,
                'is_mandatory': False,
                'min_margin': min_m,
                'total_net': c_net,
                'total_profit': c_profit,
                'period_margin': c_period_margin,
                'avg_period_margin': c_avg_period_margin,
                'has_sales': (c_net > 0),
                'is_most_restrictive': False,
            })

        most_restrictive_class = None
        most_restrictive_min_margin = Decimal('0.00')
        if complementary_breakdown:
            highest_min = max(c['min_margin'] for c in complementary_breakdown)
            most_restrictive_min_margin = highest_min
            for c in complementary_breakdown:
                if c['min_margin'] == highest_min and highest_min > Decimal('0.00') and not most_restrictive_class:
                    c['is_most_restrictive'] = True
                    most_restrictive_class = c
            if not most_restrictive_class and complementary_breakdown:
                most_restrictive_class = complementary_breakdown[0]

        comp_sales = sales.filter(product_class_id__in=comp_class_ids) if comp_class_ids else sales.none()
        comp_totals = comp_sales.aggregate(net=Sum('net_amount'), profit=Sum('profit'))
        comp_net = comp_totals['net'] or Decimal('0.00')
        comp_profit = comp_totals['profit'] or Decimal('0.00')
        comp_period_margin = (comp_profit / comp_net * Decimal('100.0')) if comp_net > 0 else Decimal('0.00')

        comp_sub_margins = []
        for p_start, p_end in sub_periods:
            p_comp_sales = comp_sales.filter(sale_date__gte=p_start, sale_date__lte=p_end)
            p_comp_totals = p_comp_sales.aggregate(net=Sum('net_amount'), profit=Sum('profit'))
            p_comp_net = p_comp_totals['net'] or Decimal('0.00')
            p_comp_profit = p_comp_totals['profit'] or Decimal('0.00')
            if p_comp_net > 0:
                comp_sub_margins.append((p_comp_profit / p_comp_net) * Decimal('100.0'))

        comp_avg_period_margin = (sum(comp_sub_margins) / len(comp_sub_margins)) if comp_sub_margins else Decimal('0.00')

        comp_is_valid = True
        comp_volatility = False
        if comp_net > 0 and most_restrictive_min_margin > 0:
            if comp_period_margin >= most_restrictive_min_margin:
                comp_is_valid = True
            elif comp_avg_period_margin >= most_restrictive_min_margin:
                comp_is_valid = False
                comp_volatility = True
            else:
                comp_is_valid = False

        complementary_pool = {
            'count': len(complementary_breakdown),
            'classes': complementary_breakdown,
            'most_restrictive_class': most_restrictive_class,
            'most_restrictive_min_margin': most_restrictive_min_margin,
            'total_net': comp_net,
            'total_profit': comp_profit,
            'period_margin': comp_period_margin,
            'avg_period_margin': comp_avg_period_margin,
            'has_sales': (comp_net > 0),
            'is_valid': comp_is_valid,
            'volatility_alert': comp_volatility,
        }

        growth_projected_totals = []
        if growth_val_dec > 0 and growth_frequency:
            try:
                g_delta = PeriodicityChoices(growth_frequency).get_relativedelta()
            except Exception:
                g_delta = relativedelta(months=1)
            curr_target = global_target_dec
            for _ in range(total_agreement_periods):
                growth_projected_totals.append(curr_target)
                curr_target = curr_target * (Decimal('1.00') + (growth_val_dec / Decimal('100.00')))

        failed_mandatory = [c for c in mandatory_breakdown if c['has_sales'] and not c['is_valid'] and not c['volatility_alert']]
        volatile_mandatory = [c for c in mandatory_breakdown if c['volatility_alert']]
        failed_comp = bool(comp_class_ids and comp_net > 0 and most_restrictive_min_margin > 0 and not comp_is_valid and not comp_volatility)
        volatile_comp = comp_volatility

        overall_is_valid = True
        overall_volatility = False

        if total_net > 0 and max_required_margin > 0:
            if simulated_net_margin < max_required_margin:
                if avg_period_margin >= max_required_margin:
                    overall_is_valid = False
                    overall_volatility = True
                else:
                    overall_is_valid = False
            elif failed_mandatory or failed_comp:
                overall_is_valid = False
            elif volatile_mandatory or volatile_comp:
                overall_is_valid = False
                overall_volatility = True
        else:
            overall_is_valid = True
            overall_volatility = False

        result_data = {
            'avg_period_margin': avg_period_margin,
            'total_profit': total_profit,
            'total_net': total_net,
            'past_cost': past_cost,
            'cme': cme,
            'has_partial_periods': has_partial_periods,
            'duration_months': hist_months,
            'periodicity_months': periodicity_months,
            'historic_margin': historic_margin,
            'avg_hist_period_margin': avg_hist_period_margin,
            'benefit_cost': benefit.cost,
            'benefit_name': benefit.name,
            'simulated_total_periods': total_agreement_periods,
            'participating_classes_count': len(participating_class_ids),
            'traffic_light': get_traffic_light_status(simulated_net_margin),
            'hist_traffic_light': get_traffic_light_status(historic_margin),
            'is_seller': self.is_seller,
            'simulated_margin': simulated_net_margin,
            'min_margin': max_required_margin,
            'amortized_benefit_cost': cme,
            'mandatory_breakdown': mandatory_breakdown,
            'has_mandatory': len(mandatory_breakdown) > 0,
            'complementary_pool': complementary_pool,
            'has_complementary': len(complementary_breakdown) > 0,
            'most_restrictive_class_name': most_restrictive_class['product_class_name'] if most_restrictive_class else None,
            'most_restrictive_min_margin': most_restrictive_min_margin,
            'failed_mandatory_count': len(failed_mandatory),
            'failed_complementary': failed_comp,
            'is_valid': overall_is_valid,
            'volatility_alert': overall_volatility,
        }

        return overall_is_valid, simulated_net_margin, max_required_margin, overall_volatility, result_data


    def get_assigned_advisor_name(self, route: Route | None, target_date: date | None = None) -> str:
        """
        finds the full name of the collaborator assigned to the route via RouteAssignment.
        checks active assignment (date_end__isnull=True), assignment at target_date, or latest assignment.
        """
        if not route:
            return ""

        active_assign = (
            RouteAssignment.objects.filter(route=route, date_end__isnull=True)
            .select_related('employee__user')
            .first()
        )

        if not active_assign and target_date:
            active_assign = (
                RouteAssignment.objects.filter(route=route, date_start__lte=target_date)
                .filter(Q(date_end__isnull=True) | Q(date_end__gte=target_date))
                .order_by('-date_start')
                .select_related('employee__user')
                .first()
            )

        if not active_assign:
            active_assign = (
                RouteAssignment.objects.filter(route=route)
                .order_by('-date_start')
                .select_related('employee__user')
                .first()
            )

        if active_assign and active_assign.employee and active_assign.employee.user:
            u = active_assign.employee.user
            full_name = f"{u.first_name} {u.last_name}".strip()
            if not full_name:
                full_name = u.get_full_name() or u.username
            return full_name.title()

        return ""

    def generate_random_doc_id(self) -> str:
        """
        generates a unique 5 character random alphanumeric uppercase folio (doc_id).
        """
        while True:
            candidate = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
            if not self.agreement_model.objects.filter(doc_id=candidate).exists():
                return candidate

    def generate_agreement_preview(
        self,
        form_data: dict | None = None,
        classes_data: list[dict] | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """
        generates the formal printable 'contrato comercial' with 7 formal clauses
        and the 'desglose de consumos esperados' matrix with compound growth.
        """
        data = dict(form_data or {})
        data.update(kwargs)
        if classes_data is None:
            classes_data = data.get('participating_classes_data') or []

        customer_id = data.get('customer_id')
        benefit_id = data.get('benefit_id')
        agreement_type = data.get('agreement_type', AgreementTypeChoices.SHORT_TERM)
        start_date_str = data.get('start_date')
        end_date_str = data.get('end_date')
        target_frequency = data.get('target_frequency', PeriodicityChoices.MONTHLY)
        growth_frequency = data.get('growth_frequency', '')
        
        doc_id = data.get('doc_id')
        if doc_id and str(doc_id).strip():
            doc_id = str(doc_id).strip().upper()
        else:
            doc_id = self.generate_random_doc_id()

        try:
            global_target_amount = Decimal(str(data.get('global_target_amount') or '0'))
            penalty_amount = Decimal(str(data.get('penalty_amount') or '0'))
            growth_value = Decimal(str(data.get('growth_value') or '0'))
        except Exception:
            global_target_amount = Decimal('0.00')
            penalty_amount = Decimal('0.00')
            growth_value = Decimal('0.00')

        customer = Customer.objects.filter(pk=customer_id).first()
        benefit = self.benefit_model.objects.filter(pk=benefit_id).first()

        start_date = parse_month_input(start_date_str)
        end_date = parse_month_input(end_date_str, is_end=True)

        if not start_date or not end_date:
            raise ServiceError("Las fechas de inicio y fin son obligatorias.")

        delta_agr = relativedelta(end_date + timedelta(days=1), start_date)
        duration_months = delta_agr.years * 12 + delta_agr.months
        total_periods = get_periods_count(start_date, end_date, target_frequency)

        if target_frequency in (PeriodicityChoices.AT_END, 'end'):
            freq_delta = relativedelta(end_date + timedelta(days=1), start_date)
            target_freq_display = 'al término'
        else:
            try:
                freq_delta = PeriodicityChoices(target_frequency).get_relativedelta()
                target_freq_display = PeriodicityChoices(target_frequency).label
            except Exception:
                freq_delta = relativedelta(months=1)
                target_freq_display = '1 mes'

        growth_freq_display = ''
        g_delta = None
        if growth_value > 0 and growth_frequency:
            try:
                g_delta = PeriodicityChoices(growth_frequency).get_relativedelta()
                growth_freq_display = PeriodicityChoices(growth_frequency).label
            except Exception:
                g_delta = None

        
        route = None
        route_id = data.get('route_id')
        if route_id:
            route = Route.objects.filter(pk=route_id).first()
        if not route and customer:
            today = timezone.localdate()
            assignment = CustomerAssignment.objects.filter(
                customer=customer,
                start_date__lte=today
            ).filter(
                Q(end_date__isnull=True) | Q(end_date__gte=today)
            ).select_related('route').first()
            if not assignment:
                assignment = CustomerAssignment.objects.filter(
                    customer=customer,
                    end_date__isnull=True
                ).select_related('route').first()
            if not assignment:
                assignment = CustomerAssignment.objects.filter(
                    customer=customer
                ).order_by('-start_date').select_related('route').first()
            if assignment:
                route = assignment.route

        
        advisor_name = self.get_assigned_advisor_name(route, target_date=start_date)

        
        mandatory_classes = []
        complementary_classes = []
        mandatory_sum_base = Decimal('0.00')

        for item in classes_data:
            pc_id = item.get('product_class_id')
            pc = ProductClass.objects.filter(pk=pc_id).first()
            if not pc:
                continue

            is_mandatory = bool(item.get('is_mandatory'))
            try:
                req_t = Decimal(str(item.get('required_target') or '0'))
            except Exception:
                req_t = Decimal('0.00')

            row_info = {
                'product_class': pc,
                'is_mandatory': is_mandatory,
                'required_target': req_t,
            }

            if is_mandatory and req_t > 0:
                mandatory_classes.append(row_info)
                mandatory_sum_base += req_t
            else:
                complementary_classes.append(row_info)

        complementary_base = max(Decimal('0.00'), global_target_amount - mandatory_sum_base)

        
        period_columns = []
        current_start = start_date
        growth_multiplier = Decimal('1.00')
        next_growth_date = start_date + g_delta if (g_delta and growth_value > 0) else None

        for p_num in range(1, total_periods + 1):
            while next_growth_date and current_start >= next_growth_date:
                growth_multiplier *= (Decimal('1.00') + (growth_value / Decimal('100.00')))
                next_growth_date += g_delta

            current_end = current_start + freq_delta - relativedelta(days=1)
            if current_end > end_date:
                current_end = end_date

            p_global_target = (global_target_amount * growth_multiplier).quantize(Decimal('0.01'))
            p_mandatory_classes = []
            p_mandatory_sum = Decimal('0.00')

            for mc in mandatory_classes:
                p_mc_target = (mc['required_target'] * growth_multiplier).quantize(Decimal('0.01'))
                p_mandatory_classes.append({
                    'class_name': mc['product_class'].name.title(),
                    'target': p_mc_target,
                })
                p_mandatory_sum += p_mc_target

            p_comp_target = max(Decimal('0.00'), p_global_target - p_mandatory_sum)

            pct_growth_str = f"+{growth_value}%" if (growth_multiplier > 1) else ""

            period_columns.append({
                'number': p_num,
                'start_date': current_start,
                'end_date': current_end,
                'global_target': p_global_target,
                'mandatory_classes': p_mandatory_classes,
                'complementary_target': p_comp_target,
                'growth_pct_str': pct_growth_str,
            })

            current_start = current_start + freq_delta

        total_accumulated_target = sum(p['global_target'] for p in period_columns)

        
        clauses = [
            {
                'number': 1,
                'citation': '[1]',
                'title': 'CLÁUSULA PRIMERA [1] — VIGENCIA Y PERIODOS DE EVALUACIÓN',
                'text': (
                    f"El presente convenio tendrá una vigencia improrrogable del {start_date.strftime('%m/%Y')} al {end_date.strftime('%m/%Y')}. "
                    f"El periodo total comprende {duration_months} meses divididos en {total_periods} periodo(s) de evaluación con periodicidad {target_freq_display.lower()}."
                ),
            },
            {
                'number': 2,
                'citation': '[2]',
                'title': 'CLÁUSULA SEGUNDA [2] — OBJETO Y ENTREGA DEL BENEFICIO COMERCIAL',
                'text': (
                    f"La empresa se compromete a otorgar a favor del cliente {customer.name if customer else ''} "
                    f"el beneficio comercial consistente en '{benefit.name if benefit else ''}' "
                    f"({benefit.get_benefit_type_display() if benefit else ''}), "
                    f"con valor de referencia de ${benefit.cost:,.2f} MXN, sujeto al cabal y estricto cumplimiento de los consumos y cuotas pactadas en el presente instrumento."
                ),
            },
            {
                'number': 3,
                'citation': '[3]',
                'title': 'CLÁUSULA TERCERA [3] — CUOTA PERIÓDICA, META GLOBAL Y CONSUMO COMPROMETIDO',
                'text': (
                    f"El cliente se obliga a mantener una cuota de compras netas base de ${global_target_amount:,.2f} MXN por cada periodo de evaluación {target_freq_display.lower()}, "
                    f"alcanzando un acumulado total comprometido de ${total_accumulated_target:,.2f} MXN durante la vigencia del contrato. "
                    + (
                        f"Asimismo, se estipula una tasa de crecimiento proyectada del {growth_value}% con periodicidad {growth_freq_display.lower()} sobre las cuotas subsecuentes."
                        if growth_value > 0 and growth_freq_display else
                        "No se establece incremento porcentual a las cuotas durante la vigencia del convenio."
                    )
                ),
            },
            {
                'number': 4,
                'citation': '[4]',
                'title': 'CLÁUSULA CUARTA [4] — CONDICIONES DE CRÉDITO Y PLAZOS DE PAGO',
                'text': (
                    f"El otorgamiento del beneficio está condicionado a que el cliente mantenga su cuenta corriente sin adeudos vencidos, "
                    f"respetando el plazo de pago concedido de {customer.credit_days if customer and customer.credit_days else 0} días de crédito. "
                    f"Cualquier morosidad facultará a la empresa para suspender o rescindir de pleno derecho el beneficio comercial."
                ),
            },
            {
                'number': 5,
                'citation': '[5]',
                'title': 'CLÁUSULA QUINTA [5] — LÍNEAS DE PRODUCTO, CLASES OBLIGATORIAS Y COMPLEMENTARIAS',
                'text': (
                    (
                        f"De la cuota establecida, las siguientes clases de producto se fijan como OBLIGATORIAS: "
                        + ", ".join([f"{mc['product_class'].name.title()} (${mc['required_target']:,.2f} MXN)" for mc in mandatory_classes])
                        + f"; el remanente de ${complementary_base:,.2f} MXN podrá ser cubierto indistintamente con las clases participantes complementarias: "
                        + ", ".join([cc['product_class'].name.title() for cc in complementary_classes])
                        if mandatory_classes else
                        f"La totalidad de la cuota podrá ser cubierta indistintamente con cualquiera de las líneas y clases comerciales participantes seleccionadas: "
                        + ", ".join([cc['product_class'].name.title() for cc in complementary_classes])
                    )
                    + ". Todas las compras se computan en compras netas antes de IVA."
                ),
            },
            {
                'number': 6,
                'citation': '[6]',
                'title': 'CLÁUSULA SEXTA [6] — FACTURACIÓN POR PENALIZACIÓN DE INCUMPLIMIENTO',
                'text': (
                    f"En caso de que el cliente no alcance el 100% de la cuota pactada o del acumulado comprometido, "
                    f"se generará y emitirá una factura por concepto de penalización por la cantidad de ${penalty_amount:,.2f} MXN "
                    f"que el cliente se obliga incondicionalmente a liquidar dentro de los plazos comerciales acordados."
                    if penalty_amount > 0 else
                    "El incumplimiento de la meta pactada facultará a la empresa para revocar el beneficio comercial sin responsabilidad adicional."
                ),
            },
            {
                'number': 7,
                'citation': '[7]',
                'title': 'CLÁUSULA SÉPTIMA [7] — RESTITUCIÓN, EMBARGO, VALIDEZ Y JURISDICCIÓN',
                'text': (
                    "En caso de no cubrirse las cuotas pactadas o de negativa de pago de penalizaciones, el cliente se compromete a cubrir el valor comercial íntegro del bien otorgado, "
                    "o autoriza expresamente la restitución o embargo del beneficio otorgado. "
                    "Las partes ratifican el presente instrumento sin mediar vicio en el consentimiento, sometiéndose expresamente a los tribunales de Guadalajara, Jalisco."
                ),
            },
        ]

        matrix_periods = []
        for p in period_columns:
            growth_pct = Decimal('0.0')
            if p['growth_pct_str']:
                try:
                    growth_pct = Decimal(p['growth_pct_str'].replace('+', '').replace('%', ''))
                except Exception:
                    growth_pct = Decimal('0.0')
            matrix_periods.append({
                'period_number': p['number'],
                'start_date': p['start_date'],
                'end_date': p['end_date'],
                'target_amount': p['global_target'],
                'growth_pct': growth_pct,
            })

        mandatory_rows = []
        for mc in mandatory_classes:
            pc = mc['product_class']
            targets = []
            for p in period_columns:
                matching = next((item['target'] for item in p['mandatory_classes'] if item['class_name'] == pc.name.title()), Decimal('0.00'))
                targets.append(matching)
            mandatory_rows.append({
                'product_class': pc,
                'targets': targets,
                'total_class_target': sum(targets),
            })

        complementary_row = None
        if complementary_classes or not mandatory_classes:
            comp_targets = [p['complementary_target'] for p in period_columns]
            complementary_row = {
                'targets': comp_targets,
                'total_complementary_target': sum(comp_targets),
            }

        projection_matrix = {
            'periods': matrix_periods,
            'mandatory_rows': mandatory_rows,
            'complementary_row': complementary_row,
            'complementary_classes_names': [cc['product_class'].name.title() for cc in complementary_classes],
            'grand_total_target': total_accumulated_target,
        }

        return {
            'customer': customer,
            'benefit': benefit,
            'route': route,
            'advisor_name': advisor_name,
            'doc_id': doc_id,
            'agreement_type_display': dict(AgreementTypeChoices.choices).get(agreement_type, agreement_type),
            'start_date': start_date,
            'end_date': end_date,
            'duration_months': duration_months,
            'total_periods': total_periods,
            'target_freq_display': target_freq_display,
            'target_frequency_name': target_freq_display,
            'global_target_amount': global_target_amount,
            'total_accumulated_target': total_accumulated_target,
            'penalty_amount': penalty_amount,
            'growth_value': growth_value,
            'growth_freq_display': growth_freq_display,
            'mandatory_classes': mandatory_classes,
            'complementary_classes': complementary_classes,
            'mandatory_sum_base': mandatory_sum_base,
            'complementary_base': complementary_base,
            'period_columns': period_columns,
            'clauses': clauses,
            'projection_matrix': projection_matrix,
            'today': timezone.localdate(),
        }

    @transaction.atomic
    def create_customer_agreement(
        self,
        customer_id: str | None = None,
        benefit_id: int | None = None,
        agreement_type: str = AgreementTypeChoices.SHORT_TERM,
        start_date: Any = None,
        end_date: Any = None,
        global_target_amount: Decimal | None = None,
        target_frequency: str = PeriodicityChoices.MONTHLY,
        growth_value: Decimal = Decimal('0.00'),
        growth_frequency: str | None = None,
        penalty_amount: Decimal = Decimal('0.00'),
        related_doc: Any = None,
        signed: bool = False,
        benefit_already_provided: bool = False,
        doc_id: str | None = None,
        participating_classes_data: list[dict[str, Any]] | None = None,
        margin_warning_accepted: bool = False,
        user: Any = None,
        data: dict[str, Any] | None = None,
        targets_data: list[dict[str, Any]] | None = None,
        **kwargs,
    ) -> CustomerAgreement:
        """
        creates CustomerAgreement, AgreementClassTarget, and up-front generation
        of all AgreementEvaluationPeriod and AgreementPeriodClassResult records.
        guarantees doc_id uniqueness and sets immutability.
        """
        user = user or self.user
        payload = dict(data or {})
        payload.update(kwargs)
        if customer_id is not None:
            payload['customer_id'] = customer_id
        if benefit_id is not None:
            payload['benefit_id'] = benefit_id
        if agreement_type is not None:
            payload['agreement_type'] = agreement_type
        if start_date is not None:
            payload['start_date'] = start_date
        if end_date is not None:
            payload['end_date'] = end_date
        if global_target_amount is not None:
            payload['global_target_amount'] = global_target_amount
        if target_frequency is not None:
            payload['target_frequency'] = target_frequency
        if growth_value is not None:
            payload['growth_value'] = growth_value
        if growth_frequency is not None:
            payload['growth_frequency'] = growth_frequency
        if penalty_amount is not None:
            payload['penalty_amount'] = penalty_amount
        if related_doc is not None:
            payload['related_doc'] = related_doc
        if signed is not None:
            payload['signed'] = signed
        if benefit_already_provided is not None:
            payload['benefit_already_provided'] = benefit_already_provided
        if doc_id is not None:
            payload['doc_id'] = doc_id

        actual_targets = targets_data or participating_classes_data or payload.get('participating_classes_data') or []
        targets_data = actual_targets
        data = payload

        customer_id = data['customer_id']
        customers_service = CustomersService(user=user)
        if not customers_service.get_allowed_customers(can_view=True).filter(pk=customer_id).exists():
            raise PermissionsError(f"No tienes permiso para generar convenios para el cliente {customer_id}.")

        customer = Customer.objects.get(pk=customer_id)
        benefit = self.benefit_model.objects.get(pk=data['benefit_id'])

        route_id = data.get('route_id')
        route = Route.objects.filter(pk=route_id).first() if route_id else None
        if not route:
            today = timezone.localdate()
            assignment = CustomerAssignment.objects.filter(
                customer=customer,
                start_date__lte=today
            ).filter(
                Q(end_date__isnull=True) | Q(end_date__gte=today)
            ).select_related('route').first()
            if not assignment:
                assignment = CustomerAssignment.objects.filter(
                    customer=customer,
                    end_date__isnull=True
                ).select_related('route').first()
            if not assignment:
                assignment = CustomerAssignment.objects.filter(
                    customer=customer
                ).order_by('-start_date').select_related('route').first()
            if assignment:
                route = assignment.route

        if not route:
            raise ServiceError("No se pudo determinar una ruta activa para asociar al convenio.")

        start_date = parse_month_input(data['start_date'])
        end_date = parse_month_input(data.get('end_date'), is_end=True)

        if not start_date or not end_date:
            raise ServiceError("Fechas de inicio y fin requeridas.")

        doc_id = data.get('doc_id')
        if doc_id and str(doc_id).strip():
            doc_id = str(doc_id).strip().upper()
            if self.agreement_model.objects.filter(doc_id=doc_id).exists():
                raise ServiceError(f"El folio de convenio '{doc_id}' ya existe en el sistema. Ingrese un folio diferente.")
        else:
            doc_id = self.generate_random_doc_id()

        agreement = self.agreement_model.objects.create(
            customer=customer,
            route=route,
            benefit=benefit,
            doc_id=doc_id,
            agreement_type=data.get('agreement_type', AgreementTypeChoices.SHORT_TERM),
            start_date=start_date,
            end_date=end_date,
            global_target_amount=Decimal(str(data.get('global_target_amount') or '0')),
            target_frequency=data.get('target_frequency', PeriodicityChoices.MONTHLY),
            penalty_amount=Decimal(str(data.get('penalty_amount') or '0')),
            growth_value=Decimal(str(data.get('growth_value') or '0')),
            growth_frequency=data.get('growth_frequency') or '',
            related_doc=data.get('related_doc'),
            signed=bool(data.get('signed', False)),
            benefit_already_provided=bool(data.get('benefit_already_provided', False)),
            margin_warning_accepted=margin_warning_accepted,
            created_by=user,
        )

        created_targets = []
        for td in targets_data:
            pc_id = td.get('product_class_id')
            if not pc_id:
                continue
            is_mand = bool(td.get('is_mandatory'))
            req_t = Decimal(str(td.get('required_target') or '0'))
            created_targets.append(
                self.class_target_model.objects.create(
                    agreement=agreement,
                    product_class_id=pc_id,
                    required_target=req_t,
                    is_mandatory=is_mand,
                )
            )

        total_periods = get_periods_count(start_date, end_date, agreement.target_frequency)
        amortized_cost = (benefit.cost / Decimal(str(total_periods))).quantize(Decimal('0.01')) if total_periods > 0 else Decimal('0.00')

        if agreement.target_frequency in (PeriodicityChoices.AT_END, 'end'):
            freq_delta = relativedelta(end_date + timedelta(days=1), start_date)
        else:
            try:
                freq_delta = PeriodicityChoices(agreement.target_frequency).get_relativedelta()
            except Exception:
                freq_delta = relativedelta(months=1)

        g_delta = None
        if agreement.growth_value > 0 and agreement.growth_frequency:
            try:
                g_delta = PeriodicityChoices(agreement.growth_frequency).get_relativedelta()
            except Exception:
                g_delta = None

        current_start = start_date
        growth_multiplier = Decimal('1.00')
        next_growth_date = start_date + g_delta if g_delta else None

        for p_num in range(1, total_periods + 1):
            while next_growth_date and current_start >= next_growth_date:
                growth_multiplier *= (Decimal('1.00') + (agreement.growth_value / Decimal('100.00')))
                next_growth_date += g_delta

            current_end = current_start + freq_delta - relativedelta(days=1)
            if current_end > end_date:
                current_end = end_date

            p_global_target = (agreement.global_target_amount * growth_multiplier).quantize(Decimal('0.01'))

            period = self.evaluation_period_model.objects.create(
                agreement=agreement,
                period_number=p_num,
                start_date=current_start,
                end_date=current_end,
                expected_global_target=p_global_target,
                status=PeriodStatusChoices.PENDING,
                amortized_benefit_cost=amortized_cost,
            )

            for ct in created_targets:
                class_target_amt = (ct.required_target * growth_multiplier).quantize(Decimal('0.01'))
                self.period_class_result_model.objects.create(
                    evaluation_period=period,
                    product_class=ct.product_class,
                    expected_class_target=class_target_amt,
                )

            current_start = current_start + freq_delta

        return agreement

    @transaction.atomic
    def update_agreement_execution(
        self,
        *,
        pk: int | str,
        signed: Optional[bool] = None,
        benefit_already_provided: Optional[bool] = None,
        file_obj: Any = None,
        related_doc: Any = None,
    ) -> CustomerAgreement:
        """
        updates execution state (signed, benefit_already_provided, and/or related_doc)
        of an existing agreement. only authorized users (can_edit_agreement) can perform this.
        """
        if not self.can_edit_agreement:
            raise PermissionsError("No tienes permiso para modificar el convenio ni su documentación.")

        agreement = self.read_agreement(pk)
        update_fields = ['updated_at']

        if signed is not None:
            agreement.signed = bool(signed)
            update_fields.append('signed')

        if benefit_already_provided is not None:
            agreement.benefit_already_provided = bool(benefit_already_provided)
            update_fields.append('benefit_already_provided')

        doc = file_obj if file_obj is not None else related_doc
        if doc is not None:
            agreement.related_doc = doc
            update_fields.append('related_doc')

        agreement.save(update_fields=list(set(update_fields)))
        return agreement

    def update_agreement_document(self, *, pk: int | str, file_obj: Any = None, related_doc: Any = None) -> CustomerAgreement:
        """
        only the related_doc file is updated on the existing agreement.
        enforces can_edit_agreement permission.
        """
        doc = file_obj if file_obj is not None else related_doc
        if not doc:
            raise ValidationError("No se proporcionó ningún archivo para actualizar.")

        return self.update_agreement_execution(pk=pk, file_obj=doc)

    @transaction.atomic
    def evaluate_pending_periods(self, agreement_id: int | str | None = None, pk: int | str | None = None) -> tuple[int, int]:
        """
        evaluates periods that are pending or ended within the last 45 days (or all periods of a specific agreement if agreement_id/pk given).
        updates achieved sales, statuses, penalties and margins in batch.
        """
        target_agreement_id = agreement_id or pk
        today = timezone.localdate()
        limit_date = today - timedelta(days=45)

        periods_qs = self.evaluation_period_model.objects.select_related('agreement').prefetch_related(
            'agreement__class_targets',
            'class_results'
        )

        if target_agreement_id:
            periods = periods_qs.filter(agreement_id=target_agreement_id)
        else:
            periods = periods_qs.filter(
                agreement__start_date__lte=today
            ).filter(
                Q(agreement__end_date__isnull=True) | Q(agreement__end_date__gte=limit_date)
            ).filter(
                Q(status=PeriodStatusChoices.PENDING) | Q(end_date__gte=limit_date)
            )

        if not periods.exists():
            return 0, 0


        customer_ids = set()
        min_date = None
        max_date = None

        for p in periods:
            customer_ids.add(p.agreement.customer_id)
            if min_date is None or p.start_date < min_date:
                min_date = p.start_date
            if max_date is None or p.end_date > max_date:
                max_date = p.end_date

        sales_data = self.sale_transaction_model.objects.filter(
            customer_id__in=customer_ids,
            sale_date__gte=min_date,
            sale_date__lte=max_date
        ).values('customer_id', 'sale_date', 'product_class_id', 'net_amount', 'profit')

        sales_by_customer = {}
        for row in sales_data:
            cid = row['customer_id']
            if cid not in sales_by_customer:
                sales_by_customer[cid] = []
            sales_by_customer[cid].append(row)

        agreements_affected = set()
        periods_to_update = []
        class_results_to_update = []

        for period in periods:
            agreement = period.agreement
            agreements_affected.add(agreement.id)

            c_sales = sales_by_customer.get(agreement.customer_id, [])
            p_sales = [
                s for s in c_sales
                if period.start_date <= s['sale_date'] <= period.end_date
            ]

            total_net = sum((s['net_amount'] or Decimal('0.00')) for s in p_sales)
            total_profit = sum((s['profit'] or Decimal('0.00')) for s in p_sales)
            period.achieved_global_sales = total_net

            sales_by_class = {}
            for s in p_sales:
                cls_id = s['product_class_id']
                sales_by_class[cls_id] = sales_by_class.get(cls_id, Decimal('0.00')) + (s['net_amount'] or Decimal('0.00'))

            targets_by_class = {
                t.product_class_id: t for t in agreement.class_targets.all()
            }

            achieved_mandatory = True
            for cr in period.class_results.all():
                cls_id = cr.product_class_id
                c_net = sales_by_class.get(cls_id, Decimal('0.00'))
                cr.achieved_class_sales = c_net
                class_results_to_update.append(cr)

                tgt = targets_by_class.get(cls_id)
                if tgt and tgt.is_mandatory:
                    if c_net < cr.expected_class_target:
                        achieved_mandatory = False

            achieved_global = (period.achieved_global_sales >= period.expected_global_target)

            if achieved_global and achieved_mandatory:
                period.status = PeriodStatusChoices.ACHIEVED
                period.penalty_applied = False
                period.observations = "Objetivo global y metas obligatorias alcanzadas."
            else:
                if today <= period.end_date:
                    period.status = PeriodStatusChoices.PENDING
                    period.penalty_applied = False
                    period.observations = "En progreso. Aún no se alcanza la meta."
                else:
                    period.status = PeriodStatusChoices.FAILED
                    period.penalty_applied = True
                    period.observations = "Periodo vencido sin alcanzar objetivo global o metas obligatorias."

            if period.penalty_applied:
                period.period_profit = total_profit
            else:
                period.period_profit = total_profit - period.amortized_benefit_cost

            if total_net > 0:
                calc_margin = (period.period_profit / total_net) * Decimal('100.00')
                if calc_margin > Decimal('999.99'):
                    period.period_margin = Decimal('999.99')
                elif calc_margin < Decimal('-999.99'):
                    period.period_margin = Decimal('-999.99')
                else:
                    period.period_margin = calc_margin.quantize(Decimal('0.01'))
            else:
                period.period_margin = Decimal('0.00')

            periods_to_update.append(period)

        if class_results_to_update:
            self.period_class_result_model.objects.bulk_update(class_results_to_update, ['achieved_class_sales'])

        if periods_to_update:
            self.evaluation_period_model.objects.bulk_update(periods_to_update, [
                'achieved_global_sales', 'status', 'penalty_applied', 'observations', 'period_profit', 'period_margin'
            ])

        return len(periods_to_update), len(agreements_affected)


class CustomerAgreementsStats:
    def __init__(self, service: Optional[CustomerAgreementsService] = None, agreements_service: Optional[CustomerAgreementsService] = None):
        self.service = service or agreements_service

    def stats(self, qs: Optional[QuerySet] = None) -> dict[str, Any]:
        base_qs = qs if qs is not None else (self.service.read_agreements() if self.service else CustomerAgreement.objects.none())

        today = timezone.localdate()
        agg = base_qs.aggregate(
            total_agreements=Count('pk', distinct=True),
            unique_customers=Count('customer_id', distinct=True),
            active_agreements=Count('pk', filter=Q(start_date__lte=today, end_date__gte=today), distinct=True),
            expired_agreements=Count('pk', filter=Q(end_date__lt=today), distinct=True),
            upcoming_agreements=Count('pk', filter=Q(start_date__gt=today), distinct=True),
            total_target=Sum('global_target_amount'),
            total_penalties=Sum('penalty_amount'),
        )

        total_agreements = agg['total_agreements'] or 0
        unique_customers = agg['unique_customers'] or 0
        active_agreements = agg['active_agreements'] or 0
        expired_agreements = agg['expired_agreements'] or 0
        upcoming_agreements = agg['upcoming_agreements'] or 0
        total_target = agg['total_target'] or Decimal('0.00')
        total_penalties = agg['total_penalties'] or Decimal('0.00')

        period_agg = AgreementEvaluationPeriod.objects.filter(agreement__in=base_qs).aggregate(
            total_expected=Sum('expected_global_target'),
            total_achieved=Sum('achieved_global_sales'),
        )
        total_expected_target = period_agg['total_expected'] or Decimal('0.00')
        total_achieved_sales = period_agg['total_achieved'] or Decimal('0.00')

        overall_compliance_pct = Decimal('0.00')
        if total_expected_target > 0:
            overall_compliance_pct = (total_achieved_sales / total_expected_target) * Decimal('100.00')

        return {
            'total_agreements': total_agreements,
            'unique_customers': unique_customers,
            'active_agreements': active_agreements,
            'expired_agreements': expired_agreements,
            'upcoming_agreements': upcoming_agreements,
            'total_expected_target': total_expected_target,
            'total_achieved_sales': total_achieved_sales,
            'overall_compliance_pct': overall_compliance_pct,
            'total_count': total_agreements,
            'active_count': active_agreements,
            'inactive_count': expired_agreements,
            'total_target': total_target,
            'total_penalties': total_penalties,
        }
