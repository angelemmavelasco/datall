from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from dateutil.relativedelta import relativedelta
from django.db.models import QuerySet, Sum
from django.utils import timezone
from collections import defaultdict

from apps.core.models import Reference

@dataclass
class CustomerKpisService:
    user: Any
    customers_qs: QuerySet
    transactions_qs: QuerySet
    ars_qs: QuerySet
    date_start: date | str | None = None
    date_end: date | str | None = None
    cleaned_data: dict[str, Any] | None = None
    # calcs and attrs
    order_by: str = field(default='net_amount', init=False)
    today: date = field(init=False)
    current_year: int = field(init=False)
    previous_year: int = field(init=False)
    first_day_q: date = field(init=False)
    last_day_q: date = field(init=False)
    categories: list[tuple[str, Decimal]] = field(default_factory=list, init=False)
    frequency_categories: list[tuple[str, int]] = field(default_factory=list, init=False)
    relevant_classes: list[tuple[str, str]] = field(default_factory=list, init=False)

    def __post_init__(self):
        self._init_dates()
        self._init_config()

    def _init_dates(self) -> None:
        self.today = timezone.localdate()
        self.current_year = self.today.year
        self.previous_year = self.current_year - 1
        #last full quarter
        first_day_current_month = self.today.replace(day=1)
        self.last_day_q = first_day_current_month - relativedelta(days=1)
        self.first_day_q = self.last_day_q.replace(day=1) - relativedelta(months=2)
        #parse or defaults
        self.date_start = self._parse_date(self.date_start) or self.first_day_q
        self.date_end = self._parse_date(self.date_end) or self.last_day_q

    def _parse_date(self, date_val: Any) -> date | None:
        '''
        converts str objs to date obj if necesary
        '''
        if not date_val:
            return None
        if isinstance(date_val, date) and not isinstance(date_val, datetime):
            return date_val
        if isinstance(date_val, datetime):
            return date_val.date()
        if isinstance(date_val, str):
            for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d'):
                try:
                    return datetime.strptime(date_val.strip(), fmt).date()
                except ValueError:
                    continue
        return None

    def _init_config(self) -> None:
        """init config vars from cleaned_data."""
        config = self.cleaned_data or {}
        self.order_by = config.get('order_contrib') or 'net_amount'
        self._init_categories()
        self._init_frequency_categories()
        self._init_relevant_classes()

    class CategoryObj:
        """aux obj to make categories accessible in template"""
        def __init__(self, name: str):
            self.name = name.lower()
        def __str__(self):
            return self.name
    
    def _init_categories(self) -> None:
        refs = Reference.objects.filter(context='categoria_cliente_monto')
        self.categories = sorted(
            [(r.key.lower(), Decimal(r.value)) for r in refs],
            key=lambda x: x[1],
            reverse=True
        )

    def _init_frequency_categories(self) -> None:
        refs = Reference.objects.filter(context='categoria_frecuencia_compra')
        parsed = []
        for r in refs:
            try:
                parsed.append((r.key.strip().lower(), int(r.value)))
            except (ValueError, TypeError):
                continue
        if parsed:
            self.frequency_categories = sorted(parsed, key=lambda x: x[1])
        else:
            self.frequency_categories = [('regular', 30), ('irregular', 60)]

    def _init_relevant_classes(self) -> None:
        refs = Reference.objects.filter(context='clases_producto_relevantes')
        classes = [r.key.strip().lower() for r in refs if r.key]
        if classes:
            self.relevant_classes = classes
        else:
            self.relevant_classes = ['dmd', 'nat', 'tow', 'care', 'msd', 'vtq', 'zts']

    def _calculate_category(self, sales: Decimal | float | None = None) -> str:
        '''returns the category which the customer belongs given a sales amount'''
        if sales is None:
            return 'c'
        sales_dec = Decimal(str(sales))
        for name, min_amount in self.categories:
            if sales_dec >= min_amount:
                return name
        return 'c'

    def _get_prev_year_sales(self) -> dict[Any, Decimal]:
        '''
        returns {customer_id: total_net_sales_prev_year}
        '''
        sales = (
            self.transactions_qs
            .filter(sale_date__year=self.previous_year)
            .order_by()
            .values('customer_id')
            .annotate(total=Sum('net_amount'))
        )
        return {row['customer_id']: row['total'] or Decimal('0.00') for row in sales}

    def _get_prev_quarter_sales(self) -> dict[Any, Decimal]:
        """
        returns {customer_id: total_net_sales_prev_quarter}
        """
        sales = (
            self.transactions_qs
            .filter(sale_date__gte=self.first_day_q, sale_date__lte=self.last_day_q)
            .order_by()
            .values('customer_id')
            .annotate(total=Sum('net_amount'))
        )
        return {row['customer_id']: row['total'] or Decimal('0.00') for row in sales}

    def _get_prev_month_sales(self) -> dict[Any, Decimal]:
        last_day_prev_month = timezone.now().date().replace(day=1) - timedelta(days=1)
        first_day_prev_month = last_day_prev_month.replace(day=1)
        sales = (
            self.transactions_qs
            .filter(sale_date__gte=first_day_prev_month, sale_date__lte=last_day_prev_month)
            .order_by()
            .values('customer_id')
            .annotate(total=Sum('net_amount'))
        )
        return {row['customer_id']: row['total'] or Decimal('0.00') for row in sales}

    def _get_curr_year_sales(self) -> dict[Any, Decimal]:
        sales = (
            self.transactions_qs
            .filter(sale_date__gte=date(self.current_year, 1, 1), sale_date__lte=self.today)
            .order_by()
            .values('customer_id')
            .annotate(total=Sum('net_amount'))
        )
        return {row['customer_id']: row['total'] or Decimal('0.00') for row in sales}

    def _calculate_period_avg(self, total_sales: Decimal | float, start_date: date, end_date: date, reg_date: date |None) -> Decimal:
        '''
        calculates the monthly sales average for any period, by respecting active months given the registration date
        '''
        if not total_sales or total_sales <= 0:
            return Decimal('0.00')
        if not reg_date or reg_date <= start_date:
            #the customer was active all period
            months = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month) + 1
        elif reg_date > end_date:
            #the customer was not active during this period
            return Decimal('0.00')
        else:
            #the customer was active for part of the period
            months = (end_date.year - reg_date.year) * 12 + (end_date.month - reg_date.month) + 1
        months = max(months, 1)
        return total_sales / Decimal(months)

    def _calculate_sale_frequency(self) -> dict[Any, dict[str, Any]]:
        """
        calculates the purchase frequency by customer based on the average number of days between purchases (> 0).
        returns {customer_id: {'name': 'regular', 'days': 15}}
        """
        dates_qs = (
            self.transactions_qs
            .filter(sale_date__gte=date(self.previous_year, 1, 1), net_amount__gt=0)
            .order_by()
            .values('customer_id', 'sale_date')
            .distinct()
            .order_by('customer_id', 'sale_date')
        )

        customer_dates = defaultdict(list)
        for row in dates_qs:
            customer_dates[row['customer_id']].append(row['sale_date'])

        freq_map = {}
        for c_id, dates in customer_dates.items():
            if len(dates) < 2:
                freq_map[c_id] = {'name': 'nula', 'days': 0}
                continue

            intervals = [(dates[i] - dates[i-1]).days for i in range(1, len(dates))]
            avg_interval = round(sum(intervals) / len(intervals)) if intervals else 0

            freq_name = 'atipico'
            for name, max_days in self.frequency_categories:
                if avg_interval <= max_days:
                    freq_name = name
                    break

            freq_map[c_id] = {'name': freq_name, 'days': avg_interval}

        return freq_map

    def _calculate_product_classes_consumption(self) -> dict[Any, dict[str, Any]]:
        '''
        returns unique consumed product classes per customer (considering only relevant classes).
        returns {customer_id: {class_id: {'name': class_name, 'total': total_net_amount}}}
        '''
        classes_qs = (
            self.transactions_qs
            .filter(
                sale_date__gte=self.first_day_q,
                sale_date__lte=self.last_day_q,
                net_amount__gt=0,
                product_class_id__in=self.relevant_classes
            )
            .order_by()
            .values('customer_id', 'product_class_id', 'product_class__name')
            .annotate(total=Sum('net_amount'))
        )

        classes_map = defaultdict(dict)
        for row in classes_qs:
            cid = row['customer_id']
            class_id = row['product_class_id']
            class_name = row['product_class__name'] or class_id
            classes_map[cid][class_id] = {
                'name': class_name,
                'total': row['total'] or Decimal('0.00')
            }

        return dict(classes_map)

    def _get_collections_info(self) -> dict[Any, dict[str, Decimal]]:
        '''
        returns a dictionary with current balance, overdue balance and total balance for each customer.
        returns {customer_id: {'current_balance': Decimal, 'overdue_balance': Decimal, 'total_balance': Decimal}}
        '''
        ar_data = (
            self.ars_qs
            .order_by()
            .values('customer_id')
            .annotate(
                total_balance=Sum('total_balance'),
                current_balance=Sum('current_balance')
            )
        )
        collections_map = {}
        for row in ar_data:
            cid = row['customer_id']
            curr_b = row['current_balance'] or Decimal('0.00')
            tot_b = row['total_balance'] or Decimal('0.00')
            overdue_b = max(tot_b - curr_b, Decimal('0.00'))
            collections_map[cid] = {
                'current_balance': curr_b,
                'overdue_balance': overdue_b,
                'total_balance': tot_b,
            }
        return collections_map

    def _get_contrib_metrics(self) -> dict[Any, dict[str, Decimal]]:
        '''
        returns a dict with the necesary information to know contrib metrics about a customer.
        {customer_id: {'net_amount': Decimal, 'profit': Decimal}}
        '''
        sales = (
            self.transactions_qs
            .filter(sale_date__gte=self.date_start, sale_date__lte=self.date_end)
            .order_by()
            .values('customer_id')
            .annotate(
                net_amount=Sum('net_amount'),
                profit=Sum('profit')
            )
        )
        return {
            row['customer_id']: {
                'net_amount': row['net_amount'] or Decimal('0.00'),
                'profit': row['profit'] or Decimal('0.00'),
            }
            for row in sales
        }

    def get_stats(self) -> dict[str, Any]:
        """
        Returns high-level summary KPIs for the header cards in the template.
        Only considers customers registered on or before date_end and with net consumption > 0.
        """
        valid_customers = [c for c in self.customers_qs if not c.registration_date or c.registration_date <= self.date_end]
        registered_customers = len(valid_customers)

        contrib_map = self._get_contrib_metrics()
        customers_with_consumption = sum(
            1 for c in valid_customers
            if contrib_map.get(c.id, {}).get('net_amount', Decimal('0.00')) > Decimal('0.00')
        )
        customers_without_consumption = max(registered_customers - customers_with_consumption, 0)
        
        net_sales = sum(
            (contrib_map.get(c.id, {}).get('net_amount', Decimal('0.00')) for c in valid_customers
             if contrib_map.get(c.id, {}).get('net_amount', Decimal('0.00')) > Decimal('0.00')),
            Decimal('0.00')
        )

        return {
            'registered_customers': registered_customers,
            'customers_with_consumption': customers_with_consumption,
            'customers_with_consumption_pct': (Decimal(customers_with_consumption) / Decimal(registered_customers) * Decimal('100.00')) if registered_customers > 0 else Decimal('0.00'),
            'customers_without_consumption': customers_without_consumption,
            'customers_without_consumption_pct': (Decimal(customers_without_consumption) / Decimal(registered_customers) * Decimal('100.00')) if registered_customers > 0 else Decimal('0.00'),
            'net_sales': net_sales,
        }

    def get_table_records(self) -> list:
        #consumption amounts and metrics
        prev_year_sales_map = self._get_prev_year_sales()
        prev_quarter_sales_map = self._get_prev_quarter_sales()
        prev_month_sales_map = self._get_prev_month_sales()
        curr_year_sales_map = self._get_curr_year_sales()
        freq_sales_map = self._calculate_sale_frequency()
        classes_consumption_map = self._calculate_product_classes_consumption()
        collections_map = self._get_collections_info()
        contrib_metrics_map = self._get_contrib_metrics()

        #accesible range date
        start_prev_y = date(self.previous_year, 1, 1)
        end_prev_y = date(self.previous_year, 12, 31)
        start_curr_y = date(self.current_year, 1, 1)
        end_curr_y = self.today

        customers = list(self.customers_qs)
        global_net = Decimal('0.00')
        global_profit = Decimal('0.00')

        for customer in customers:
            c_id = customer.id
            reg_date = customer.registration_date

            #prev periods sales
            customer.previous_year_total = prev_year_sales_map.get(c_id, Decimal('0.00'))
            customer.previous_quarter_total = prev_quarter_sales_map.get(c_id, Decimal('0.00'))
            customer.previous_month_total = prev_month_sales_map.get(c_id, Decimal('0.00'))
            customer.current_year_total = curr_year_sales_map.get(c_id, Decimal('0.00'))
            
            #prev sale avg
            customer.previous_year_avg = self._calculate_period_avg(customer.previous_year_total, start_prev_y, end_prev_y, reg_date)
            customer.previous_quarter_avg = self._calculate_period_avg(customer.previous_quarter_total, self.first_day_q, self.last_day_q, reg_date)
            customer.current_year_avg = self._calculate_period_avg(customer.current_year_total, start_curr_y, end_curr_y, reg_date)

            #categories according to prev periods sales
            customer.category_prev_year = self.CategoryObj(self._calculate_category(customer.previous_year_avg))
            customer.category_prev_quarter = self.CategoryObj(self._calculate_category(customer.previous_quarter_avg))
            customer.category_prev_month = self.CategoryObj(self._calculate_category(customer.previous_month_total))

            #sale freq
            c_freq = freq_sales_map.get(c_id, {'name': 'nula', 'days': 0})
            customer.frequency = c_freq['name']
            customer.frequency_days = c_freq['days']

            #collections
            col_info = collections_map.get(c_id, {
                'current_balance': Decimal('0.00'),
                'overdue_balance': Decimal('0.00'),
                'total_balance': Decimal('0.00'),
            })
            customer.current_balance = col_info['current_balance']
            customer.overdue_balance = col_info['overdue_balance']
            customer.total_balance = col_info['total_balance']

            credit_limit = customer.credit_limit or Decimal('0.00')
            if credit_limit > Decimal('0.00'):
                customer.credit_usage = (customer.total_balance / credit_limit) * Decimal('100.00')
            else:
                customer.credit_usage = Decimal('0.00')

            #agreements
            customer.active_agreements = 0

            #classes consumption
            customer.product_classes_consumed = classes_consumption_map.get(c_id, {})
            customer.product_classes_with_consumption = len(customer.product_classes_consumed)

            #contrib metrics
            c_contrib = contrib_metrics_map.get(c_id, {'net_amount': Decimal('0.00'), 'profit': Decimal('0.00')})
            customer.performance_net_amount = c_contrib['net_amount']
            customer.performance_profit = c_contrib['profit']
            customer.selected_contrib_by = 'profit' if self.order_by == 'profit' else 'net_amount'

            global_net += customer.performance_net_amount
            global_profit += customer.performance_profit

        #pareto sorting & accumulation based on selected criterion
        if self.order_by == 'profit':
            active_customers = [c for c in customers if c.performance_profit > Decimal('0.00')]
            active_customers.sort(key=lambda x: x.performance_profit, reverse=True)
        else:
            active_customers = [c for c in customers if c.performance_net_amount > Decimal('0.00')]
            active_customers.sort(key=lambda x: x.performance_net_amount, reverse=True)

        total_active_customers = len(active_customers)
        cumuled_val = Decimal('0.00')

        for index, customer in enumerate(active_customers, start=1):
            if global_net > Decimal('0.00'):
                customer.contrib_net_amount = (customer.performance_net_amount / global_net) * Decimal('100.00')
            else:
                customer.contrib_net_amount = Decimal('0.00')
            customer.net_amount = customer.contrib_net_amount

            if global_profit > Decimal('0.00'):
                customer.contrib_profit = (customer.performance_profit / global_profit) * Decimal('100.00')
            else:
                customer.contrib_profit = Decimal('0.00')
            customer.profit = customer.contrib_profit

            primary_contrib = customer.contrib_profit if self.order_by == 'profit' else customer.contrib_net_amount
            cumuled_val += primary_contrib
            customer.cumuled_contrib = cumuled_val
            customer.cumuled_portafolio_count = index
            customer.cumuled_portafolio_pct = (Decimal(index) / Decimal(total_active_customers)) * Decimal('100.00') if total_active_customers > 0 else Decimal('0.00')

        active_ids = set(c.id for c in active_customers)
        inactive_customers = [c for c in customers if c.id not in active_ids]
        for customer in inactive_customers:
            customer.contrib_net_amount = Decimal('0.00')
            customer.net_amount = Decimal('0.00')
            customer.contrib_profit = Decimal('0.00')
            customer.profit = Decimal('0.00')
            customer.cumuled_contrib = Decimal('0.00')
            customer.cumuled_portafolio_count = 0
            customer.cumuled_portafolio_pct = Decimal('0.00')

        return active_customers + inactive_customers