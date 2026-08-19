from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from dateutil.relativedelta import relativedelta
from django.db.models import QuerySet, Q, Sum, Count
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from apps.core.models import Reference
from apps.customers.models import AccountsReceivable
from apps.customers.services.customers import CustomersService
from apps.sales.services.sale_transactions import SaleTransactionsService

if TYPE_CHECKING:
    from apps.core.models import User as UserType

class MockCategory:
    def __init__(self, name):
        self.name = name

@dataclass
class CustomerKpisService:
    """
    Service responsible for aggregating and transforming customer KPI metrics.
    Reuses CustomersService for permissions and SaleTransactionsService for full sales records.
    """
    user: Any
    customers_qs: QuerySet | None = None
    transactions_qs: QuerySet | None = None
    date_start: date | None = None
    date_end: date | None = None
    cleaned_data: dict[str, Any] | None = None

    _resolved_customers_qs: QuerySet | None = field(default=None, init=False, repr=False)
    _resolved_transactions_qs: QuerySet | None = field(default=None, init=False, repr=False)
    _categorizations: list[tuple[str, float]] | None = field(default=None, init=False, repr=False)
    _calculated_kpis: dict[str, Any] | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        self._init_dates()

    def _init_dates(self) -> None:
        """
        Normalizes date_start and date_end.
        Defaults to current full quarter equivalent logic if not specified.
        """
        today = timezone.now().date()

        def _parse_val(val: Any) -> date | None:
            if not val:
                return None
            if isinstance(val, date) and not isinstance(val, datetime):
                return val
            if isinstance(val, datetime):
                return val.date()
            if isinstance(val, str):
                for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d'):
                    try:
                        return datetime.strptime(val.strip(), fmt).date()
                    except ValueError:
                        continue
            return None

        self.date_start = _parse_val(self.date_start)
        self.date_end = _parse_val(self.date_end)

        first_day_current_month = date(today.year, today.month, 1)
        last_day_q = first_day_current_month - relativedelta(days=1)
        first_day_q = last_day_q.replace(day=1) - relativedelta(months=2)

        if not self.date_start:
            self.date_start = first_day_q
        if not self.date_end:
            self.date_end = last_day_q

    def _get_dynamic_categorizations(self) -> list[tuple[str, float]]:
        if self._categorizations is not None:
            return self._categorizations

        try:
            ct = ContentType.objects.get(app_label='customers', model='customer')
            refs = Reference.objects.filter(
                context='categorizacion_clientes_consumo',
                content_type=ct
            )
            cat_list = []
            for ref in refs:
                try:
                    val = float(ref.value.replace(',', '').strip())
                    cat_list.append((ref.key.strip(), val))
                except (ValueError, AttributeError, TypeError):
                    continue
            
            cat_list.sort(key=lambda x: x[1], reverse=True)
            self._categorizations = cat_list
        except ContentType.DoesNotExist:
            self._categorizations = []

        return self._categorizations

    def _get_category(self, sales: Decimal | float) -> str:
        categorizations = self._get_dynamic_categorizations()
        if not categorizations:
            categorizations = [
                ('DIAMANTE', 250000),
                ('ORO', 100000),
                ('AA', 25000),
                ('A', 3000),
                ('C', 0),
            ]

        sales_val = float(sales) if sales is not None else 0.0
        
        for label, threshold in categorizations:
            if sales_val >= threshold:
                return label
        return 'C'

    def _base_qs(self) -> tuple[QuerySet, QuerySet]:
        if self._resolved_customers_qs is not None and self._resolved_transactions_qs is not None:
            return self._resolved_customers_qs, self._resolved_transactions_qs

        #allowed customers
        if self.customers_qs is not None:
            c_qs = self.customers_qs
        else:
            customers_service = CustomersService(user=self.user)
            c_qs = customers_service.read_customers()

        #transactions for allowed customers (all routes)
        if self.transactions_qs is not None:
            tx_qs = self.transactions_qs
        else:
            tx_service = SaleTransactionsService(user=self.user)
            tx_qs = tx_service.read_transactions_by_allowed_customers()

        self._resolved_customers_qs = c_qs
        self._resolved_transactions_qs = tx_qs

        return self._resolved_customers_qs, self._resolved_transactions_qs

    def get_table_records(self) -> list[Any]:
        customers_qs, tx_qs = self._base_qs()
        dashboard_customers = list(customers_qs)
        customer_ids = [c.id for c in dashboard_customers]

        if not customer_ids:
            self._calculated_kpis = {
                'registered_customers': 0,
                'customers_with_consumption': 0,
                'customers_with_consumption_pct': 0.0,
                'customers_without_consumption': 0,
                'customers_without_consumption_pct': 0.0,
                'net_sales': 0.0,
            }
            return []

        today = timezone.now().date()
        current_year = today.year
        previous_year = current_year - 1

        first_day_current_month = date(today.year, today.month, 1)
        last_day_q = first_day_current_month - relativedelta(days=1)
        first_day_q = last_day_q.replace(day=1) - relativedelta(months=2)

        start_contrib = self.date_start or first_day_q
        end_contrib = self.date_end or last_day_q
        
        order_by = 'net_amount'
        if self.cleaned_data:
            order_by = self.cleaned_data.get('order_contrib', 'net_amount')

        relevant_product_classes = Reference.objects.filter(
            context='relevant_product_classes',
            key='customer'
        ).values_list('value', flat=True)

        annotations = {
            'prev_year_total': Sum('net_amount', filter=Q(sale_date__year=previous_year)),
            'trim_total': Sum('net_amount', filter=Q(sale_date__gte=first_day_q, sale_date__lte=last_day_q)),
            'contrib_net': Sum('net_amount', filter=Q(sale_date__gte=start_contrib, sale_date__lte=end_contrib)),
            'contrib_profit': Sum('profit', filter=Q(sale_date__gte=start_contrib, sale_date__lte=end_contrib)),
            'classes_qty': Count('product_class_id', distinct=True, filter=Q(sale_date__gte=date(previous_year, 1, 1), product_class_id__in=relevant_product_classes)),
        }

        for m in range(1, 13):
            annotations[f'm_{m}'] = Sum('net_amount', filter=Q(sale_date__year=current_year, sale_date__month=m))

        earliest_date = min(first_day_q, start_contrib, date(previous_year, 1, 1))
        
        sales_stats = tx_qs.filter(
            customer_id__in=customer_ids,
            sale_date__gte=earliest_date
        ).values('customer_id').annotate(**annotations)

        stats_map = {row['customer_id']: row for row in sales_stats}

        ar_qs = AccountsReceivable.objects.filter(
            customer_id__in=customer_ids
        ).values('customer_id').annotate(
            total_balance=Sum('total_balance'),
            current_balance=Sum('current_balance'),
        )
        ar_map = {row['customer_id']: row for row in ar_qs}

        freq_dates_qs = tx_qs.filter(
            customer_id__in=customer_ids,
            sale_date__gte=date(previous_year, 1, 1),
            net_amount__gt=0
        ).values('customer_id', 'sale_date').distinct().order_by('customer_id', 'sale_date')

        freq_map = defaultdict(list)
        for row in freq_dates_qs:
            freq_map[row['customer_id']].append(row['sale_date'])

        global_net = Decimal('0.00')
        global_profit = Decimal('0.00')

        for customer in dashboard_customers:
            cid = customer.id
            row = stats_map.get(cid, {})

            total_trim = row.get('trim_total') or Decimal('0.00')
            reg_date = customer.registration_date
            
            if reg_date and first_day_q <= reg_date <= last_day_q:
                months_divisor = (last_day_q.year - reg_date.year) * 12 + (last_day_q.month - reg_date.month) + 1
                months_divisor = max(months_divisor, 1)
            else:
                months_divisor = 3
                
            avg_trim = total_trim / Decimal(months_divisor)
            customer.category_last_moving_q = MockCategory(self._get_category(avg_trim))
            customer.previous_moving_quarter_average = avg_trim

            dates_list = freq_map.get(cid, [])
            if len(dates_list) < 2:
                freq_text = "Nula"
            else:
                intervals = [(dates_list[i] - dates_list[i-1]).days for i in range(1, len(dates_list))]
                avg_interval = sum(intervals) / len(intervals)

                if avg_interval <= 30: freq_text = "Regular"
                elif avg_interval <= 60: freq_text = "Irregular"
                else: freq_text = "Atípico"
            
            customer.frequency = freq_text

            ar = ar_map.get(cid)
            if ar:
                customer.current_balance = ar.get('current_balance') or Decimal('0.00')
                total_balance = ar.get('total_balance') or Decimal('0.00')
                customer.overdue_balance = total_balance - customer.current_balance
            else:
                customer.current_balance = Decimal('0.00')
                customer.overdue_balance = Decimal('0.00')
                total_balance = Decimal('0.00')

            credit_limit = customer.credit_limit or Decimal('0.00')
            customer.credit_usage = (total_balance / credit_limit) * 100 if credit_limit > 0 else Decimal('0.00')

            customer.active_agreements = 0 
            customer.product_classes_with_consumption = row.get('classes_qty') or 0
            customer.previous_year_average = (row.get('prev_year_total') or Decimal('0.00')) / Decimal('12.00')
            current_year_total = Decimal('0.00')
            monthly_qs = []
            prev_month_sale = Decimal('0.00')
            
            for m in range(1, 13):
                current_sale = row.get(f'm_{m}') or Decimal('0.00')
                current_year_total += current_sale
                
                if prev_month_sale > 0:
                    growth = ((current_sale - prev_month_sale) / prev_month_sale) * 100
                else:
                    growth = Decimal('100.00') if current_sale > 0 else Decimal('0.00')
                    
                monthly_qs.append({
                    'month_number': m,
                    'date': date(current_year, m, 1),
                    'sale': current_sale,
                    'growth_vs_previous_month': growth
                })
                prev_month_sale = current_sale
                
            customer.monthly_consumption_qs = monthly_qs
            customer.current_year_average = current_year_total / Decimal(max(today.month, 1))

            c_net = row.get('contrib_net') or Decimal('0.00')
            c_profit = row.get('contrib_profit') or Decimal('0.00')
            
            customer.performance_net_amount = c_net
            customer.performance_profit = c_profit
            customer.selected_contrib_by = 'Venta neta' if order_by == 'net_amount' else 'Utilidad'
            
            customer.contrib_net_amount = Decimal('0.00')
            customer.contrib_profit = Decimal('0.00')
            customer.cumuled_contrib = Decimal('0.00')
            customer.cumuled_portafolio_count = 0
            customer.cumuled_portafolio_pct = Decimal('0.00')
            
            global_net += c_net
            global_profit += c_profit

        return self._apply_pareto_and_sort(
            dashboard_customers, order_by, end_contrib, global_net, global_profit
        )

    def _apply_pareto_and_sort(self, customers: list[Any], order_by: str, end_contrib: date, global_net: Decimal, global_profit: Decimal) -> list[Any]:
        valid_customers = [c for c in customers if not c.registration_date or c.registration_date <= end_contrib]
        registered_customers = len(valid_customers)
        customers_with_consumption = sum(1 for c in valid_customers if c.performance_net_amount > 0)
        customers_without_consumption = registered_customers - customers_with_consumption

        self._calculated_kpis = {
            'registered_customers': registered_customers,
            'customers_with_consumption': customers_with_consumption,
            'customers_with_consumption_pct': round((customers_with_consumption / registered_customers) * 100, 2) if registered_customers > 0 else 0.0,
            'customers_without_consumption': customers_without_consumption,
            'customers_without_consumption_pct': round((customers_without_consumption / registered_customers) * 100, 2) if registered_customers > 0 else 0.0,
            'net_sales': round(float(global_net), 2),
        }

        if order_by == 'net_amount':
            active_customers = [c for c in customers if c.performance_net_amount > 0]
            active_customers.sort(key=lambda c: c.performance_net_amount, reverse=True)
            global_total = global_net
        else:
            active_customers = [c for c in customers if c.performance_profit > 0]
            active_customers.sort(key=lambda c: c.performance_profit, reverse=True)
            global_total = global_profit

        total_active_customers = len(active_customers)
        cumuled = Decimal('0.00')
        for idx, customer in enumerate(active_customers, start=1):
            if order_by == 'net_amount':
                val = customer.performance_net_amount
            else:
                val = customer.performance_profit

            cumuled += val
            customer.contrib_net_amount = (val / global_total * Decimal('100.00')) if global_total > 0 else Decimal('0.00')
            customer.cumuled_contrib = (cumuled / global_total * Decimal('100.00')) if global_total > 0 else Decimal('0.00')
            customer.cumuled_portafolio_count = idx
            customer.cumuled_portafolio_pct = (Decimal(idx) / Decimal(total_active_customers) * Decimal('100.00')) if total_active_customers > 0 else Decimal('0.00')

            customer.contrib_profit = customer.performance_profit
            customer.contrib_start_date = self.date_start
            customer.contrib_end_date = self.date_end

        active_ids = set(c.id for c in active_customers)
        inactive_customers = [c for c in customers if c.id not in active_ids]
        for customer in inactive_customers:
            customer.contrib_start_date = self.date_start
            customer.contrib_end_date = self.date_end

        return active_customers + inactive_customers

    def get_stats(self) -> dict[str, Any]:
        """Returns top-level KPIs for customer dashboard"""
        if self._calculated_kpis is not None:
            return self._calculated_kpis
        self.get_table_records()
        return self._calculated_kpis or {}

    def get_kpis(self) -> dict[str, Any]:
        """Alias for get_stats"""
        return self.get_stats()

    def get_months_headers(self) -> list[date]:
        """Returns 12 month start dates for current year"""
        current_year = timezone.now().date().year
        return [date(current_year, m, 1) for m in range(1, 13)]
