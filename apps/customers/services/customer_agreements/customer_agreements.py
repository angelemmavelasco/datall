
from decimal import Decimal
from datetime import date
from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.db.models import Sum, Q

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


class CustomerAgreementService:
    def __init__(self):
        self.sale_crud = SaleTransactionCRUD()

    def validate_agreement_margin(self, customer_id, benefit_id, product_class_ids, start_date, end_date):
        """
        Paso A, B, C: Calcula margen real histórico, simula impacto de amortización y cruza contra mínimo exigido.
        """
        start_date = date.fromisoformat(start_date)
        end_date = date.fromisoformat(end_date)
        
        # Calculate months in the range
        delta = relativedelta(end_date, start_date)
        months = delta.years * 12 + delta.months + (1 if delta.days > 0 else 0)
        if months <= 0:
            months = 1

        # A: historical margin
        # We need the customer's route for read permissions? 
        # For the service, we can fetch directly or assume caller validated access.
        # But SaleTransactionCRUD.read requires allowed_routes. 
        # To bypass UI restrictions internally, we fetch all sales for this customer and classes.
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
            # Cannot calculate margin if no sales
            return True, None, None
            
        benefit = CommercialBenefit.objects.get(id=benefit_id)
        
        # B: Amortization simulation
        amortized_cost = benefit.cost / benefit.amortization_periods
        simulated_profit = total_profit - amortized_cost
        simulated_margin = (simulated_profit / total_net) * Decimal('100.0')

        # C: Cross with Minimum Margin
        # Get min_margin_percentage for customer and product_class_ids
        min_margins = CustomerClassMargin.objects.filter(
            customer_id=customer_id
        )
        if product_class_ids:
            min_margins = min_margins.filter(product_class_id__in=product_class_ids)
            
        if not min_margins.exists():
            return True, simulated_margin, None
            
        # Get the highest minimum margin required among the classes
        max_required_margin = max(m.min_margin_percentage for m in min_margins)
        
        if simulated_margin < max_required_margin:
            return False, simulated_margin, max_required_margin
            
        return True, simulated_margin, max_required_margin

    @transaction.atomic
    def create_customer_agreement(self, user, data, targets_data, margin_warning_accepted=False):
        """
        Creates the CustomerAgreement, its targets, and initial evaluation periods.
        Logs to DataHistory if margin warning was accepted.
        """
        customer = Customer.objects.get(id=data['customer_id'])
        route = customer.route
        benefit = CommercialBenefit.objects.get(id=data['benefit_id'])
        
        agreement = CustomerAgreement.objects.create(
            customer=customer,
            route=route,
            benefit=benefit,
            doc_id=data.get('doc_id'),
            agreement_name=data['agreement_name'],
            agreement_type=data.get('agreement_type', CustomerAgreement.TypesChoices.SHORT_TERM),
            start_date=data['start_date'],
            end_date=data.get('end_date'),
            global_target_amount=Decimal(data.get('global_target_amount', 0)),
            target_freq_id=data['target_freq_id'],
            penalty_freq_id=data.get('penalty_freq_id'),
            growth_freq_id=data.get('growth_freq_id'),
            penalty_amount=Decimal(data.get('penalty_amount', 0)),
            growth_value=Decimal(data.get('growth_value', 0)),
            related_doc=data.get('related_doc')
        )
        
        # Create targets
        for td in targets_data:
            AgreementClassTarget.objects.create(
                agreement=agreement,
                product_class_id=td['product_class_id'],
                required_target=Decimal(td['required_target']),
                is_mandatory=td.get('is_mandatory', True)
            )
            
        # Generate initial evaluation period (just 1 for now, next ones generated dynamically on evaluation)
        # or we could generate them all until end_date if it exists. 
        # For simplicity, we create the first period.
        # target_freq could be 'mensual' for example.
        end_date_period = agreement.start_date + relativedelta(months=1) - relativedelta(days=1)
        period = AgreementEvaluationPeriod.objects.create(
            agreement=agreement,
            period_number=1,
            start_date=agreement.start_date,
            end_date=end_date_period,
            expected_global_target=agreement.global_target_amount,
            status=AgreementEvaluationPeriod.StatusChoices.PENDING,
            amortized_benefit_cost=benefit.cost / benefit.amortization_periods
        )
        
        # Create class results for period
        for ct in agreement.class_targets.all():
            AgreementPeriodClassResult.objects.create(
                evaluation_period=period,
                product_class=ct.product_class,
                expected_class_target=ct.required_target
            )

        # Log creation
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
        Evaluates all pending periods where end_date has passed.
        Updates status, applies penalties, and creates next periods with growth rules.
        """
        today = date.today()
        pending_periods = AgreementEvaluationPeriod.objects.filter(
            status=AgreementEvaluationPeriod.StatusChoices.PENDING,
            end_date__lt=today
        ).select_related('agreement')
        
        for period in pending_periods:
            agreement = period.agreement
            
            # Get real sales for period
            sales = SaleTransaction.objects.filter(
                customer=agreement.customer,
                sale_date__gte=period.start_date,
                sale_date__lte=period.end_date
            )
            
            # Global achieved
            total_net = sales.aggregate(Sum('net_amount'))['net_amount__sum'] or Decimal('0.00')
            period.achieved_global_sales = total_net
            
            # Class achieved
            achieved_mandatory = True
            for class_result in period.class_results.all():
                class_net = sales.filter(product_class=class_result.product_class).aggregate(Sum('net_amount'))['net_amount__sum'] or Decimal('0.00')
                class_result.achieved_class_sales = class_net
                class_result.save()
                
                # check if mandatory target was reached
                target = agreement.class_targets.filter(product_class=class_result.product_class).first()
                if target and target.is_mandatory:
                    if class_net < class_result.expected_class_target:
                        achieved_mandatory = False

            # Check if global target achieved
            achieved_global = period.achieved_global_sales >= period.expected_global_target
            
            if achieved_global and achieved_mandatory:
                period.status = AgreementEvaluationPeriod.StatusChoices.ACHIEVED
            else:
                period.status = AgreementEvaluationPeriod.StatusChoices.FAILED
                period.penalty_applied = True # Should trigger something else depending on penalty_freq
                period.observations = "Meta global o metas obligatorias no alcanzadas."
                
            period.save()
            
            # Generate next period if agreement is still active
            # Assuming target_freq is monthly for evaluation
            if not agreement.end_date or period.end_date < agreement.end_date:
                next_start = period.end_date + relativedelta(days=1)
                next_end = next_start + relativedelta(months=1) - relativedelta(days=1)
                
                # Apply growth
                next_global_target = period.expected_global_target
                
                # Simplification: assuming growth is evaluated yearly (e.g. if period_number % 12 == 0)
                # In real scenario, it depends on growth_freq and its meaning.
                if agreement.growth_freq and period.period_number % 12 == 0:
                    # growth_value could be % or fixed
                    next_global_target += (next_global_target * (agreement.growth_value / 100))
                    
                next_period = AgreementEvaluationPeriod.objects.create(
                    agreement=agreement,
                    period_number=period.period_number + 1,
                    start_date=next_start,
                    end_date=next_end,
                    expected_global_target=next_global_target,
                    status=AgreementEvaluationPeriod.StatusChoices.PENDING,
                    amortized_benefit_cost=period.amortized_benefit_cost
                )
                
                for ct in agreement.class_targets.all():
                    # Apply same growth to class target if needed, assuming proportional
                    growth_ratio = (next_global_target / period.expected_global_target) if period.expected_global_target > 0 else 1
                    next_class_target = ct.required_target * growth_ratio
                    AgreementPeriodClassResult.objects.create(
                        evaluation_period=next_period,
                        product_class=ct.product_class,
                        expected_class_target=next_class_target
                    )