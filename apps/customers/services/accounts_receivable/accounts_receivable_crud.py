# class AccountsReceivable(models.Model):
#     customer = models.ForeignKey(
#         Customer,
#         on_delete=models.CASCADE,
#         related_name='accounts_receivable'
#     )

#     route = models.ForeignKey(
#         'Route',
#         on_delete=models.SET_NULL,
#         null=True,
#         blank=True,
#         related_name='accounts_receivables'
#     )

#     total_balance = models.DecimalField(max_digits=18, decimal_places=4, default=0, blank=True, null=True)
#     current_balance = models.DecimalField(max_digits=18, decimal_places=4, default=0, blank=True, null=True)
#     balance_15 = models.DecimalField(max_digits=18, decimal_places=4, default=0, blank=True, null=True)
#     balance_30 = models.DecimalField(max_digits=18, decimal_places=4, default=0, blank=True, null=True)
#     balance_60 = models.DecimalField(max_digits=18, decimal_places=4, default=0, blank=True, null=True)
#     past_due = models.DecimalField(max_digits=18, decimal_places=4, default=0, blank=True, null=True)

#     period = models.DateField()


from apps.core.models import (
    AccountsReceivable,
    Reference,
    Customer,
    Route
)
from django.db.models import QuerySet
from typing import List
from datetime import datetime, date


class AccountsReceivableCrud:
    def __init__(self, *, allowed_routes=None, allowed_customers=None, allowed_warehouses=None):
        self.allowed_routes = allowed_routes
        self.allowed_customers = allowed_customers
        self.allowed_warehouses = allowed_warehouses
    
    def read(self, **kwargs):
        period = date.today().replace(day=1)

        if kwargs.get('month'):
            period = period.replace(month=int(kwargs['month']))
        if kwargs.get('year'):
            period = period.replace(year=int(kwargs['year']))

        if kwargs.get('customers'):
            customer_list = kwargs['customers']
        else:
            customer_list = self.allowed_customers.values_list('id', flat=True) if self.allowed_customers else []

        
        return AccountsReceivable.objects.filter(
            period=period,
            customer_id__in=customer_list,
            customer__route__in=self.allowed_routes 
        )
            

            


        
        

                
        
obj = AccountsReceivableCrud(allowed_routes=['1'])
obj.read(year=2023, month=5)        

