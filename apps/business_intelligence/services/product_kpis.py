from dataclasses import dataclass, field
from django.db.models import QuerySet, Q, Sum, Count, Avg, F, ExpressionWrapper, DecimalField
from apps.core.models import SaleTransaction, Product, ProductCategory, ProductClass, Customer, Warehouse
from datetime import datetime, date
from django.db.models.functions import TruncMonth, TruncDay
from collections import defaultdict
import django.db.models

@dataclass
class ProductKpisService:
    sales_qs: QuerySet[SaleTransaction]

    def get_summary_stats(self):
        '''
        Calculate the main kpis which are used mainly for BANS.
        '''
        stats = self.sales_qs.aggregate(
            net_amount=Sum('net_amount'),
            gross_amount=Sum('gross_amount'),
            cost=Sum('cost'),
            profit=Sum('profit'),
            quantity=Sum('quantity'),
        )
        
        # Format the stats, handle None values
        for key in stats:
            stats[key] = float(stats[key]) if stats[key] is not None else 0.0

        if stats['quantity'] > 0:
            stats['avg_price'] = stats['net_amount'] / stats['quantity']
            stats['avg_cost'] = stats['cost'] / stats['quantity']
            stats['avg_profit'] = stats['profit'] / stats['quantity']
        else:
            stats['avg_price'] = 0.0
            stats['avg_cost'] = 0.0
            stats['avg_profit'] = 0.0
            
        return stats

    def get_timeline_data(self):
        '''
        Group data by date (month or day depending on the date range) and by product.
        '''
        if not self.sales_qs.exists():
            return {"dates": [], "products": {}, "grouped": {}}

        dates = self.sales_qs.aggregate(min_date=django.db.models.Min('sale_date'), max_date=django.db.models.Max('sale_date'))
        min_date = dates['min_date']
        max_date = dates['max_date']

        if not min_date or not max_date:
            return {"dates": [], "products": {}, "grouped": {}}

        # If date range duration is <= the number of days in the starting month, group by day, else month.
        import calendar
        delta = max_date - min_date
        days_in_month = calendar.monthrange(min_date.year, min_date.month)[1]
        is_daily = (delta.days + 1) <= days_in_month

        trunc_func = TruncDay('sale_date') if is_daily else TruncMonth('sale_date')

        grouped_qs = self.sales_qs.annotate(
            period=trunc_func
        ).values('period', 'product__id', 'product__name').annotate(
            net_amount=Sum('net_amount'),
            cost=Sum('cost'),
            profit=Sum('profit'),
            quantity=Sum('quantity'),
        ).order_by('period')

        # Structure for Echarts
        # We need a unified list of periods (dates)
        unique_periods = sorted(list(set(item['period'] for item in grouped_qs)))
        period_strings = [p.strftime('%Y-%m-%d') if is_daily else p.strftime('%Y-%m') for p in unique_periods]

        # Product Comparative Data
        # product_id -> { name, data_by_date: { period: {net, cost, profit, qty} } }
        products_data = defaultdict(lambda: {"name": "", "data": {}})
        
        # Grouped Data (overall per period)
        grouped_data = defaultdict(lambda: {"net_amount": 0, "cost": 0, "profit": 0, "quantity": 0})

        for row in grouped_qs:
            p_str = row['period'].strftime('%Y-%m-%d') if is_daily else row['period'].strftime('%Y-%m')
            prod_id = row['product__id'] or 'Unknown'
            prod_name = (row['product__name'] or 'Unknown').title()
            
            qty = float(row['quantity'] or 0)
            net = float(row['net_amount'] or 0)
            cost = float(row['cost'] or 0)
            profit = float(row['profit'] or 0)

            if prod_id not in products_data:
                products_data[prod_id]['name'] = f"{prod_id.upper()} {prod_name}"

            products_data[prod_id]['data'][p_str] = {
                'net': net,
                'cost': cost,
                'profit': profit,
                'quantity': qty
            }

            grouped_data[p_str]['net_amount'] += net
            grouped_data[p_str]['cost'] += cost
            grouped_data[p_str]['profit'] += profit
            grouped_data[p_str]['quantity'] += qty

        # Format into final arrays matching the unique_periods order
        # For each product
        formatted_products = []
        for pid, pdata in products_data.items():
            series = {
                "name": pdata['name'],
                "avg_price": [],
                "avg_cost": [],
                "avg_profit": [],
                "quantity": []
            }
            for p_str in period_strings:
                day_data = pdata['data'].get(p_str, {'net': 0, 'cost': 0, 'profit': 0, 'quantity': 0})
                qty = day_data['quantity']
                series['quantity'].append(qty)
                series['avg_price'].append(day_data['net']/qty if qty else 0)
                series['avg_cost'].append(day_data['cost']/qty if qty else 0)
                series['avg_profit'].append(day_data['profit']/qty if qty else 0)
            formatted_products.append(series)

        # For grouped data
        grouped_series = {
            "avg_price": [],
            "avg_cost": [],
            "avg_profit": [],
            "quantity": []
        }
        for p_str in period_strings:
            day_data = grouped_data[p_str]
            qty = day_data['quantity']
            grouped_series['quantity'].append(qty)
            grouped_series['avg_price'].append(day_data['net_amount']/qty if qty else 0)
            grouped_series['avg_cost'].append(day_data['cost']/qty if qty else 0)
            grouped_series['avg_profit'].append(day_data['profit']/qty if qty else 0)

        return {
            "periods": period_strings,
            "comparative": formatted_products,
            "grouped": grouped_series
        }

    def get_category_distribution(self):
        qs = self.sales_qs.values(
            'product_class__product_category__name'
        ).annotate(
            net=Sum('net_amount'),
            cost=Sum('cost'),
            profit=Sum('profit'),
            qty=Sum('quantity')
        ).order_by('-net')

        total_net = sum(float(item['net'] or 0) for item in qs)
        
        data = []
        for item in qs:
            net = float(item['net'] or 0)
            cat_name = item['product_class__product_category__name']
            name = cat_name.title() if cat_name else "Sin Categoría"
            percent = (net / total_net * 100) if total_net else 0
            
            data.append({
                "name": name,
                "value": net,
                "percent": round(percent, 2),
                "cost": float(item['cost'] or 0),
                "profit": float(item['profit'] or 0),
                "quantity": float(item['qty'] or 0)
            })
        return data

    def get_class_distribution(self):
        qs = self.sales_qs.values(
            'product_class__name'
        ).annotate(
            net=Sum('net_amount'),
            cost=Sum('cost'),
            profit=Sum('profit'),
            qty=Sum('quantity')
        ).order_by('-net')

        total_net = sum(float(item['net'] or 0) for item in qs)
        
        categories = []
        sales = []
        
        for item in qs:
            net = float(item['net'] or 0)
            class_name = item['product_class__name']
            name = class_name.title() if class_name else "Sin Clase"
            percent = (net / total_net * 100) if total_net else 0
            
            categories.append(name)
            sales.append({
                "value": net,
                "percent": round(percent, 2),
                "cost": float(item['cost'] or 0),
                "profit": float(item['profit'] or 0),
                "quantity": float(item['qty'] or 0)
            })
            
        return {
            "categories": categories,
            "sales": sales
        }

    def get_breakdown_tables(self):
        # By Route
        routes_qs = self.sales_qs.values(
            'route__id', 'route__name'
        ).annotate(
            net=Sum('net_amount'),
            cost=Sum('cost'),
            profit=Sum('profit'),
            qty=Sum('quantity')
        ).order_by('-net')

        routes_data = []
        for item in routes_qs:
            rid = item['route__id'] or "N/A"
            rname = item['route__name'] or ""
            qty = float(item['qty'] or 0)
            net = float(item['net'] or 0)
            cost = float(item['cost'] or 0)
            profit = float(item['profit'] or 0)
            
            routes_data.append({
                "id": rid,
                "name": rname.title(),
                "net": net,
                "avg_price": net / qty if qty else 0,
                "cost": cost,
                "avg_cost": cost / qty if qty else 0,
                "profit": profit,
                "avg_profit": profit / qty if qty else 0,
                "quantity": qty
            })

        # By Customer
        customers_qs = self.sales_qs.values(
            'customer__id', 'customer__name'
        ).annotate(
            net=Sum('net_amount'),
            cost=Sum('cost'),
            profit=Sum('profit'),
            qty=Sum('quantity')
        ).order_by('-net')

        customers_data = []
        for item in customers_qs:
            cid = item['customer__id'] or "N/A"
            cname = item['customer__name'] or ""
            qty = float(item['qty'] or 0)
            net = float(item['net'] or 0)
            cost = float(item['cost'] or 0)
            profit = float(item['profit'] or 0)
            
            customers_data.append({
                "id": cid,
                "name": cname.title(),
                "net": net,
                "avg_price": net / qty if qty else 0,
                "cost": cost,
                "avg_cost": cost / qty if qty else 0,
                "profit": profit,
                "avg_profit": profit / qty if qty else 0,
                "quantity": qty
            })

        return routes_data, customers_data