from datetime import datetime, date
from decimal import Decimal
from collections import defaultdict
from dateutil.relativedelta import relativedelta
from django.db.models import Sum, F, Count, Max
from apps.core.models import Customer, SaleTransaction, AccountsReceivable

CATEGORIZATIONS = [
    ('DIAMANTE', 250_000),
    ('ORO', 100_000),
    ('AA', 25_000),
    ('A', 3_000),
    ('C', 0),
]

def get_category(sales):
    if sales is None:
        return 'C'
    for label, threshold in CATEGORIZATIONS:
        if sales >= threshold:
            return label
    return 'C'

class MockCategory:
    def __init__(self, name):
        self.name = name

class CustomersKpis:
    def __init__(self, customers_qs):
        self.customers_qs = customers_qs

    def build_dashboard_data(self):
        """
        Assembles all the KPIs to send them to the template.
        """
        today = date.today()
        current_year = today.year
        previous_year = current_year - 1
        
        first_day_current_month = date(today.year, today.month, 1)
        last_day_trimestre = first_day_current_month - relativedelta(days=1)
        first_day_trimestre = last_day_trimestre.replace(day=1) - relativedelta(months=2)

        dashboard_customers = list(self.customers_qs)
        customer_ids = [c.id for c in dashboard_customers]

        if not customer_ids:
            return [], []

        transactions = SaleTransaction.objects.filter(customer_id__in=customer_ids)

        current_year_sales_qs = transactions.filter(
            sale_date__year=current_year
        ).values('customer_id', month_num=F('sale_date__month')).annotate(
            total_sale=Sum('net_amount')
        )
        
        monthly_sales = {cid: {m: Decimal('0.00') for m in range(1, 13)} for cid in customer_ids}
        for row in current_year_sales_qs:
            monthly_sales[row['customer_id']][row['month_num']] = row['total_sale'] or Decimal('0.00')

        prev_year_sales_qs = transactions.filter(
            sale_date__year=previous_year
        ).values('customer_id').annotate(
            total_sale=Sum('net_amount')
        )
        prev_year_sales = {row['customer_id']: row['total_sale'] or Decimal('0.00') for row in prev_year_sales_qs}

        monthly_sales_trim_qs = transactions.filter(
            sale_date__gte=first_day_trimestre,
            sale_date__lte=last_day_trimestre
        ).values('customer_id', month=F('sale_date__month')).annotate(
            monthly_total=Sum('net_amount')
        )

        totals_trim = defaultdict(Decimal)
        active_months_trim = defaultdict(int)

        for row in monthly_sales_trim_qs:
            cid = row['customer_id']
            totals_trim[cid] += (row['monthly_total'] or Decimal('0.00'))
            active_months_trim[cid] += 1

        product_classes_qs = transactions.filter(
            sale_date__year=current_year
        ).values('customer_id').annotate(
            classes_count=Count('product_class_id', distinct=True)
        )
        product_classes_count = {row['customer_id']: row['classes_count'] for row in product_classes_qs}

        positive_txs = transactions.filter(
            net_amount__gt=0,
            sale_date__year__gte=current_year - 1 # Last 1-2 years is usually enough for frequency
        ).values('customer_id', 'doc_id', 'sale_date').distinct().order_by('customer_id', 'sale_date')

        customer_dates = defaultdict(list)
        for tx in positive_txs:
            customer_dates[tx['customer_id']].append(tx['sale_date'])

        frequency_dict = {}
        for cid, dates in customer_dates.items():
            if len(dates) > 1:
                diffs = [(dates[i] - dates[i-1]).days for i in range(1, len(dates))]
                avg_diff = sum(diffs) / len(diffs)
            else:
                avg_diff = None
            frequency_dict[cid] = avg_diff

        latest_period = AccountsReceivable.objects.aggregate(max_date=Max('period'))['max_date']
        accounts_receivable = {}
        if latest_period:
            ar_qs = AccountsReceivable.objects.filter(
                customer_id__in=customer_ids,
                period=latest_period
            )
            for ar in ar_qs:
                accounts_receivable[ar.customer_id] = ar

        months_headers = []
        for month_num in range(1, 13):
            months_headers.append(date(current_year, month_num, 1))
        for customer in dashboard_customers:
            cid = customer.id
            
            reg_date = customer.registration_date
            total_trim = totals_trim.get(cid, Decimal('0.00'))
            
            if reg_date and first_day_trimestre <= reg_date <= last_day_trimestre:
                months_divisor = active_months_trim.get(cid, 0)
            else:
                months_divisor = 3
                
            avg_trim = (total_trim / months_divisor) if months_divisor > 0 else Decimal('0.00')
            customer.category_last_moving_q = MockCategory(get_category(avg_trim))
            customer.previous_moving_quarter_average = avg_trim

            avg_diff = frequency_dict.get(cid)
            if avg_diff is None:
                freq_text = "Nula"
            elif avg_diff <= 30:
                freq_text = "Regular"
            elif avg_diff <= 60:
                freq_text = "Irregular"
            else:
                freq_text = "Atípico"
            customer.frequency = freq_text


            ar = accounts_receivable.get(cid)
            if ar:
                customer.current_balance = ar.current_balance or Decimal('0.00')
                customer.overdue_balance = ar.past_due or Decimal('0.00')
                total_balance = ar.total_balance or Decimal('0.00')
            else:
                customer.current_balance = Decimal('0.00')
                customer.overdue_balance = Decimal('0.00')
                total_balance = Decimal('0.00')

            credit_limit = customer.credit_limit or Decimal('0.00')
            if credit_limit > 0:
                customer.credit_usage = (total_balance / credit_limit) * 100
            else:
                customer.credit_usage = Decimal('0.00')

            # Metrics
            customer.active_agreements = 0 # Placeholder ya que no existe modelo de convenios
            customer.product_classes_with_consumption = product_classes_count.get(cid, 0)
            
            customer.previous_year_average = prev_year_sales.get(cid, Decimal('0.00')) / Decimal('12.00')
            customer.current_year_average = sum(monthly_sales[cid].values()) / Decimal(max(today.month, 1))

            # Monthly breakdown
            customer_sales = monthly_sales[cid]
            monthly_qs = []
            previous_month_sale = Decimal('0.00')
            
            for month_num in range(1, 13):
                current_sale = customer_sales[month_num]
                
                if previous_month_sale > 0:
                    growth = ((current_sale - previous_month_sale) / previous_month_sale) * 100
                else:
                    growth = Decimal('100.00') if current_sale > 0 else Decimal('0.00')
                    
                monthly_qs.append({
                    'month_number': month_num,
                    'date': date(current_year, month_num, 1),
                    'sale': current_sale,
                    'growth_vs_previous_month': growth
                })
                previous_month_sale = current_sale

            customer.monthly_consumption_qs = monthly_qs

        # Sort the customers by category avg_trim as per calculate_categorizations_trim
        dashboard_customers.sort(key=lambda x: getattr(x, 'previous_moving_quarter_average', Decimal('0.00')), reverse=True)

        return dashboard_customers, months_headers