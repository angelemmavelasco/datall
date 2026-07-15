import datetime
from django.db.models import Q, Sum
from apps.core.models import SaleTransaction, Customer, Product, Route, Warehouse
from apps.core.utils import get_allowed_routes_for_user, get_allowed_warehouses_for_user

class SalesAnalyticsService:
    ALLOWED_DIMENSIONS = {
        'sale_date', 
        'sale_date__year', 
        'sale_date__month',
        'customer_id', 
        'customer__name', 
        'product_id', 
        'product__name', 
        'route_id', 
        'route__name', 
        'warehouse_id', 
        'warehouse__name',
        'warehouse__region_id',
        'warehouse__region__name'
    }

    ALLOWED_METRICS = {
        'net_amount',
        'gross_amount',
        'profit',
        'quantity',
        'cost',
    }

    def __init__(self, user):
        self.user = user

    def get_aggregated_data(self, dimensions=None, metrics=None, start_date=None, end_date=None, filters=None):
        dimensions = dimensions or []
        metrics = metrics or ['net_amount']
        filters = filters or {}
        allowed_routes = get_allowed_routes_for_user(self.user).filter(is_active=True)
        queryset = SaleTransaction.objects.filter(route__in=allowed_routes)

        if start_date:
            queryset = queryset.filter(sale_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(sale_date__lte=end_date)

        for key, value in filters.items():
            if key in self.ALLOWED_DIMENSIONS:
                if isinstance(value, str) and not value.isdigit() and not 'id' in key:
                    queryset = queryset.filter(**{f"{key}__icontains": value})
                else:
                    queryset = queryset.filter(**{key: value})
        valid_dimensions = [d for d in dimensions if d in self.ALLOWED_DIMENSIONS]
        valid_metrics = [m for m in metrics if m in self.ALLOWED_METRICS]
        annotations = {f"total_{m}": Sum(m) for m in valid_metrics}
        if valid_dimensions:
            queryset = queryset.values(*valid_dimensions).annotate(**annotations).order_by(*valid_dimensions)
        else:
            queryset = queryset.aggregate(**annotations)
            return [queryset]
        return list(queryset)[:100]

    def search_catalog(self, entity_type, search_term):
        allowed_routes = get_allowed_routes_for_user(self.user).filter(is_active=True)
        if entity_type == 'route':
            return list(allowed_routes.filter(Q(id__icontains=search_term) | Q(name__icontains=search_term)).values('id', 'name')[:10])
        elif entity_type == 'customer':
            return list(Customer.objects.filter(route__in=allowed_routes).filter(Q(id__icontains=search_term) | Q(name__icontains=search_term)).values('id', 'name').distinct()[:10])
        elif entity_type == 'product':
            return list(Product.objects.filter(Q(id__icontains=search_term) | Q(name__icontains=search_term)).values('id', 'name')[:10])
        elif entity_type == 'warehouse':
            allowed_warehouses = get_allowed_warehouses_for_user(self.user)
            return list(allowed_warehouses.filter(Q(id__icontains=search_term) | Q(name__icontains=search_term)).values('id', 'name')[:10])
        elif entity_type == 'region':
            from apps.core.models import Region
            return list(Region.objects.filter(Q(id__icontains=search_term) | Q(name__icontains=search_term)).values('id', 'name')[:10])
        return []
