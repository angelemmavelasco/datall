from decimal import Decimal
from collections import defaultdict
import datetime
from apps.sales.services.sale_transactions.sale_transactions_crud import SaleTransactionCRUD
from apps.sales.services.sale_targets.sale_targets_crud import SaleTargetCRUD
from apps.core.models import Customer, AccountsReceivable
import calendar
from django.db.models import OuterRef, Subquery, Sum, Count, Q

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

    def _get_applicable_target(self, t, start_date=None, end_date=None):
        """
        Devuelve el 100% del target si el periodo (mes/año) 
        tiene algún solapamiento con el rango de fechas establecido.
        """
        target_amount = self._safe_decimal(t.get('target_amount', 0))
        
        d_start = start_date if start_date else self.date_start
        d_end = end_date if end_date else self.date_end

        if not d_start and not d_end:
            return target_amount

        period = t.get('period')
        if not period:
            return target_amount

        if isinstance(period, str):
            try:
                period = datetime.datetime.strptime(period, '%Y-%m-%d').date()
            except ValueError:
                return target_amount
        
        month_start = period.replace(day=1)
        _, last_day = calendar.monthrange(month_start.year, month_start.month)
        month_end = datetime.date(month_start.year, month_start.month, last_day)

        start = d_start if d_start else month_start
        end = d_end if d_end else month_end

        overlap_start = max(month_start, start)
        overlap_end = min(month_end, end)

        if overlap_start <= overlap_end:
            return target_amount

        return Decimal('0.00')

    def _initialize_routes(self):
        from apps.core.models import RouteAssignment
        
        route_ids = [r.id for r in self.routes_qs]
        active_assignments = RouteAssignment.objects.filter(
            route_id__in=route_ids,
            end_date__isnull=True
        ).select_related('employee__user')
        
        photo_dict = {}
        for assignment in active_assignments:
            if assignment.employee and assignment.employee.user and assignment.employee.user.photo:
                photo_dict[assignment.route_id] = assignment.employee.user.photo.url
                
        for route in self.routes_qs:
            r_id = route.id
            self.routes_data[r_id] = {
                'id': r_id,
                'name': route.name,
                'photo_url': photo_dict.get(r_id),
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





            c_type = t.get('customer__customer_type__name') or 'Desconocido'
            customer_types_sales[c_type] += net

        for r_id, cust_set in customers_with_purchases.items():
            self.routes_data[r_id]['clients_with_purchases'] = len(cust_set)




        for t in targets:
            r_id = t.get('route_id')
            if not r_id or r_id not in self.routes_data:
                continue

            target_amt = self._get_applicable_target(t)
            self.routes_data[r_id]['sale_target'] += target_amt

            p_class = str(t.get('product_class_id') or 'otr').lower()
            if p_class not in self.routes_data[r_id]['product_class_performance']:
                p_class = 'otr'

            self.routes_data[r_id]['product_class_performance'][p_class]['target'] += target_amt
            self.routes_data[r_id]['product_class_performance']['total']['target'] += target_amt




        route_ids = [r.id for r in self.routes_qs]
        customers = Customer.objects.filter(route_id__in=route_ids).values('route_id', 'credit_limit', 'id', 'registration_date')
        
        for c in customers:
            r_id = c['route_id']
            if r_id in self.routes_data:
                reg_date = c.get('registration_date')
                rd = None
                if reg_date:
                    rd = reg_date.date() if hasattr(reg_date, 'date') else reg_date
                
                if self.date_end and rd and rd > self.date_end:
                    continue

                self.routes_data[r_id]['collections']['total_credit'] += self._safe_decimal(c.get('credit_limit'))
                self.routes_data[r_id]['clients'] += 1
                
                # new clients logic
                if rd and self.date_start and self.date_end:
                    if self.date_start <= rd <= self.date_end:
                        self.routes_data[r_id]['new_clients'] += 1
        
        #accs recaivale
        ar_query = Q(customer__route_id__in=route_ids)

        if self.date_end:
            ar_query &= (Q(issue_date__lte=self.date_end) | Q(issue_date__isnull=True))

        ars = AccountsReceivable.objects.filter(
            ar_query
        ).values(
            'customer__route_id'
        ).annotate(
            total_balance_sum=Sum('total_balance'),
            current_balance_sum=Sum('current_balance'),
            balance_15_sum=Sum('balance_15'),
            balance_30_sum=Sum('balance_30'),
            balance_60_sum=Sum('balance_60'),
            past_due_sum=Sum('past_due'),
            
            accounts_with_debt=Count(
                'customer_id', 
                filter=Q(total_balance__gt=0), 
                distinct=True
            )
        )
        

        for ar in ars:
            r_id = ar['customer__route_id']
            
            if r_id in self.routes_data:
                total_bal = self._safe_decimal(ar.get('total_balance_sum'))
                
                self.routes_data[r_id]['collections']['total_balance'] += total_bal
                self.routes_data[r_id]['collections']['current_balance'] += self._safe_decimal(ar.get('current_balance_sum'))
                self.routes_data[r_id]['collections']['days_1_15'] += self._safe_decimal(ar.get('balance_15_sum'))
                self.routes_data[r_id]['collections']['days_16_30'] += self._safe_decimal(ar.get('balance_30_sum'))
                self.routes_data[r_id]['collections']['days_31_60'] += self._safe_decimal(ar.get('balance_60_sum'))
                self.routes_data[r_id]['collections']['days_60_over'] += self._safe_decimal(ar.get('past_due_sum'))
                
                overdue = (
                    self._safe_decimal(ar.get('balance_15_sum')) + 
                    self._safe_decimal(ar.get('balance_30_sum')) + 
                    self._safe_decimal(ar.get('balance_60_sum')) + 
                    self._safe_decimal(ar.get('past_due_sum'))
                )
                self.routes_data[r_id]['collections']['overdue_balance'] += overdue

                self.routes_data[r_id]['collections']['overdue_count'] += ar.get('accounts_with_debt', 0)


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

        self._build_charts(transactions, targets, customer_types_sales)

    def _build_charts(self, transactions, targets, customer_types_sales):
        is_single_month = False
        if self.date_start and self.date_end:
            if self.date_start.year == self.date_end.year and self.date_start.month == self.date_end.month:
                is_single_month = True

        if is_single_month:
            chart_start_date = datetime.date(self.date_end.year, 1, 1)
            chart_end_date = datetime.date.today()

            chart_filters = {}
            chart_filters['sale_date_start'] = chart_start_date.strftime('%Y-%m-%d')
            chart_filters['sale_date_end'] = chart_end_date.strftime('%Y-%m-%d')

            target_filters = {}
            target_filters['period_start'] = chart_start_date.strftime('%Y-%m-%d')
            target_filters['period_end'] = chart_end_date.strftime('%Y-%m-%d')

            trans_crud = SaleTransactionCRUD()
            transactions_qs = trans_crud.read(self.routes_qs, **chart_filters)
            chart_transactions = list(transactions_qs.values('sale_date', 'net_amount', 'customer_id'))

            targets_crud = SaleTargetCRUD()
            targets_qs = targets_crud.read(self.routes_qs, **target_filters)
            chart_targets = list(targets_qs.values('period', 'target_amount'))
        else:
            chart_transactions = transactions
            chart_targets = targets
            chart_start_date = self.date_start
            chart_end_date = self.date_end

        monthly_sales = defaultdict(Decimal)
        for t in chart_transactions:
            if t.get('sale_date'):
                period_str = t['sale_date'].strftime('%Y-%m')
                monthly_sales[period_str] += self._safe_decimal(t.get('net_amount', 0))
            
        monthly_targets = defaultdict(Decimal)
        for t in chart_targets:
            if t.get('period'):
                period_str = t['period'].strftime('%Y-%m')
                monthly_targets[period_str] += self._get_applicable_target(t, chart_start_date, chart_end_date)
                
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
        
        total_cat_sales = sum(customer_types_sales.values())
        client_category_data = []
        for cat, val in customer_types_sales.items():
            client_category_data.append({
                'name': cat,
                'value': float(val),
                'percent': float((val / total_cat_sales * 100)) if total_cat_sales > 0 else 0.0
            })

        cust_by_month = defaultdict(set)
        for t in chart_transactions:
            if t.get('sale_date') and t.get('customer_id'):
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
        result_routes = []
        for r in self.routes_qs:
            if r.id in self.routes_data:
                result_routes.append(self.routes_data[r.id])
        return result_routes, self.global_charts
