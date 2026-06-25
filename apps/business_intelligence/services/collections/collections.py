from apps.core.models import (
    AccountsReceivable,
    Reference,
    Customer,
)
from apps.customers.services.accounts_receivable.accounts_receivable_crud import AccountsReceivableCrud

from django.db.models import F, Sum
from collections import defaultdict


class Collections(AccountsReceivableCrud):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

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
            overdue_balance_sum=F('total_balance') - F('current_balance')
        )

    def get_ar_kpis(self, qs):
        kpis = defaultdict(dict)
        pass

        