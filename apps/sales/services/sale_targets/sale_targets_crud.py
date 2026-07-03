from django.db import models
from django.core.exceptions import ValidationError
from datetime import datetime, date
from apps.core.models import SaleTarget
from decimal import Decimal
from django.db.models import Sum, Count, Q
from apps.sales.services.sale_transactions.sale_transactions_crud import SaleTransactionCRUD

class SaleTargetCRUD:
    def __init__(self):
        pass

    def _normalize_period(self, period_val):
        if isinstance(period_val, str):
            try:
                dt = datetime.strptime(period_val, '%Y-%m-%d').date()
                return dt.replace(day=1)
            except ValueError:
                return period_val
        elif hasattr(period_val, 'replace'):
            return period_val.replace(day=1)
        return period_val
    
    def create(self, **kwargs):
        if 'period' in kwargs:
            kwargs['period'] = self._normalize_period(kwargs['period'])
            
        target = SaleTarget(**kwargs)
        target.full_clean()
        target.save()
        return target
    
    def read(self, allowed_routes, **kwargs):
        queryset = SaleTarget.objects.filter(route__in=allowed_routes)
        
        if kwargs.get('period_start'):
            start_date = self._normalize_period(kwargs['period_start'])
            queryset = queryset.filter(period__gte=start_date)
        if kwargs.get('period_end'):
            end_date = self._normalize_period(kwargs['period_end'])
            queryset = queryset.filter(period__lte=end_date)
            
        if kwargs.get('period'):
            exact_period = self._normalize_period(kwargs['period'])
            queryset = queryset.filter(period=exact_period)
            
        if kwargs.get('target_amount_min') is not None:
            queryset = queryset.filter(target_amount__gte=kwargs['target_amount_min'])
        if kwargs.get('target_amount_max') is not None:
            queryset = queryset.filter(target_amount__lte=kwargs['target_amount_max'])
                
        fk_fields = {
            'product_classes': 'product_class_id__in',
            'product_categories': 'product_class__product_category_id__in',
            'warehouses': 'warehouse_id__in',
            'regions': 'route__warehouse__region_id__in',
            'routes': 'route_id__in',
            'route_warehouse_ids': 'route__warehouse_id__in'
        }
        
        for param, lookup in fk_fields.items():
            value = kwargs.get(param)
            if value:
                if not isinstance(value, (list, tuple, set)):
                    value = [value]
                queryset = queryset.filter(**{lookup: value})
        return queryset.select_related('route', 'warehouse', 'product_class')
        
    def get_kpis(self, allowed_routes, **kwargs):
        targets_qs = self.read(allowed_routes, **kwargs)
        
        target_aggs = targets_qs.aggregate(
            total_target=Sum('target_amount'),
            unique_pc=Count('product_class_id', filter=Q(target_amount__gt=0), distinct=True)
        )
        
        sale_target = Decimal(str(target_aggs.get('total_target') or '0.00'))
        pc_with_targets = target_aggs.get('unique_pc') or 0
        
        avg_by_product_class = Decimal('0.00')
        if pc_with_targets > 0:
            avg_by_product_class = sale_target / Decimal(pc_with_targets)
            
        trans_kwargs = kwargs.copy()
        if 'period_start' in trans_kwargs:
            trans_kwargs['sale_date_start'] = trans_kwargs.pop('period_start')
        if 'period_end' in trans_kwargs:
            trans_kwargs['sale_date_end'] = trans_kwargs.pop('period_end')
            
        trans_crud = SaleTransactionCRUD()
        trans_qs = trans_crud.read(allowed_routes, **trans_kwargs)
        
        trans_aggs = trans_qs.aggregate(total_net=Sum('net_amount'))
        net_sale = Decimal(str(trans_aggs.get('total_net') or '0.00'))
        
        difference = net_sale - sale_target
        scope = Decimal('0.00')
        if sale_target > 0:
            scope = (net_sale / sale_target) * Decimal('100.00')
            
        return {
            'sale_target': sale_target,
            'pc_with_targets': pc_with_targets,
            'avg_by_product_class': avg_by_product_class,
            'difference': difference,
            'scope': scope
        }
    
    def update(self, target_id, **kwargs):
        try:
            target = SaleTarget.objects.get(pk=target_id)
        except SaleTarget.DoesNotExist:
            return None
            
        if 'period' in kwargs:
            kwargs['period'] = self._normalize_period(kwargs['period'])
            
        for key, value in kwargs.items():
            setattr(target, key, value)
            
        target.full_clean()
        target.save()
        return target
    
    def delete(self, target_id):
        try:
            target = SaleTarget.objects.get(pk=target_id)
            target.delete()
            return True
        except SaleTarget.DoesNotExist:
            return False