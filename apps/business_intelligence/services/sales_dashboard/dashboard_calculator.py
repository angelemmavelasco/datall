from decimal import Decimal
from collections import defaultdict

class SalesDashboardCalculator:
    def __init__(self, transactions, targets):
        """
        Receives two lists of dictionaries (from .values() execution) to avoid N+1 queries.
        transactions: list of dicts with sale_date, net_amount, gross_amount, quantity, profit, 
                      route_id, route__name, warehouse_id, warehouse__name, 
                      product_class_id, product_class__name, product_class__product_category__name,
                      product_id, product__name, customer_id, customer__name
        targets: list of dicts with period, target_amount, route_id, route__name, warehouse_id, warehouse__name, product_class_id
        """
        self.transactions = transactions
        self.targets = targets

    def _safe_decimal(self, val):
        return Decimal(str(val)) if val is not None else Decimal('0.00')

    def calculate_kpis(self):
        net_sale = Decimal('0.00')
        total_sale = Decimal('0.00')
        units = Decimal('0.00')
        profit = Decimal('0.00')

        for t in self.transactions:
            net_sale += self._safe_decimal(t.get('net_amount', 0))
            total_sale += self._safe_decimal(t.get('gross_amount', 0))
            units += self._safe_decimal(t.get('quantity', 0))
            profit += self._safe_decimal(t.get('profit', 0))

        target = Decimal('0.00')
        for t in self.targets:
            target += self._safe_decimal(t.get('target_amount', 0))

        margin = (profit / net_sale * 100) if net_sale > 0 else Decimal('0.00')
        scope = (net_sale / target * 100) if target > 0 else Decimal('0.00')
        difference = net_sale - target

        return {
            'net_sale': net_sale,
            'target': target,
            'scope': scope,
            'difference': difference,
            'total_sale': total_sale,
            'units': units,
            'profit': profit,
            'margin': margin,
        }

    def calculate_timeline(self):
        daily_data = defaultdict(lambda: {'net_sale': Decimal('0.00'), 'units': Decimal('0.00')})
        
        for t in self.transactions:
            date_str = str(t.get('sale_date')) if t.get('sale_date') else 'N/A'
            if date_str != 'N/A':
                daily_data[date_str]['net_sale'] += self._safe_decimal(t.get('net_amount', 0))
                daily_data[date_str]['units'] += self._safe_decimal(t.get('quantity', 0))
            
        sorted_dates = sorted(daily_data.keys())
        
        return {
            'categories': sorted_dates,
            'sales': [float(daily_data[d]['net_sale']) for d in sorted_dates],
            'units': [float(daily_data[d]['units']) for d in sorted_dates]
        }

    def calculate_warehouse_chart(self):
        wh_data = defaultdict(lambda: {'sale': Decimal('0.00'), 'target': Decimal('0.00')})
        
        for t in self.transactions:
            wh_name = t.get('warehouse__name') or 'N/A'
            wh_data[wh_name]['sale'] += self._safe_decimal(t.get('net_amount', 0))
            
        for t in self.targets:
            wh_name = t.get('warehouse__name') or 'N/A'
            wh_data[wh_name]['target'] += self._safe_decimal(t.get('target_amount', 0))
            
        categories = sorted(wh_data.keys())
        return {
            'categories': [str(c).title() for c in categories],
            'sales': [float(wh_data[c]['sale']) for c in categories],
            'targets': [float(wh_data[c]['target']) for c in categories]
        }

    def calculate_product_class_chart(self):
        pc_sales = defaultdict(Decimal)
        for t in self.transactions:
            pc_name = t.get('product_class__name') or 'N/A'
            pc_sales[pc_name] += self._safe_decimal(t.get('net_amount', 0))
            
        sorted_items = sorted(pc_sales.items(), key=lambda x: x[1], reverse=True)
        return {
            'categories': [str(x[0]).title() for x in sorted_items],
            'sales': [float(x[1]) for x in sorted_items]
        }

    def calculate_product_category_chart(self):
        cat_sales = defaultdict(Decimal)
        for t in self.transactions:
            cat_name = t.get('product_class__product_category__name') or 'Sin Categoria'
            cat_sales[cat_name] += self._safe_decimal(t.get('net_amount', 0))
            
        sorted_items = sorted(cat_sales.items(), key=lambda x: x[1], reverse=True)
        return [
            {'name': str(x[0]).title(), 'value': float(x[1])}
            for x in sorted_items
        ]

    def calculate_route_table(self):
        route_data = defaultdict(lambda: {
            'name': '',
            'sale': Decimal('0.00'),
            'target': Decimal('0.00'),
            'profit': Decimal('0.00')
        })
        
        for t in self.transactions:
            r_id = t.get('route_id') or 'N/A'
            route_data[r_id]['name'] = t.get('route__name') or ''
            route_data[r_id]['sale'] += self._safe_decimal(t.get('net_amount', 0))
            route_data[r_id]['profit'] += self._safe_decimal(t.get('profit', 0))
            
        for t in self.targets:
            r_id = t.get('route_id') or 'N/A'
            route_data[r_id]['target'] += self._safe_decimal(t.get('target_amount', 0))
            if 'route__name' in t and not route_data[r_id]['name']:
                route_data[r_id]['name'] = t.get('route__name') or ''
            
        table = []
        for r_id, data in route_data.items():
            diff = data['sale'] - data['target']
            scope = (data['sale'] / data['target'] * 100) if data['target'] > 0 else Decimal('0.00')
            margin = (data['profit'] / data['sale'] * 100) if data['sale'] > 0 else Decimal('0.00')
            table.append({
                'id': r_id,
                'name': data['name'],
                'total_net_sale': round(float(data['sale']), 2),
                'total_target': round(float(data['target']), 2),
                'total_difference': round(float(diff), 2),
                'total_scope': round(float(scope), 2),
                'total_margin': round(float(margin), 2)
            })
            
        return sorted(table, key=lambda x: x['total_net_sale'], reverse=True)

    def calculate_top_products(self, limit=50):
        prod_data = defaultdict(lambda: {
            'name': '',
            'units': Decimal('0.00'),
            'net_sale': Decimal('0.00'),
            'gross_sale': Decimal('0.00'),
            'profit': Decimal('0.00')
        })
        
        for t in self.transactions:
            p_id = t.get('product_id') or 'N/A'
            prod_data[p_id]['name'] = t.get('product__name') or ''
            prod_data[p_id]['units'] += self._safe_decimal(t.get('quantity', 0))
            prod_data[p_id]['net_sale'] += self._safe_decimal(t.get('net_amount', 0))
            prod_data[p_id]['gross_sale'] += self._safe_decimal(t.get('gross_amount', 0))
            prod_data[p_id]['profit'] += self._safe_decimal(t.get('profit', 0))
            
        table = []
        for p_id, data in prod_data.items():
            margin = (data['profit'] / data['net_sale'] * 100) if data['net_sale'] > 0 else Decimal('0.00')
            table.append({
                'id': p_id,
                'name': data['name'],
                'total_units': round(float(data['units']), 2),
                'total_net_sale': round(float(data['net_sale']), 2),
                'total_gross_sale': round(float(data['gross_sale']), 2),
                'total_margin': round(float(margin), 2)
            })
            
        table = sorted(table, key=lambda x: x['total_net_sale'], reverse=True)
        return table[:limit]

    def calculate_top_customers(self, limit=50):
        cust_data = defaultdict(lambda: {
            'name': '',
            'net_sale': Decimal('0.00'),
            'gross_sale': Decimal('0.00'),
            'units': Decimal('0.00'),
            'profit': Decimal('0.00')
        })
        
        for t in self.transactions:
            c_id = t.get('customer_id') or 'N/A'
            cust_data[c_id]['name'] = t.get('customer__name') or ''
            cust_data[c_id]['net_sale'] += self._safe_decimal(t.get('net_amount', 0))
            cust_data[c_id]['gross_sale'] += self._safe_decimal(t.get('gross_amount', 0))
            cust_data[c_id]['units'] += self._safe_decimal(t.get('quantity', 0))
            cust_data[c_id]['profit'] += self._safe_decimal(t.get('profit', 0))
            
        table = []
        for c_id, data in cust_data.items():
            margin = (data['profit'] / data['net_sale'] * 100) if data['net_sale'] > 0 else Decimal('0.00')
            table.append({
                'id': c_id,
                'name': data['name'],
                'total_net_sale': round(float(data['net_sale']), 2),
                'total_gross_sale': round(float(data['gross_sale']), 2),
                'total_units': round(float(data['units']), 2),
                'total_margin': round(float(margin), 2)
            })
            
        table = sorted(table, key=lambda x: x['total_net_sale'], reverse=True)
        return table[:limit]

