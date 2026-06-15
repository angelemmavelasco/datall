from django.db.models import Count, Sum

class UniqueCustomersService:
    def __init__(self, queryset):
        self.queryset = queryset

    def get_pivot_data(self):
        data = self.queryset.values(
            'route__warehouse__id',
            'route__warehouse__name',
            'product_class__id',
            'product_class__name'
        ).annotate(
            unique_customers_count=Count('customer_id', distinct=True),
            total_net_amount=Sum('net_amount'),
            total_quantity=Sum('quantity')
        )
        
        product_classes_dict = {}
        warehouses_dict = {}
        
        for row in data:
            w_id = row['route__warehouse__id']
            w_name = row['route__warehouse__name']
            p_id = row['product_class__id']
            p_name = row['product_class__name']
            
            if not w_id:
                w_id = 'N/A'
                w_name = 'Sin Gerencia'
                
            if not p_id:
                p_id = 'N/A'
                p_name = 'Sin Clase'
            
            if p_id not in product_classes_dict:
                product_classes_dict[p_id] = {'id': p_id, 'name': p_name}
                
            if w_id not in warehouses_dict:
                warehouses_dict[w_id] = {
                    'id': w_id, 
                    'name': w_name, 
                    'classes': {}
                }
                
            warehouses_dict[w_id]['classes'][p_id] = {
                'unique_customers_count': row['unique_customers_count'],
                'total_net_amount': float(row['total_net_amount'] or 0),
                'total_quantity': float(row['total_quantity'] or 0)
            }
            
        sorted_classes = sorted(product_classes_dict.values(), key=lambda x: x['name'] or '')
        sorted_warehouses = sorted(warehouses_dict.values(), key=lambda x: x['name'] or '')
        
        for w in sorted_warehouses:
            aligned_classes = []
            for pc in sorted_classes:
                pc_id = pc['id']
                if pc_id in w['classes']:
                    aligned_classes.append(w['classes'][pc_id])
                else:
                    aligned_classes.append({
                        'unique_customers_count': 0,
                        'total_net_amount': 0,
                        'total_quantity': 0
                    })
            w['aligned_classes'] = aligned_classes
            
        return sorted_warehouses, sorted_classes