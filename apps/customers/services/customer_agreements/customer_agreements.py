import re
import calendar
from decimal import Decimal
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.db.models import Sum, Q
from django.db.models.functions import TruncMonth

from apps.core.models import (
    Customer, CommercialBenefit, CustomerAgreement, AgreementClassTarget,
    AgreementEvaluationPeriod, AgreementPeriodClassResult, CustomerClassMargin,
    SaleTransaction, SystemModule
)
from apps.sales.services.sale_transactions.sale_transactions_crud import SaleTransactionCRUD
from apps.data_admin.services.data_history.data_history_crud import ActivityLogger, DataHistory


class MarginValidationException(Exception):
    def __init__(self, message, simulated_margin, min_margin):
        self.message = message
        self.simulated_margin = simulated_margin
        self.min_margin = min_margin
        super().__init__(self.message)


def parse_periodicity(period_id):
    match = re.match(r'^(\d+)([dmsy])$', period_id)
    if not match:
        raise ValueError(f"Invalid periodicity format: {period_id}")
    return int(match.group(1)), match.group(2)

def get_relativedelta_for_period(val, unit):
    if unit == 'd':
        return relativedelta(days=val)
    elif unit == 'w':
        return relativedelta(weeks=val)
    elif unit == 'm':
        return relativedelta(months=val)
    elif unit == 'y':
        return relativedelta(years=val)
    return relativedelta()

def get_periods_count(start_date, end_date, freq_id):
    if not end_date:
        return 1
    val, unit = parse_periodicity(freq_id)
    delta = get_relativedelta_for_period(val, unit)
    count = 0
    current = start_date
    while current <= end_date:
        count += 1
        current += delta
    return count if count > 0 else 1

def parse_month_input(date_str, is_end=False):
    if not date_str:
        return None
    if len(date_str) == 7:
        y, m = map(int, date_str.split('-'))
        if is_end:
            last_day = calendar.monthrange(y, m)[1]
            return date(y, m, last_day)
        return date(y, m, 1)
    return date.fromisoformat(date_str)


