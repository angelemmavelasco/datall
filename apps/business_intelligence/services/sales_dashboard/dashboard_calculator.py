from decimal import Decimal
from collections import defaultdict

class SalesDashboardCalculator:
    def __init__(self, transactions, targets, date_start=None, date_end=None):
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
        self.date_start = self._parse_date(date_start)
        self.date_end = self._parse_date(date_end)

    def _parse_date(self, date_val):
        from datetime import datetime
        if isinstance(date_val, str) and date_val:
            try:
                return datetime.strptime(date_val, '%Y-%m-%d').date()
            except ValueError:
                return None
        return date_val

    def _prorate_target(self, t):
        target_amount = self._safe_decimal(t.get('target_amount', 0))
        if not self.date_start and not self.date_end:
            return target_amount

        from datetime import date
        import calendar

        period = t.get('period')
        if not period:
            return target_amount

        if isinstance(period, str):
            try:
                from datetime import datetime
                period = datetime.strptime(period, '%Y-%m-%d').date()
            except ValueError:
                return target_amount
        
        month_start = period
        _, last_day = calendar.monthrange(month_start.year, month_start.month)
        month_end = date(month_start.year, month_start.month, last_day)

        start = self.date_start if self.date_start else month_start
        end = self.date_end if self.date_end else month_end

        overlap_start = max(month_start, start)
        overlap_end = min(month_end, end)

        if overlap_start > overlap_end:
            return Decimal('0.00')

        overlap_days = (overlap_end - overlap_start).days + 1
        total_days = (month_end - month_start).days + 1

        return target_amount * Decimal(overlap_days) / Decimal(total_days)

    def _safe_decimal(self, val):
        return Decimal(str(val)) if val is not None else Decimal('0.00')

    def calculate_kpis(self):
        net_sale = Decimal('0.00')
        total_sale = Decimal('0.00')
        units = Decimal('0.00')
        profit = Decimal('0.00')
        customer_ids = set()

        for t in self.transactions:
            net_sale += self._safe_decimal(t.get('net_amount', 0))
            total_sale += self._safe_decimal(t.get('gross_amount', 0))
            units += self._safe_decimal(t.get('quantity', 0))
            profit += self._safe_decimal(t.get('profit', 0))
            if t.get('customer_id'):
                customer_ids.add(t.get('customer_id'))

        target = Decimal('0.00')
        for t in self.targets:
            target += self._prorate_target(t)

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
            'customers_with_purchases': len(customer_ids),
        }

    def calculate_timeline(self):
        daily_data = defaultdict(lambda: {'net_sale': Decimal('0.00'), 'units': Decimal('0.00')})
        
        if self.date_start and self.date_end:
            current_date = self.date_start.replace(day=1)
            while current_date <= self.date_end or (current_date.year == self.date_end.year and current_date.month == self.date_end.month):
                date_str = current_date.strftime('%Y-%m')
                daily_data[date_str] # Initialize
                if current_date.month == 12:
                    current_date = current_date.replace(year=current_date.year + 1, month=1)
                else:
                    current_date = current_date.replace(month=current_date.month + 1)
                    
        for t in self.transactions:
            if t.get('sale_date'):
                date_str = t['sale_date'].strftime('%Y-%m')
            else:
                date_str = 'N/A'
            if date_str != 'N/A':
                # Only add if we didn't filter it out, or if it's within the range. 
                # Since transactions are already filtered by date_start/date_end in views, we can just add it.
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
            wh_id = t.get('route__warehouse_id') or 'N/A'
            wh_data[wh_id]['sale'] += self._safe_decimal(t.get('net_amount', 0))
            
        for t in self.targets:
            wh_id = t.get('route__warehouse_id') or 'N/A'
            wh_data[wh_id]['target'] += self._prorate_target(t)
            
        categories = sorted(wh_data.keys())
        return {
            'categories': [str(c).upper() for c in categories],
            'sales': [float(wh_data[c]['sale']) for c in categories],
            'targets': [float(wh_data[c]['target']) for c in categories]
        }

    def calculate_product_class_chart(self):
        pc_sales = defaultdict(Decimal)
        for t in self.transactions:
            pc_id = t.get('product_class_id') or 'N/A'
            pc_sales[pc_id] += self._safe_decimal(t.get('net_amount', 0))
            
        sorted_items = sorted(pc_sales.items(), key=lambda x: x[1], reverse=True)
        return {
            'categories': [str(x[0]).upper() for x in sorted_items],
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
            route_data[r_id]['target'] += self._prorate_target(t)
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

