from decimal import Decimal
from collections import defaultdict
import datetime
from apps.sales.services.sale_transactions.sale_transactions_crud import SaleTransactionCRUD
from apps.sales.services.sale_targets.sale_targets_crud import SaleTargetCRUD
from apps.core.models import Customer, AccountsReceivable
import calendar
from django.db.models import OuterRef, Subquery

class RoutesKpisService:
    def __init__(self, routes_qs, date_start=None, date_end=None):
        self.routes_qs = routes_qs
        self.date_start = self._parse_date(date_start)
        self.date_end = self._parse_date(date_end)
        self.routes_data = {}
        self.global_charts = {}
        
        self._initialize_routes()
        self._load_and_process_data()

    def _parse_date(self, date_val):
        if isinstance(date_val, str) and date_val:
            try:
                return datetime.datetime.strptime(date_val, '%Y-%m-%d').date()
            except ValueError:
                return None
        return date_val

    def _safe_decimal(self, val):
        return Decimal(str(val)) if val is not None else Decimal('0.00')

    def _prorate_target(self, t):
        target_amount = self._safe_decimal(t.get('target_amount', 0))
        if not self.date_start and not self.date_end:
            return target_amount

        period = t.get('period')
        if not period:
            return target_amount

        if isinstance(period, str):
            try:
                period = datetime.datetime.strptime(period, '%Y-%m-%d').date()
            except ValueError:
                return target_amount
        
        month_start = period
        _, last_day = calendar.monthrange(month_start.year, month_start.month)
        month_end = datetime.date(month_start.year, month_start.month, last_day)

        start = self.date_start if self.date_start else month_start
        end = self.date_end if self.date_end else month_end

        overlap_start = max(month_start, start)
        overlap_end = min(month_end, end)

        if overlap_start > overlap_end:
            return Decimal('0.00')

        overlap_days = (overlap_end - overlap_start).days + 1
        total_days = (month_end - month_start).days + 1

        return target_amount * Decimal(overlap_days) / Decimal(total_days)

    def _initialize_routes(self):
        for route in self.routes_qs:
            r_id = route.id
            self.routes_data[r_id] = {
                'id': r_id,
                'name': route.name,
                'net_sale': Decimal('0.00'),
                'sale_target': Decimal('0.00'),
                'scope_diff': Decimal('0.00'),
                'scope': Decimal('0.00'),
                'clients': 0,
                'new_clients': 0,
                'clients_with_purchases': 0,
                'coverage_percentage': Decimal('0.00'),
                'product_class_performance': {
                    cls: {'net_sales': Decimal('0.00'), 'target': Decimal('0.00'), 'difference': Decimal('0.00'), 'scope': Decimal('0.00')}
                    for cls in ['dmd', 'nat', 'care', 'cv', 'tow', 'msd', 'vtq', 'zts', 'ntrf', 'otr', 'total']
                },
                'collections': {
                    'total_balance': Decimal('0.00'),
                    'current_balance': Decimal('0.00'),
                    'overdue_balance': Decimal('0.00'),
                    'overdue_count': 0,
                    'total_credit': Decimal('0.00'),
                    'credit_usage': Decimal('0.00'),
                    'days_1_15': Decimal('0.00'),
                    'days_16_30': Decimal('0.00'),
                    'days_31_60': Decimal('0.00'),
                    'days_60_over': Decimal('0.00'),
                }
            }

    def _load_and_process_data(self):
        filters = {}
        if self.date_start: filters['sale_date_start'] = self.date_start.strftime('%Y-%m-%d')
        if self.date_end: filters['sale_date_end'] = self.date_end.strftime('%Y-%m-%d')

        target_filters = {}
        if self.date_start: target_filters['period_start'] = self.date_start.strftime('%Y-%m-%d')
        if self.date_end: target_filters['period_end'] = self.date_end.strftime('%Y-%m-%d')

        trans_crud = SaleTransactionCRUD()
        transactions_qs = trans_crud.read(self.routes_qs, **filters)
        transactions = list(transactions_qs.values(
            'sale_date', 'net_amount', 'route_id', 'product_class_id', 'customer_id', 'customer__customer_type__name'
        ))

        targets_crud = SaleTargetCRUD()
        targets_qs = targets_crud.read(self.routes_qs, **target_filters)
        targets = list(targets_qs.values(
            'period', 'target_amount', 'route_id', 'product_class_id'
        ))

        # Process Sales
        customers_with_purchases = defaultdict(set)
        customer_types_sales = defaultdict(Decimal)

        for t in transactions:
            r_id = t.get('route_id')
            if not r_id or r_id not in self.routes_data:
                continue

            net = self._safe_decimal(t.get('net_amount', 0))
            self.routes_data[r_id]['net_sale'] += net
            
            p_class = str(t.get('product_class_id') or 'otr').lower()
            if p_class not in self.routes_data[r_id]['product_class_performance']:
                p_class = 'otr'
            
            self.routes_data[r_id]['product_class_performance'][p_class]['net_sales'] += net
            self.routes_data[r_id]['product_class_performance']['total']['net_sales'] += net

            customers_with_purchases[r_id].add(t.get('customer_id'))

            # Chart data: customer categories
            c_type = t.get('customer__customer_type__name') or 'Desconocido'
            customer_types_sales[c_type] += net

        for r_id, cust_set in customers_with_purchases.items():
            self.routes_data[r_id]['clients_with_purchases'] = len(cust_set)

        # Process Targets
        for t in targets:
            r_id = t.get('route_id')
            if not r_id or r_id not in self.routes_data:
                continue

            target_amt = self._prorate_target(t)
            self.routes_data[r_id]['sale_target'] += target_amt

            p_class = str(t.get('product_class_id') or 'otr').lower()
            if p_class not in self.routes_data[r_id]['product_class_performance']:
                p_class = 'otr'

            self.routes_data[r_id]['product_class_performance'][p_class]['target'] += target_amt
            self.routes_data[r_id]['product_class_performance']['total']['target'] += target_amt

        # Process Customers for limit credit
        route_ids = [r.id for r in self.routes_qs]
        customers = Customer.objects.filter(route_id__in=route_ids).values('route_id', 'credit_limit', 'id', 'registration_date')
        
        for c in customers:
            r_id = c['route_id']
            if r_id in self.routes_data:
                self.routes_data[r_id]['collections']['total_credit'] += self._safe_decimal(c.get('credit_limit'))
                self.routes_data[r_id]['clients'] += 1
                
                # new clients logic
                reg_date = c.get('registration_date')
                if reg_date and self.date_start and self.date_end:
                    if self.date_start <= reg_date <= self.date_end:
                        self.routes_data[r_id]['new_clients'] += 1

        # Process Accounts Receivable
        ar_filters = {'customer__route_id__in': route_ids}
        # Assuming we fetch the most recent AR period for each customer, or within date range? 
        # By default, AR is usually a snapshot. If period_end is provided, we filter up to date_end.
        if self.date_end:
            ar_filters['period__lte'] = self.date_end
        elif self.date_start:
            ar_filters['period__gte'] = self.date_start

        latest_ar_id = AccountsReceivable.objects.filter(
            customer_id=OuterRef('customer_id'),
            **ar_filters
        ).order_by('-period', '-id').values('id')[:1]

        # 2. Consulta principal: Filtramos para quedarnos únicamente con esos IDs más recientes
        ars = AccountsReceivable.objects.filter(
            **ar_filters,
            id=Subquery(latest_ar_id)
        ).values(
            'customer__route_id', 'total_balance', 'current_balance', 
            'balance_15', 'balance_30', 'balance_60', 'past_due'
        )
        
        for ar in ars:
            r_id = ar['customer__route_id']
            if r_id in self.routes_data:
                total_bal = self._safe_decimal(ar.get('total_balance'))
                
                self.routes_data[r_id]['collections']['total_balance'] += total_bal
                self.routes_data[r_id]['collections']['current_balance'] += self._safe_decimal(ar.get('current_balance'))
                self.routes_data[r_id]['collections']['days_1_15'] += self._safe_decimal(ar.get('balance_15'))
                self.routes_data[r_id]['collections']['days_16_30'] += self._safe_decimal(ar.get('balance_30'))
                self.routes_data[r_id]['collections']['days_31_60'] += self._safe_decimal(ar.get('balance_60'))
                self.routes_data[r_id]['collections']['days_60_over'] += self._safe_decimal(ar.get('past_due'))
                
                overdue = self._safe_decimal(ar.get('balance_15')) + self._safe_decimal(ar.get('balance_30')) + self._safe_decimal(ar.get('balance_60')) + self._safe_decimal(ar.get('past_due'))
                self.routes_data[r_id]['collections']['overdue_balance'] += overdue

                if total_bal > 0:
                    self.routes_data[r_id]['collections']['overdue_count'] += 1

        # Post-Process Calculations per Route
        for r_id, data in self.routes_data.items():
            net = data['net_sale']
            tgt = data['sale_target']
            data['scope_diff'] = net - tgt
            data['scope'] = (net / tgt * 100) if tgt > 0 else Decimal('0.00')

            tc = data['collections']['total_credit']
            tb = data['collections']['total_balance']
            data['collections']['credit_usage'] = (tb / tc * 100) if tc > 0 else Decimal('0.00')
            
            clients = data['clients']
            purchased = data['clients_with_purchases']
            data['coverage_percentage'] = (Decimal(purchased) / Decimal(clients) * 100) if clients > 0 else Decimal('0.00')

            for p_class, p_data in data['product_class_performance'].items():
                p_net = p_data['net_sales']
                p_tgt = p_data['target']
                p_data['difference'] = p_net - p_tgt
                p_data['scope'] = (p_net / p_tgt * 100) if p_tgt > 0 else Decimal('0.00')

        # Build Charts Data
        self._build_charts(transactions, targets, customer_types_sales)

    def _build_charts(self, transactions, targets, customer_types_sales):
        # targetBarChart
        monthly_sales = defaultdict(Decimal)
        for t in transactions:
            period_str = t['sale_date'].strftime('%Y-%m')
            monthly_sales[period_str] += self._safe_decimal(t.get('net_amount', 0))
            
        monthly_targets = defaultdict(Decimal)
        for t in targets:
            if t.get('period'):
                period_str = t['period'].strftime('%Y-%m')
                monthly_targets[period_str] += self._prorate_target(t)
                
        all_months = sorted(list(set(monthly_sales.keys()) | set(monthly_targets.keys())))
        
        target_chart_data = {
            'months': all_months,
            'sales': [float(monthly_sales[m]) for m in all_months],
            'targets': [float(monthly_targets[m]) for m in all_months],
            'scopes': [
                float((monthly_sales[m] / monthly_targets[m] * 100)) if monthly_targets[m] > 0 else 0.0
                for m in all_months
            ]
        }
        
        # clientCategoryChart
        total_cat_sales = sum(customer_types_sales.values())
        client_category_data = []
        for cat, val in customer_types_sales.items():
            client_category_data.append({
                'name': cat,
                'value': float(val),
                'percent': float((val / total_cat_sales * 100)) if total_cat_sales > 0 else 0.0
            })

        # lostAndWonBarChart (Comparing strictly previous month and current month within range or overall history)
        # We group customer purchases by month
        cust_by_month = defaultdict(set)
        for t in transactions:
            m_str = t['sale_date'].strftime('%Y-%m')
            cust_by_month[m_str].add(t['customer_id'])

        lost_won_data = {
            'months': all_months[1:] if len(all_months) > 1 else [],
            'lost': [],
            'won': []
        }
        
        for i in range(1, len(all_months)):
            prev_m = all_months[i-1]
            curr_m = all_months[i]
            
            prev_custs = cust_by_month[prev_m]
            curr_custs = cust_by_month[curr_m]
            
            lost = prev_custs - curr_custs
            won = curr_custs - prev_custs
            
            lost_won_data['lost'].append(len(lost))
            lost_won_data['won'].append(len(won))

        self.global_charts = {
            'targetBarChart': target_chart_data,
            'clientCategoryChart': client_category_data,
            'lostAndWonBarChart': lost_won_data
        }

    def get_data(self):
        # Retorna la lista de rutas procesadas en el mismo orden que routes_qs
        result_routes = []
        for r in self.routes_qs:
            if r.id in self.routes_data:
                result_routes.append(self.routes_data[r.id])
        return result_routes, self.global_charts
