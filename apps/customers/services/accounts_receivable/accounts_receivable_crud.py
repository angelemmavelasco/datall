from apps.core.models import (
    AccountsReceivable,
    Reference,
    Customer,
    Route
)
from django.db.models import QuerySet, Q
from typing import List
from datetime import datetime, date


class AccountsReceivableCrud:
    def __init__(self, *, allowed_routes=None, allowed_customers=None, allowed_warehouses=None):
        self.allowed_routes = allowed_routes
        self.allowed_customers = allowed_customers
        self.allowed_warehouses = allowed_warehouses
    
    def read(self, **kwargs):
        qs = AccountsReceivable.objects.select_related('customer', 'route', 'customer__route', 'customer__route__warehouse')

        #if date start/end exists, the reports will asume issue date
        date_start = kwargs.get('date_start')
        date_end = kwargs.get('date_end')
        
        issue_date_start = kwargs.get('issue_date_start', date_start)
        issue_date_end = kwargs.get('issue_date_end', date_end)
        due_date_start = kwargs.get('due_date_start')
        due_date_end = kwargs.get('due_date_end')
        q_search = kwargs.get('q')

        if q_search:
            qs = qs.filter(Q(doc_id__icontains=q_search) | Q(description__icontains=q_search))

        # iisue date always includes null values because that kind of discounts alwya affects collections
        if issue_date_start and issue_date_end:
            qs = qs.filter(Q(issue_date__range=(issue_date_start, issue_date_end)) | Q(issue_date__isnull=True))
        elif issue_date_start:
            qs = qs.filter(Q(issue_date__gte=issue_date_start) | Q(issue_date__isnull=True))
        elif issue_date_end:
            qs = qs.filter(Q(issue_date__lte=issue_date_end) | Q(issue_date__isnull=True))

        #duedate filters
        if due_date_start and due_date_end:
            qs = qs.filter(Q(due_date__range=(due_date_start, due_date_end)) | Q(due_date__isnull=True))
        elif due_date_start:
            qs = qs.filter(Q(due_date__gte=due_date_start) | Q(due_date__isnull=True))
        elif due_date_end:
            qs = qs.filter(Q(due_date__lte=due_date_end) | Q(due_date__isnull=True))

        if kwargs.get('customers'):
            customer_list = kwargs['customers']
        else:
            customer_list = self.allowed_customers.values_list('id', flat=True) if self.allowed_customers else []

        qs = qs.filter(
            customer_id__in=customer_list,
            customer__route__in=self.allowed_routes 
        )
        return qs
            

            


        
        

