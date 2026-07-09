from django.db import models
from django.db.models import Q
from django.core.exceptions import ValidationError
from apps.core.models import SaleTransaction

class SaleTransactionCRUD:
    def __init__(self):
        pass
    
    def create(self, **kwargs):
        if 'net_amount' in kwargs and 'cost' in kwargs and 'profit' not in kwargs:
            kwargs['profit'] = kwargs['net_amount'] - kwargs['cost']
            
        transaction = SaleTransaction(**kwargs)
        transaction.full_clean()
        transaction.save()
        return transaction
    
    def read(self,allowed_routes, **kwargs):
        queryset = SaleTransaction.objects.filter(route__in=allowed_routes)
        
        if kwargs.get('doc_id'):
            queryset = queryset.filter(doc_id__iexact=kwargs['doc_id'])
            
        if kwargs.get('sale_date_start'):
            queryset = queryset.filter(sale_date__gte=kwargs['sale_date_start'])
        if kwargs.get('sale_date_end'):
            queryset = queryset.filter(sale_date__lte=kwargs['sale_date_end'])

        if kwargs.get('months'):
            months = [int(m) for m in kwargs['months'] if m.isdigit()]
            if months:
                queryset = queryset.filter(sale_date__month__in=months)
            
        if kwargs.get('products'):
            products = kwargs['products']
            if not isinstance(products, (list, tuple, set)):
                products = [products]
            q_products = Q()
            for p in products:
                q_products |= Q(product__id__iexact=p.strip())
            queryset = queryset.filter(q_products)

        if kwargs.get('customers'):
            customers = kwargs['customers']
            if not isinstance(customers, (list, tuple, set)):
                customers = [customers]
            q_customers = Q()
            for c in customers:
                q_customers |= Q(customer__id__iexact=c.strip())
            queryset = queryset.filter(q_customers)

        numeric_fields = ['cost', 'net_amount', 'gross_amount', 'profit', 'quantity']
        for field in numeric_fields:
            min_val = kwargs.get(f'{field}_min')
            max_val = kwargs.get(f'{field}_max')
            
            if min_val is not None:
                queryset = queryset.filter(**{f"{field}__gte": min_val})
            if max_val is not None:
                queryset = queryset.filter(**{f"{field}__lte": max_val})
                
        fk_fields = {
            'product_classes': 'product_class_id__in',
            'product_categories': 'product_class__product_category_id__in',
            'routes': 'route_id__in',
            'warehouses': 'warehouse_id__in', 
            'regions': 'route__warehouse__region_id__in',
            'route_warehouse_ids': 'route__warehouse_id__in',
            'customer_routes': 'customer__route_id__in',
            'customer_warehouses': 'customer__route__warehouse_id__in'
        }
        
        for param, lookup in fk_fields.items():
            value = kwargs.get(param)
            if value:
                if not isinstance(value, (list, tuple, set)):
                    value = [value]
                queryset = queryset.filter(**{lookup: value})
        return queryset.select_related('product', 'warehouse', 'route', 'product_class')
    
    def update(self, transaction_id, **kwargs):
        try:
            transaction = SaleTransaction.objects.get(pk=transaction_id)
        except SaleTransaction.DoesNotExist:
            return None
            
        for key, value in kwargs.items():
            setattr(transaction, key, value)
            
        if 'net_amount' in kwargs or 'cost' in kwargs:
            transaction.profit = transaction.net_amount - transaction.cost
            
        transaction.full_clean()
        transaction.save()
        return transaction
    
    def delete(self, transaction_id):
        try:
            transaction = SaleTransaction.objects.get(pk=transaction_id)
            transaction.delete()
            return True
        except SaleTransaction.DoesNotExist:
            return False