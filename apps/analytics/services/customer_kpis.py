from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from dateutil.relativedelta import relativedelta
from django.db.models import QuerySet, Sum, Q
from django.utils import timezone
from collections import defaultdict

from apps.core.models import Reference
from apps.customers.models import CustomerAssignment

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

        # Last full quarter
        first_day_current_month = self.today.replace(day=1)
        self.last_day_q = first_day_current_month - relativedelta(days=1)
        self.first_day_q = self.last_day_q.replace(day=1) - relativedelta(months=2)

        # Parse or defaults
        d_start = self._parse_date(self.date_start) or self.first_day_q
        d_end = self._parse_date(self.date_end) or self.last_day_q

        # Ensure date_start <= date_end
        if d_start > d_end:
            d_start, d_end = d_end, d_start

        self.date_start = d_start
        self.date_end = d_end

    def _parse_date(self, date_val: Any) -> date | None:
        """Converts str objects to date object if necessary"""
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

    def _get_target_customers(self) -> list[Any]:
        """
        returns customers from self.customers_qs who were registered on or before self.date_end
        (or historical customers with no registration_date).
        """
        return [
            c for c in self.customers_qs
            if not c.registration_date or c.registration_date <= self.date_end
        ]

    def _get_prev_year_sales(self, customer_ids: list[Any]) -> dict[Any, Decimal]:
        """returns {customer_id: total_net_sales_prev_year}"""
        if not customer_ids:
            return {}
        sales = (
            self.transactions_qs
            .filter(customer_id__in=customer_ids, sale_date__year=self.previous_year)
            .order_by()
            .values('customer_id')
            .annotate(total=Sum('net_amount'))
        )
        return {row['customer_id']: row['total'] or Decimal('0.00') for row in sales}

    def _get_prev_quarter_sales(self, customer_ids: list[Any]) -> dict[Any, Decimal]:
        """returns {customer_id: total_net_sales_prev_quarter}"""
        if not customer_ids:
            return {}
        sales = (
            self.transactions_qs
            .filter(
                customer_id__in=customer_ids,
                sale_date__gte=self.first_day_q,
                sale_date__lte=self.last_day_q
            )
            .order_by()
            .values('customer_id')
            .annotate(total=Sum('net_amount'))
        )
        return {row['customer_id']: row['total'] or Decimal('0.00') for row in sales}

    def _get_prev_month_sales(self, customer_ids: list[Any]) -> dict[Any, Decimal]:
        """returns {customer_id: total_net_sales_prev_month}"""
        if not customer_ids:
            return {}
        last_day_prev_month = self.today.replace(day=1) - timedelta(days=1)
        first_day_prev_month = last_day_prev_month.replace(day=1)
        sales = (
            self.transactions_qs
            .filter(
                customer_id__in=customer_ids,
                sale_date__gte=first_day_prev_month,
                sale_date__lte=last_day_prev_month
            )
            .order_by()
            .values('customer_id')
            .annotate(total=Sum('net_amount'))
        )
        return {row['customer_id']: row['total'] or Decimal('0.00') for row in sales}

    def _get_curr_year_sales(self, customer_ids: list[Any]) -> dict[Any, Decimal]:
        """returns {customer_id: total_net_sales_current_year}"""
        if not customer_ids:
            return {}
        sales = (
            self.transactions_qs
            .filter(
                customer_id__in=customer_ids,
                sale_date__gte=date(self.current_year, 1, 1),
                sale_date__lte=self.today
            )
            .order_by()
            .values('customer_id')
            .annotate(total=Sum('net_amount'))
        )
        return {row['customer_id']: row['total'] or Decimal('0.00') for row in sales}

    def _calculate_period_avg(self, total_sales: Decimal | float, start_date: date, end_date: date, reg_date: date | None) -> Decimal:
        """calculates the monthly sales average for any period, respecting active months given registration date"""
        if not total_sales or total_sales <= 0:
            return Decimal('0.00')
        if not reg_date or reg_date <= start_date:
            months = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month) + 1
        elif reg_date > end_date:
            return Decimal('0.00')
        else:
            months = (end_date.year - reg_date.year) * 12 + (end_date.month - reg_date.month) + 1
        months = max(months, 1)
        return total_sales / Decimal(months)

    def _calculate_sale_frequency(self, customer_ids: list[Any]) -> dict[Any, dict[str, Any]]:
        """calculates purchase frequency per customer based on average days between purchases (> 0)"""
        if not customer_ids:
            return {}
        dates_qs = (
            self.transactions_qs
            .filter(
                customer_id__in=customer_ids,
                sale_date__gte=date(self.previous_year, 1, 1),
                net_amount__gt=0
            )
            .order_by()
            .values('customer_id', 'sale_date')
            .distinct()
            .order_by('customer_id', 'sale_date')
        )

        customer_dates = defaultdict(list)
        for row in dates_qs:
            customer_dates[row['customer_id']].append(row['sale_date'])

        freq_map = {}
        for c_id in customer_ids:
            dates = customer_dates.get(c_id, [])
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

    def _calculate_product_classes_consumption(self, customer_ids: list[Any]) -> dict[Any, dict[str, Any]]:
        """
        returns unique consumed product classes per customer (considering only relevant classes).
        returns {customer_id: {class_id: {'name': class_name, 'total': total_net_amount}}}
        """
        if not customer_ids or not self.relevant_classes:
            return {}

        classes_qs = (
            self.transactions_qs
            .filter(
                customer_id__in=customer_ids,
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

    def _get_collections_info(self, customer_ids: list[Any]) -> dict[Any, dict[str, Decimal]]:
        '''
        returns a dictionary with current balance, overdue balance and total balance for each customer.
        returns {customer_id: {'current_balance': Decimal, 'overdue_balance': Decimal, 'total_balance': Decimal}}
        '''        
        if not customer_ids:
            return {}
        ar_data = (
            self.ars_qs
            .filter(customer_id__in=customer_ids)
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

    def _get_contrib_metrics(self, customer_ids: list[Any]) -> dict[Any, dict[str, Decimal]]:
        """
        Returns contribution metrics strictly between date_start and date_end for target customers.
        {customer_id: {'net_amount': Decimal, 'profit': Decimal}}
        """
        if not customer_ids:
            return {}
        sales = (
            self.transactions_qs
            .filter(
                customer_id__in=customer_ids,
                sale_date__gte=self.date_start,
                sale_date__lte=self.date_end
            )
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

    def _get_customer_assignments_map(self, customer_ids: list[Any]) -> dict[Any, dict[str, str]]:
        """returns active route and business unit for each customer"""
        if not customer_ids:
            return {}
        assignments = (
            CustomerAssignment.objects
            .filter(customer_id__in=customer_ids)
            .filter(Q(end_date__isnull=True) | Q(end_date__gte=self.today))
            .select_related('route', 'route__business_unit')
        )
        route_map = {}
        for a in assignments:
            b_unit = a.route.business_unit.name if a.route and a.route.business_unit else ''
            route_map[a.customer_id] = {
                'route_id': a.route_id or '',
                'business_unit': b_unit,
            }
        return route_map

    def _get_monthly_consumption(self, customer_ids: list[Any]) -> dict[Any, list[dict[str, Any]]]:
        """
        calculates 12 monthly consumption slots for the current year,
        including month sales and growth vs the previous month.
        returns {customer_id: [{month_number, date, sale, growth_vs_previous_month}, ...]}
        """
        if not customer_ids:
            return {}

        monthly_sales = (
            self.transactions_qs
            .filter(
                customer_id__in=customer_ids,
                sale_date__year=self.current_year,
            )
            .order_by()
            .values('customer_id', 'sale_date__month')
            .annotate(total=Sum('net_amount'))
        )

        sales_by_customer_month = defaultdict(dict)
        for row in monthly_sales:
            cid = row['customer_id']
            month = row['sale_date__month']
            sales_by_customer_month[cid][month] = row['total'] or Decimal('0.00')

        result = {}
        for cid in customer_ids:
            monthly_list = []
            prev_sale = Decimal('0.00')
            c_sales = sales_by_customer_month.get(cid, {})

            for m in range(1, 13):
                current_sale = c_sales.get(m, Decimal('0.00'))

                if prev_sale > Decimal('0.00'):
                    growth = ((current_sale - prev_sale) / prev_sale) * Decimal('100.00')
                else:
                    growth = Decimal('100.00') if current_sale > Decimal('0.00') else Decimal('0.00')

                monthly_list.append({
                    'month_number': m,
                    'date': date(self.current_year, m, 1),
                    'sale': current_sale,
                    'growth_vs_previous_month': growth,
                })
                prev_sale = current_sale

            result[cid] = monthly_list

        return result

    def get_stats(self) -> dict[str, Any]:
        """
        returns high-level summary KPIs for the header cards in the template.
        only considers target customers registered on or before date_end.
        """
        valid_customers = self._get_target_customers()
        registered_customers = len(valid_customers)
        customer_ids = [c.id for c in valid_customers]

        contrib_map = self._get_contrib_metrics(customer_ids)

        #only takes customers with profit and net_amount > 0
        if self.order_by == 'profit':
            customers_with_consumption = sum(
                1 for c in valid_customers
                if contrib_map.get(c.id, {}).get('profit', Decimal('0.00')) > Decimal('0.00')
            )
        else:
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
        total_profit = sum(
            (contrib_map.get(c.id, {}).get('profit', Decimal('0.00')) for c in valid_customers
             if contrib_map.get(c.id, {}).get('profit', Decimal('0.00')) > Decimal('0.00')),
            Decimal('0.00')
        )

        return {
            'registered_customers': registered_customers,
            'customers_with_consumption': customers_with_consumption,
            'customers_with_consumption_pct': (Decimal(customers_with_consumption) / Decimal(registered_customers) * Decimal('100.00')) if registered_customers > 0 else Decimal('0.00'),
            'customers_without_consumption': customers_without_consumption,
            'customers_without_consumption_pct': (Decimal(customers_without_consumption) / Decimal(registered_customers) * Decimal('100.00')) if registered_customers > 0 else Decimal('0.00'),
            'net_amount': net_sales,
            'net_sales': net_sales,
            'profit': total_profit,
            'margin': (total_profit / net_sales * Decimal('100.00')) if net_sales > Decimal('0.00') else Decimal('0.00')
        }

    def read_customer_kpis(self) -> list:
        """Builds and returns fully enriched customer records sorted by Pareto criterion"""
        customers = self._get_target_customers()
        customer_ids = [c.id for c in customers]

        # Consumption amounts and metrics
        prev_year_sales_map = self._get_prev_year_sales(customer_ids)
        prev_quarter_sales_map = self._get_prev_quarter_sales(customer_ids)
        prev_month_sales_map = self._get_prev_month_sales(customer_ids)
        curr_year_sales_map = self._get_curr_year_sales(customer_ids)
        freq_sales_map = self._calculate_sale_frequency(customer_ids)
        classes_consumption_map = self._calculate_product_classes_consumption(customer_ids)
        collections_map = self._get_collections_info(customer_ids)
        contrib_metrics_map = self._get_contrib_metrics(customer_ids)
        routes_map = self._get_customer_assignments_map(customer_ids)
        monthly_consumption_map = self._get_monthly_consumption(customer_ids)

        # Period ranges
        start_prev_y = date(self.previous_year, 1, 1)
        end_prev_y = date(self.previous_year, 12, 31)
        start_curr_y = date(self.current_year, 1, 1)
        end_curr_y = self.today

        global_net = Decimal('0.00')
        global_profit = Decimal('0.00')

        for customer in customers:
            c_id = customer.id
            reg_date = customer.registration_date

            #current route and business unit
            r_info = routes_map.get(c_id, {})
            customer.current_route_id = r_info.get('route_id', '-')
            customer.current_route_business_unit = r_info.get('business_unit', '-')

            # Previous periods sales
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

            #monthly consumption breakdown
            customer.monthly_consumption = monthly_consumption_map.get(c_id, [])

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