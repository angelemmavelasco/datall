from apps.core.models import (
    AccountsReceivable,
    Reference,
    Customer,
)
from apps.customers.services.accounts_receivable.accounts_receivable_crud import AccountsReceivableCrud

from django.db.models import F, Sum, Count, Case, When, Value, DecimalField
from collections import defaultdict
from decimal import Decimal


class Collections(AccountsReceivableCrud):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def read(self, **kwargs):
        kwargs.pop('date_start', None)
        kwargs.pop('issue_date_start', None)
        return super().read(**kwargs)

    def get_ar_by_customer(self, qs):
        return qs.values(
            'customer__id',
            'customer__name',
            'customer__route__id',
            'customer__route__name',
            'customer__route__warehouse_id'
        ).annotate(
            total_balance=Sum('total_balance'),
            current_balance=Sum('current_balance'),
            balance_15=Sum('balance_15'),
            balance_30=Sum('balance_30'),
            balance_60=Sum('balance_60'),
            past_due=Sum('past_due'),
            overdue_balance_sum=F('total_balance') - F('current_balance'),
            credit_usage=Case(
                When(customer__credit_limit__gt=0, then=(F('total_balance') * 100.0) / F('customer__credit_limit')),
                default=Value(0.0),
                output_field=DecimalField()
            ),
            credit_limit = F('customer__credit_limit') or Value(Decimal('0.00'), output_field=DecimalField())
        ).order_by('-total_balance')

    def get_ar_kpis(self, qs):
        kpis = defaultdict(dict)
        qs_agg = qs.aggregate(
            # aldo total
            total_balance=Sum('total_balance'),
            #al corrient
            current_balance=Sum('current_balance'),
            #vencido
            overdue_balance_sum=F('total_balance') - F('current_balance'),

            #antigüedad
            balance_15=Sum('balance_15'),
            balance_30=Sum('balance_30'),
            balance_60=Sum('balance_60'),
            past_due=Sum('past_due'),
            accs_receivable_count=Count('customer__id', distinct=True)
        )

        kpis['total_balance'] = qs_agg.get('total_balance') or Decimal('0.00')
        kpis['current_balance'] = qs_agg.get('current_balance') or Decimal('0.00')
        kpis['overdue_balance'] = qs_agg.get('overdue_balance_sum') or Decimal('0.00')
        kpis['balance_15'] = qs_agg.get('balance_15') or Decimal('0.00')
        kpis['balance_30'] = qs_agg.get('balance_30') or Decimal('0.00')
        kpis['balance_60'] = qs_agg.get('balance_60') or Decimal('0.00')
        kpis['past_due'] = qs_agg.get('past_due') or Decimal('0.00')
        kpis['accs_receivable_count'] = qs_agg.get('accs_receivable_count') or Decimal('0.00')
        
        kpis['credit_usage_by_ar'], kpis['credit_usage_by_ptf'], kpis['credit_ar'], kpis['credit_ptf'] = self.get_credit_usage(qs, kpis['total_balance'])

        return kpis

    def get_credit_usage(self, qs, total_balance):
        ar_customers_qs = qs.values('customer_id').distinct()
        ar_credit_limit = Customer.objects.filter(id__in=ar_customers_qs).aggregate(total_limit=Sum('credit_limit'))['total_limit'] or Decimal('0.00')
        
        ptf_credit_limit = Decimal('0.00')
        if self.allowed_customers is not None:
            ptf_credit_limit = self.allowed_customers.aggregate(total_limit=Sum('credit_limit'))['total_limit'] or Decimal('0.00')

        usage_ar = (total_balance / ar_credit_limit * 100) if ar_credit_limit > 0 else Decimal('0.00')
        usage_ptf = (total_balance / ptf_credit_limit * 100) if ptf_credit_limit > 0 else Decimal('0.00')
        
        return usage_ar, usage_ptf, ar_credit_limit, ptf_credit_limit

        