class CustomerAgreementService:
    def __init__(self):
        self.sale_crud = SaleTransactionCRUD()

    def read(self, allowed_routes, **kwargs):
        queryset = CustomerAgreement.objects.filter(route__in=allowed_routes)

        if kwargs.get('status'):
            status_list = kwargs['status']
            if not isinstance(status_list, (list, tuple, set)):
                status_list = [status_list]
            
            today = date.today()
            q_status = Q()
            
            if 'active' in status_list:
                q_status |= Q(start_date__lte=today) & (Q(end_date__isnull=True) | Q(end_date__gte=today))
            if 'inactive' in status_list:
                q_status |= Q(start_date__gt=today) | (Q(end_date__isnull=False) & Q(end_date__lt=today))
                
            if q_status:
                queryset = queryset.filter(q_status)

        if kwargs.get('created_start'):
            queryset = queryset.filter(start_date__gte=kwargs['created_start'])
        if kwargs.get('created_end'):
            queryset = queryset.filter(start_date__lte=kwargs['created_end'])

        if kwargs.get('finished_start'):
            queryset = queryset.filter(end_date__gte=kwargs['finished_start'])
        if kwargs.get('finished_end'):
            queryset = queryset.filter(end_date__lte=kwargs['finished_end'])

        fk_fields = {
            'routes': 'route_id__in',
            'warehouses': 'route__warehouse_id__in',
            'regions': 'route__warehouse__region_id__in',
            'customers': 'customer_id__in'
        }
        
        for param, lookup in fk_fields.items():
            value = kwargs.get(param)
            if value:
                if not isinstance(value, (list, tuple, set)):
                    value = [value]
                queryset = queryset.filter(**{lookup: value})
                
        return queryset.select_related('customer', 'route', 'benefit', 'target_freq').distinct()
        
    def read_details(self, agreement_id, allowed_routes):
        agreement = CustomerAgreement.objects.select_related(
            'customer', 'route', 'benefit', 'target_freq', 'penalty_freq', 'growth_freq'
        ).prefetch_related(
            'class_targets__product_class'
        ).get(id=agreement_id)
        
        if not allowed_routes.filter(id=agreement.route_id).exists():
            return None
        
        customer = agreement.customer
        
        class_margins = CustomerClassMargin.objects.filter(customer=customer).select_related('product_class')
        
        eval_periods = list(AgreementEvaluationPeriod.objects.filter(agreement=agreement).order_by('period_number'))
        
        for period in eval_periods:
            period.penalty_amount_applied = agreement.penalty_amount if period.penalty_applied else Decimal('0.00')
            if period.penalty_applied:
                period.gross_profit = period.period_profit
            else:
                period.gross_profit = period.period_profit + period.amortized_benefit_cost
        
        period_results = AgreementPeriodClassResult.objects.filter(
            evaluation_period__agreement=agreement
        ).select_related('product_class', 'evaluation_period')
        
        return {
            'customer': {
                'data': customer,
                'class_margin': class_margins,
                'agreement': agreement,
                'eval_periods': eval_periods,
                'period_results': period_results
            }
        }
        

    def validate_agreement_margin(self, customer_id, benefit_id, product_class_ids, eval_start, eval_end, agreement_start_date, agreement_end_date, target_freq_id):
        """
        Calcula margen real histórico, simula impacto de amortización y cruza contra mínimo exigido 
        usando evaluación bicondicional.
        """

        start_date = parse_month_input(eval_start)
        end_date = parse_month_input(eval_end, is_end=True)
        agr_start = parse_month_input(agreement_start_date)
        agr_end = parse_month_input(agreement_end_date, is_end=True)
        
        delta = relativedelta(end_date, start_date)
        hist_months = delta.years * 12 + delta.months + (1 if delta.days > 0 else 0)
        if hist_months <= 0:
            hist_months = 1

        sales = SaleTransaction.objects.filter(
            customer_id=customer_id,
            sale_date__gte=start_date,
            sale_date__lte=end_date
        )
        if product_class_ids:
            sales = sales.filter(product_class_id__in=product_class_ids)

        totals = sales.aggregate(
            total_net=Sum('net_amount'),
            total_profit=Sum('profit')
        )
        
        total_net = totals['total_net'] or Decimal('0.00')
        total_profit = totals['total_profit'] or Decimal('0.00')

        if total_net == 0:
            return True, None, None, False, {}
            
        benefit = CommercialBenefit.objects.get(id=benefit_id)
        
        total_periods = get_periods_count(agr_start, agr_end, target_freq_id)
        cme = benefit.cost / total_periods
        
        # Check partial periods
        agr_delta = relativedelta(agr_end + timedelta(days=1), agr_start)
        agr_duration_months = agr_delta.years * 12 + agr_delta.months
        
        val, unit = parse_periodicity(target_freq_id)
        delta = get_relativedelta_for_period(val, unit)
        
        periodicity_months = val if unit == 'm' else (val * 12 if unit == 'y' else 1)
        has_partial_periods = False
        if hist_months % periodicity_months != 0:
            has_partial_periods = True
            
        hist_periods_count = get_periods_count(start_date, end_date, target_freq_id)
        past_cost = cme * hist_periods_count

        # A) Margen Neto Acumulado Simulado y Real
        simulated_net_margin = ((total_profit - past_cost) / total_net) * Decimal('100.0')
        historic_margin = (total_profit / total_net) * Decimal('100.0') if total_net > 0 else Decimal('0.00')

        # B) Margen Promedio Simulado por Periodo (Dinámico)
        current_start = start_date
        period_margins = []
        hist_period_margins = []
        
        while current_start <= end_date:
            current_end = current_start + delta - relativedelta(days=1)
            if current_end > end_date:
                current_end = end_date
                
            period_sales = sales.filter(sale_date__gte=current_start, sale_date__lte=current_end)
            p_agg = period_sales.aggregate(p_net=Sum('net_amount'), p_profit=Sum('profit'))
            p_net = p_agg['p_net'] or Decimal('0.00')
            p_profit = p_agg['p_profit'] or Decimal('0.00')
            
            if p_net > 0:
                p_margin = ((p_profit - cme) / p_net) * Decimal('100.0')
                p_hist = (p_profit / p_net) * Decimal('100.0')
                period_margins.append(p_margin)
                hist_period_margins.append(p_hist)
                
            current_start = current_start + delta
                
        avg_period_margin = sum(period_margins) / len(period_margins) if period_margins else Decimal('0.00')
        avg_hist_period_margin = sum(hist_period_margins) / len(hist_period_margins) if hist_period_margins else Decimal('0.00')

        min_margins = CustomerClassMargin.objects.filter(
            customer_id=customer_id
        )
        if product_class_ids:
            min_margins = min_margins.filter(product_class_id__in=product_class_ids)
            
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
            'simulated_total_periods': total_periods
        }

        if not min_margins.exists():
            return True, simulated_net_margin, None, False, result_data
            
        max_required_margin = max(m.min_margin_percentage for m in min_margins)
        
        if simulated_net_margin < max_required_margin:
            if avg_period_margin >= max_required_margin:
                return False, simulated_net_margin, max_required_margin, True, result_data # Alerta volatilidad
            return False, simulated_net_margin, max_required_margin, False, result_data
            
        return True, simulated_net_margin, max_required_margin, False, result_data


    @transaction.atomic
    def create_customer_agreement(self, user, data, targets_data, margin_warning_accepted=False):
        """
        Creates the CustomerAgreement, its targets, and ALL evaluation periods upfront.
        Logs to DataHistory if margin warning was accepted.
        """
        customer = Customer.objects.get(id=data['customer_id'])
        route = customer.route
        benefit = CommercialBenefit.objects.get(id=data['benefit_id'])
        
        start_date = parse_month_input(data['start_date'])
        end_date = parse_month_input(data.get('end_date'), is_end=True)
        
        agreement = CustomerAgreement.objects.create(
            customer=customer,
            route=route,
            benefit=benefit,
            doc_id=data.get('doc_id'),
            agreement_name=data['agreement_name'],
            agreement_type=data.get('agreement_type', CustomerAgreement.TypesChoices.SHORT_TERM),
            start_date=start_date,
            end_date=end_date,
            global_target_amount=Decimal(data.get('global_target_amount', 0)),
            target_freq_id=data['target_freq_id'],
            penalty_freq_id=data.get('penalty_freq_id'),
            growth_freq_id=data.get('growth_freq_id'),
            penalty_amount=Decimal(data.get('penalty_amount', 0)),
            growth_value=Decimal(data.get('growth_value', 0)),
            related_doc=data.get('related_doc')
        )
        for td in targets_data:
            AgreementClassTarget.objects.create(
                agreement=agreement,
                product_class_id=td['product_class_id'],
                required_target=Decimal(td['required_target']),
                is_mandatory=td.get('is_mandatory', True)
            )
            
        total_periods = get_periods_count(start_date, end_date, agreement.target_freq_id)
        amortized_cost = benefit.cost / total_periods
        
        val, unit = parse_periodicity(agreement.target_freq_id)
        delta = get_relativedelta_for_period(val, unit)
        
        current_start = start_date
        period_num = 1
        
        growth_multiplier = Decimal('1.00')
        next_growth_date = None
        delta_growth = None
        
        if agreement.growth_freq_id and agreement.growth_value > 0:
            g_val, g_unit = parse_periodicity(agreement.growth_freq_id)
            delta_growth = get_relativedelta_for_period(g_val, g_unit)
            next_growth_date = start_date + delta_growth
        
        while end_date and current_start <= end_date:
            while next_growth_date and current_start >= next_growth_date:
                growth_multiplier *= (Decimal('1') + (agreement.growth_value / Decimal('100')))
                next_growth_date += delta_growth
                
            current_end = current_start + delta - relativedelta(days=1)
            if current_end > end_date:
                current_end = end_date
                
            period_global_target = (agreement.global_target_amount * growth_multiplier).quantize(Decimal('0.01'))
                
            period = AgreementEvaluationPeriod.objects.create(
                agreement=agreement,
                period_number=period_num,
                start_date=current_start,
                end_date=current_end,
                expected_global_target=period_global_target,
                status=AgreementEvaluationPeriod.StatusChoices.PENDING,
                amortized_benefit_cost=amortized_cost
            )
            
            for ct in agreement.class_targets.all():
                class_target_amount = (ct.required_target * growth_multiplier).quantize(Decimal('0.01'))
                AgreementPeriodClassResult.objects.create(
                    evaluation_period=period,
                    product_class=ct.product_class,
                    expected_class_target=class_target_amount
                )
                
            current_start = current_start + delta
            period_num += 1
            
        module, _ = SystemModule.objects.get_or_create(name='Clientes', defaults={'url_name': 'customers:customer_agreements', 'section_id': 1})
        
        changes = {'agreement_id': agreement.id, 'margin_warning_accepted': margin_warning_accepted}
        description = "Creación de convenio de cliente."
        if margin_warning_accepted:
            description += " (Se omitió la alerta de margen financiero bajo al autorizar)."

        ActivityLogger.log_create(
            user=user,
            obj=agreement,
            module=module,
            description=description,
            changes=changes
        )
        
        return agreement

    @transaction.atomic
    def evaluate_all_pending_periods(self):
        """
        Evaluates all periods where end_date is within the last 45 days or in the future.
        Updates status and applies penalties.
        """

        today = date.today()
        limit_date = today - timedelta(days=45)
        
        periods = AgreementEvaluationPeriod.objects.filter(
            agreement__start_date__lte=today
        ).filter(
            Q(agreement__end_date__isnull=True) | Q(agreement__end_date__gte=limit_date)
        ).filter(
            Q(status=AgreementEvaluationPeriod.StatusChoices.PENDING) | Q(end_date__gte=limit_date)
        ).select_related('agreement').prefetch_related(
            'agreement__class_targets',
            'class_results'
        )
        
        if not periods:
            return 0, 0
            
        customer_ids = set()
        min_date = None
        max_date = None
        
        for period in periods:
            customer_ids.add(period.agreement.customer_id)
            if min_date is None or period.start_date < min_date:
                min_date = period.start_date
            if max_date is None or period.end_date > max_date:
                max_date = period.end_date
                
        # Fetch all relevant sales in a single query
        sales_data = SaleTransaction.objects.filter(
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
            
            customer_sales = sales_by_customer.get(agreement.customer_id, [])
            period_sales = [
                s for s in customer_sales
                if period.start_date <= s['sale_date'] <= period.end_date
            ]
            
            total_net = sum((s['net_amount'] or Decimal('0.00')) for s in period_sales)
            total_profit = sum((s['profit'] or Decimal('0.00')) for s in period_sales)
            
            period.achieved_global_sales = total_net
            
            sales_by_class = {}
            for s in period_sales:
                cls_id = s['product_class_id']
                net = s['net_amount'] or Decimal('0.00')
                sales_by_class[cls_id] = sales_by_class.get(cls_id, Decimal('0.00')) + net
            
            targets_by_class = {
                target.product_class_id: target
                for target in agreement.class_targets.all()
            }
            
            achieved_mandatory = True
            for class_result in period.class_results.all():
                class_id = class_result.product_class_id
                class_net = sales_by_class.get(class_id, Decimal('0.00'))
                
                class_result.achieved_class_sales = class_net
                class_results_to_update.append(class_result)
                
                target = targets_by_class.get(class_id)
                if target and target.is_mandatory:
                    if class_net < class_result.expected_class_target:
                        achieved_mandatory = False

            achieved_global = period.achieved_global_sales >= period.expected_global_target
            
            if achieved_global and achieved_mandatory:
                period.status = AgreementEvaluationPeriod.StatusChoices.ACHIEVED
                period.penalty_applied = False
                period.observations = ""
            else:
                if today <= period.end_date:
                    period.status = AgreementEvaluationPeriod.StatusChoices.PENDING
                    period.penalty_applied = False
                    period.observations = "En progreso. Aún no se alcanza la meta."
                else:
                    period.status = AgreementEvaluationPeriod.StatusChoices.FAILED
                    period.penalty_applied = True
                    period.observations = "Meta global o metas obligatorias no alcanzadas."
                    
            if period.penalty_applied:
                period.period_profit = total_profit
            else:
                period.period_profit = total_profit - period.amortized_benefit_cost
                
            if total_net > 0:
                period.period_margin = (period.period_profit / total_net) * Decimal('100.00')
            else:
                period.period_margin = Decimal('0.00')
                
            periods_to_update.append(period)
            
        if class_results_to_update:
            AgreementPeriodClassResult.objects.bulk_update(class_results_to_update, ['achieved_class_sales'])
            
        if periods_to_update:
            AgreementEvaluationPeriod.objects.bulk_update(periods_to_update, [
                'achieved_global_sales', 'status', 'penalty_applied', 'observations', 'period_profit', 'period_margin'
            ])
            
        return len(periods), len(agreements_affected)