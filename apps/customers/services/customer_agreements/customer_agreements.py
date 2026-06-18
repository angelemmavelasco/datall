import uuid
from decimal import Decimal
from datetime import timedelta
from dateutil.relativedelta import relativedelta
from django.db import transaction

from apps.core.models import (
    CustomerAgreement,
    AgreementProductLine,
    AgreementEvaluationPeriod,
    AgreementPeriodLineTarget,
    Customer,
    Route,
    Benefit,
    Periodicity,
    ProductClass
)

class CustomerAgreementCRUD:

    @classmethod
    @transaction.atomic
    def create_agreement(cls, data):
        """
        data dictionary should contain:
        - customer_id
        - route_id
        - agreement_type (lt, mt, st)
        - doc_id (optional)
        - agreed_benefit_id
        - start_date
        - end_date
        - target_freq_id (optional, None means 'end of contract')
        - target_amount (required if target_freq is provided, or as global target)
        - penalty_freq_id
        - penalty_amount
        - growth_freq_id (optional)
        - growth_value (optional)
        - related_doc (file, optional)
        - product_lines: list of dicts [{'product_class_id': 'id', 'target': 0.00}]
        """
        # 1. Generate doc_id if not provided
        doc_id = data.get('doc_id')
        if not doc_id:
            doc_id = str(uuid.uuid4()).split('-')[-1][:7].upper()

        target_freq = None
        if data.get('target_freq_id'):
            target_freq = Periodicity.objects.get(id=data['target_freq_id'])

        penalty_freq = None
        if data.get('penalty_freq_id'):
            penalty_freq = Periodicity.objects.get(id=data['penalty_freq_id'])

        growth_freq = None
        if data.get('growth_freq_id'):
            growth_freq = Periodicity.objects.get(id=data['growth_freq_id'])

        # 2. Create the CustomerAgreement instance
        agreement = CustomerAgreement.objects.create(
            customer_id=data['customer_id'],
            route_id=data['route_id'],
            agreement_type=data.get('agreement_type', CustomerAgreement.TypesChoices.SHORT_TERM),
            doc_id=doc_id,
            agreed_benefit_id=data.get('agreed_benefit_id'),
            start_date=data['start_date'],
            end_date=data['end_date'],
            target_freq=target_freq,
            target_amount=data.get('target_amount') or Decimal('0.00'),
            penalty_freq=penalty_freq,
            penalty_amount=data.get('penalty_amount') or Decimal('0.00'),
            growth_freq=growth_freq,
            growth_value=data.get('growth_value') or Decimal('0.00'),
            related_doc=data.get('related_doc')
        )

        # 3. Create AgreementProductLines
        product_lines_data = data.get('product_lines', [])
        for pl_data in product_lines_data:
            AgreementProductLine.objects.create(
                customer_agreement=agreement,
                product_class_id=pl_data['product_class_id'],
                required_target=pl_data.get('target') or Decimal('0.00')
            )

        # 4. Generate evaluation periods
        cls._generate_evaluation_periods(agreement, product_lines_data)

        return agreement

    @classmethod
    def _generate_evaluation_periods(cls, agreement, product_lines_data):
        import datetime
        start_date = agreement.start_date
        if isinstance(start_date, str):
            start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
            
        end_date = agreement.end_date
        if isinstance(end_date, str):
            end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()


        # If there's no target frequency, we evaluate once at the end of the contract
        if not agreement.target_freq or not agreement.target_freq.months_duration:
            period = AgreementEvaluationPeriod.objects.create(
                customer_agreement=agreement,
                period_number=1,
                start_date=start_date,
                end_date=end_date,
                expected_global_target=agreement.target_amount,
                status=AgreementEvaluationPeriod.StatusChoices.PENDING
            )
            for pl_data in product_lines_data:
                target = pl_data.get('target') or Decimal('0.00')
                if target > 0:
                    AgreementPeriodLineTarget.objects.create(
                        evaluation_period=period,
                        product_class_id=pl_data['product_class_id'],
                        expected_line_target=target
                    )
            return

        # Iterative period generation based on target frequency
        months_step = agreement.target_freq.months_duration
        current_date = start_date
        period_number = 1

        current_target = Decimal(str(agreement.target_amount))
        
        # Track growth
        growth_months_step = agreement.growth_freq.months_duration if agreement.growth_freq else None
        growth_value = Decimal(str(agreement.growth_value)) if agreement.growth_value else Decimal('0.00')
        months_since_last_growth = 0

        while current_date < end_date:
            next_date = current_date + relativedelta(months=months_step) - relativedelta(days=1)
            
            # Ensure we don't exceed the end_date
            if next_date >= end_date:
                next_date = end_date
            
            # Create period
            period = AgreementEvaluationPeriod.objects.create(
                customer_agreement=agreement,
                period_number=period_number,
                start_date=current_date,
                end_date=next_date,
                expected_global_target=current_target,
                status=AgreementEvaluationPeriod.StatusChoices.PENDING
            )

            # Create line targets with proportional growth if necessary
            # Growth ratio compared to the initial target amount
            initial_target = Decimal(str(agreement.target_amount))
            growth_ratio = current_target / initial_target if initial_target > 0 else Decimal('1.0')

            for pl_data in product_lines_data:
                target = pl_data.get('target') or Decimal('0.00')
                if target > 0:
                    AgreementPeriodLineTarget.objects.create(
                        evaluation_period=period,
                        product_class_id=pl_data['product_class_id'],
                        expected_line_target=target * growth_ratio
                    )

            # Apply growth for the next iteration
            months_since_last_growth += months_step
            if growth_months_step and months_since_last_growth >= growth_months_step:
                # Assuming growth_value is a percentage (e.g. 10 for 10%)
                current_target = current_target * (Decimal('1') + (growth_value / Decimal('100')))
                months_since_last_growth = 0

            current_date = next_date + relativedelta(days=1)
            period_number += 1


    @classmethod
    def read_agreements(cls):
        return CustomerAgreement.objects.select_related(
            'customer', 'route', 'route__warehouse', 'agreed_benefit'
        ).prefetch_related(
            'evaluation_periods'
        ).order_by('-start_date')

