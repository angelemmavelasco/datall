from datetime import datetime, date
from decimal import Decimal
from collections import defaultdict
from dateutil.relativedelta import relativedelta
from django.db.models import Sum, F, Count, Max, Min
from apps.core.models import Customer, SaleTransaction, AccountsReceivable, Reference
import io
import csv


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

    def calculate_contrib(self, dashboard_customers, transactions, contrib_config):
        """
        Calculates performance and Pareto contribution metrics in memory.
        Requires:
        - contrib_config: dict with 'order_contrib', 'start_date', 'end_date'
        """
        start_date = contrib_config.get('start_date')
        end_date = contrib_config.get('end_date')
        order_by = contrib_config.get('order_contrib', 'net_amount')

        if start_date and isinstance(start_date, str):
            try:
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
                contrib_config['start_date'] = start_date
            except ValueError:
                pass

        if end_date and isinstance(end_date, str):
            try:
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
                contrib_config['end_date'] = end_date
            except ValueError:
                pass

        contrib_qs = transactions
        if start_date:
            contrib_qs = contrib_qs.filter(sale_date__gte=start_date)
        if end_date:
            contrib_qs = contrib_qs.filter(sale_date__lte=end_date)

        customer_performance_qs = contrib_qs.values('customer_id').annotate(
            total_net=Sum('net_amount'),
            total_profit=Sum('profit')
        )
        perf_net = defaultdict(Decimal)
        perf_profit = defaultdict(Decimal)


        
        for row in customer_performance_qs:
            perf_net[row['customer_id']] = row['total_net'] or Decimal('0.00')
            perf_profit[row['customer_id']] = row['total_profit'] or Decimal('0.00')

        global_net = sum(perf_net.values())
        global_profit = sum(perf_profit.values())


        if end_date:
            valid_customers = [c for c in dashboard_customers if c.registration_date and c.registration_date <= end_date]
        else:
            valid_customers = dashboard_customers

        registered_customers = len(valid_customers)

        customers_with_consumption = sum(1 for c in valid_customers if perf_net[c.id] > 0)
        
        customers_without_consumption = registered_customers - customers_with_consumption

        kpis_dict = {
            'registered_customers': registered_customers,
            'customers_with_consumption': customers_with_consumption,
            'customers_with_consumption_pct': customers_with_consumption/registered_customers*100 if registered_customers > 0 else 0,
            'customers_without_consumption': customers_without_consumption,
            'customers_without_consumption_pct': customers_without_consumption/registered_customers*100 if registered_customers > 0 else 0,
            'net_sales': global_net,
        }

        
        if order_by == 'net_amount':
            active_customers = [c for c in dashboard_customers if perf_net[c.id] > 0]
        else: # profit
            active_customers = [c for c in dashboard_customers if perf_profit[c.id] > 0]

        total_active_customers = len(active_customers)

        for c in dashboard_customers:
            c.performance_net_amount = perf_net[c.id]
            c.performance_profit = perf_profit[c.id]
            c.selected_contrib_by = 'Venta neta' if order_by == 'net_amount' else 'Utilidad'
            
            c.contrib_net_amount = Decimal('0.00')
            c.contrib_profit = Decimal('0.00')
            c.cumuled_contrib = Decimal('0.00')
            c.cumuled_portafolio_count = 0
            c.cumuled_portafolio_pct = Decimal('0.00')

        if total_active_customers == 0:
            dashboard_customers.sort(key=lambda x: getattr(x, 'performance_net_amount'), reverse=True)
            return dashboard_customers, kpis_dict

        if order_by == 'net_amount':
            active_customers.sort(key=lambda x: x.performance_net_amount, reverse=True)
        else:
            active_customers.sort(key=lambda x: x.performance_profit, reverse=True)

        cumuled_val = Decimal('0.00')
        
        for index, customer in enumerate(active_customers, start=1):
            if global_net > 0:
                customer.contrib_net_amount = (customer.performance_net_amount / global_net) * 100
            if global_profit > 0:
                customer.contrib_profit = (customer.performance_profit / global_profit) * 100

            if order_by == 'net_amount':
                cumuled_val += customer.contrib_net_amount
            else:
                cumuled_val += customer.contrib_profit
                
            customer.cumuled_contrib = cumuled_val
            customer.cumuled_portafolio_count = index
            customer.cumuled_portafolio_pct = (Decimal(index) / Decimal(total_active_customers)) * 100

        inactive_customers = [c for c in dashboard_customers if c not in active_customers]
        
        final_sorted_customers = active_customers + inactive_customers

        return final_sorted_customers, kpis_dict

    def build_dashboard_data(self, contrib_config=None):
        """
        Assembles all the KPIs to send them to the template.
        """

        if contrib_config is None:
            contrib_config = {}
        
        today = date.today()
        current_year = today.year
        previous_year = current_year - 1
        
        first_day_current_month = date(today.year, today.month, 1)
        last_day_q = first_day_current_month - relativedelta(days=1)
        first_day_q = last_day_q.replace(day=1) - relativedelta(months=2)

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
            sale_date__gte=first_day_q,
            sale_date__lte=last_day_q
        ).values('customer_id', month=F('sale_date__month')).annotate(
            monthly_total=Sum('net_amount')
        )

        totals_trim = defaultdict(Decimal)
        active_months_trim = defaultdict(int)

        for row in monthly_sales_trim_qs:
            cid = row['customer_id']
            totals_trim[cid] += (row['monthly_total'] or Decimal('0.00'))
            active_months_trim[cid] += 1

        relevant_product_classes = Reference.objects.filter(
            field_context='relevant_product_classes',
            key='customer',
            module__url_name='business_intelligence:customers_kpis'
        ).values_list('reference', flat=True)
        print(relevant_product_classes)

        product_classes_qs = transactions.filter(
            sale_date__year=current_year,
            product_class_id__in=relevant_product_classes
        ).values('customer_id').annotate(
            classes_count=Count('product_class_id', distinct=True)
        )
        product_classes_count = {row['customer_id']: row['classes_count'] for row in product_classes_qs}

        frequency_qs = transactions.filter(
            net_amount__gt=0,
            sale_date__year__gte=current_year - 1 # Last 1-2 years is usually enough for frequency
        ).values('customer_id').annotate(
            min_date=Min('sale_date'),
            max_date=Max('sale_date'),
            doc_count=Count('doc_id', distinct=True)
        )

        frequency_dict = {}
        for row in frequency_qs:
            cid = row['customer_id']
            min_date = row['min_date']
            max_date = row['max_date']
            doc_count = row['doc_count']

            if doc_count > 1 and min_date and max_date:
                avg_diff = (max_date - min_date).days / (doc_count - 1)
                frequency_dict[cid] = avg_diff
            else:
                frequency_dict[cid] = None

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
            
            if reg_date and first_day_q <= reg_date <= last_day_q:
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
                customer.overdue_balance = (ar.past_due + ar.balance_15 + ar.balance_30 + ar.balance_60) or Decimal('0.00')
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

        if not contrib_config.get('start_date') or not contrib_config.get('end_date'):
             contrib_config['start_date'] = first_day_q
             contrib_config['end_date'] = last_day_q

        dashboard_customers, kpis_dict = self.calculate_contrib(dashboard_customers, transactions, contrib_config)

        return dashboard_customers, months_headers, kpis_dict


    def export_report_data(self, contrib_config=None):
        """
        Genera el CSV en memoria y retorna el contenido puro (string).
        """
        buffer = io.StringIO()
        buffer.write('\ufeff') 
        writer = csv.writer(buffer)

        all_customers_data, months_headers, _ = self.build_dashboard_data(contrib_config)

        header_row = [
            'ID Cliente','Cliente', 'Ruta', 'Gerencia', 'Tipo de cliente', 'Categoría', 
            'Frecuencia', 'Líder de opinión','Límite de crédito', 'Saldo al corriente', 'Saldo vencido', 
            'Uso (%)', 'Convenios activos', 'Clases de producto', 'Promedio año previo', 
            'Promedio año actual', 'Promedio trimestre', 
            # todo: mas a delante cambiar permisos para que vendedores no puedan ver utilidad
            # 'Contribución: venta neta','Contribución: aporte global', 'Contribución acumulada', 'Conteo clientes', 'Conteo porcentual clientes'
        ]
        for h in months_headers:
            month_str = h.strftime('%b %Y').title()
            header_row.append(f'{month_str} ($)')
            header_row.append(f'{month_str} Crecimiento (%)')
            
        writer.writerow(header_row)

        for c in all_customers_data:
            opinion_leader_str = "Sí" if getattr(c, 'opinion_leader', False) else "No"
            
            client_display = c.name.title()
            route_display = getattr(c.route, 'id', '') if hasattr(c, 'route') and c.route else ''
            warehouse_display = getattr(c.route.warehouse, 'name', '') if hasattr(c, 'route') and c.route and hasattr(c.route, 'warehouse') and c.route.warehouse else ''
            customer_type_display = getattr(c.customer_type, 'name', '') if hasattr(c, 'customer_type') and c.customer_type else ''
            
            row = [
                c.id,
                client_display,
                route_display,
                warehouse_display.title(),
                customer_type_display.title(),
                getattr(c.category_last_moving_q, 'name', '').title(),
                getattr(c, 'frequency', '').title(),
                opinion_leader_str.title(),
                round(getattr(c, 'credit_limit', 0), 2),
                round(getattr(c, 'current_balance', 0), 2),
                round(getattr(c, 'overdue_balance', 0), 2),
                round(getattr(c, 'credit_usage', 0), 2),
                getattr(c, 'active_agreements', 0),
                getattr(c, 'product_classes_with_consumption', 0),
                round(getattr(c, 'previous_year_average', 0), 2),
                round(getattr(c, 'current_year_average', 0), 2),
                round(getattr(c, 'previous_moving_quarter_average', 0), 2),




                # round(getattr(c, 'performance_net_amount', 0), 2),
                # round(getattr(c, 'contrib_net_amount', 0), 2),
                # round(getattr(c, 'cumuled_contrib', 0), 2),
                # getattr(c, 'cumuled_portafolio_count', 0),
                # getattr(c, 'cumuled_portafolio_pct', 0),
            ]
            for m in getattr(c, 'monthly_consumption_qs', []):
                row.append(round(m.get('sale', 0), 2))
                row.append(round(m.get('growth_vs_previous_month', 0), 0))
                
            writer.writerow(row)

        return buffer.getvalue()





class MockClass:
    """Clase auxiliar para enviar atributos como objetos al template (.name)"""
    def __init__(self, name):
        self.name = name


class CustomerProfileBuilder:
    def __init__(self, customer, filters=None):
        self.customer = customer
        self.today = date.today()
        self.filters = filters or {}

        # 1. Periodo Mensual (Mes inmediato anterior entero)
        self.first_day_curr_month = self.today.replace(day=1)
        self.last_day_prev_month = self.first_day_curr_month - relativedelta(days=1)
        self.first_day_prev_month = self.last_day_prev_month.replace(day=1)

        # 2. Periodo Trimestral (3 meses enteros previos al mes actual)
        self.first_day_last_q = self.first_day_prev_month - relativedelta(months=2)

        # 3. Periodo Anual (Año inmediato anterior entero: Ene-Dic)
        self.prev_year = self.today.year - 1
        self.first_day_prev_year = date(self.prev_year, 1, 1)
        self.last_day_prev_year = date(self.prev_year, 12, 31)

    def build(self):
        """Ejecuta todos los cálculos y retorna el cliente enriquecido."""
        self._set_monthly_category()
        self._set_quarterly_category()
        self._set_annual_category()
        self._set_purchase_frequency()
        self._set_classes_kpis()
        self._set_accounts_receivable()
        self._set_monthly_consumption()
        return self.customer

    def _set_monthly_category(self):
        sales = SaleTransaction.objects.filter(
            customer=self.customer,
            sale_date__gte=self.first_day_prev_month,
            sale_date__lte=self.last_day_prev_month
        ).aggregate(total=Sum('net_amount'))['total'] or Decimal('0.00')

        self.customer.monthly_consumption_category = get_category(sales)

    def _set_quarterly_category(self):
        sales = SaleTransaction.objects.filter(
            customer=self.customer,
            sale_date__gte=self.first_day_last_q,
            sale_date__lte=self.last_day_prev_month
        ).aggregate(total=Sum('net_amount'))['total'] or Decimal('0.00')

        reg_date = self.customer.registration_date

        if reg_date and self.first_day_last_q <= reg_date <= self.last_day_prev_month:
            # Meses activos desde su registro en el trimestre
            active_months = (self.last_day_prev_month.year - reg_date.year) * 12 + (self.last_day_prev_month.month - reg_date.month) + 1
        else:
            active_months = 3

        avg_q = (sales / Decimal(active_months)) if active_months > 0 else Decimal('0.00')
        self.customer.q_consumption_category = get_category(avg_q)

    def _set_annual_category(self):
        sales = SaleTransaction.objects.filter(
            customer=self.customer,
            sale_date__gte=self.first_day_prev_year,
            sale_date__lte=self.last_day_prev_year
        ).aggregate(total=Sum('net_amount'))['total'] or Decimal('0.00')

        reg_date = self.customer.registration_date
        months_divisor = 0

        if reg_date:
            if reg_date.year < self.prev_year:
                months_divisor = 12
            elif reg_date.year == self.prev_year:
                months_divisor = 12 - reg_date.month + 1
        else:
            months_divisor = 12

        avg_yearly = (sales / Decimal(months_divisor)) if months_divisor > 0 else Decimal('0.00')
        self.customer.annual_consumption_category = get_category(avg_yearly)

    def _set_purchase_frequency(self):
        # distinct() en sale_date agrupa múltiples doc_id del mismo día en un solo registro
        dates = SaleTransaction.objects.filter(
            customer=self.customer,
            net_amount__gt=0
        ).values_list('sale_date', flat=True).distinct().order_by('sale_date')

        dates_list = list(dates)

        if len(dates_list) < 2:
            self.customer.purchase_frequency_category = 'Nula'
            self.customer.purchase_frequency_days = ""
            return

        intervals = [(dates_list[i] - dates_list[i-1]).days for i in range(1, len(dates_list))]
        avg_interval = sum(intervals) / len(intervals)

        if avg_interval <= 30:
            self.customer.purchase_frequency_category = 'Regular'
        elif avg_interval <= 60:
            self.customer.purchase_frequency_category = 'Irregular'
        else:
            self.customer.purchase_frequency_category = 'Atípico'

        self.customer.purchase_frequency_days = f"cada {int(avg_interval)} días"

    def _set_classes_kpis(self):
        # Histórico de clases consumidas
        classes_count = SaleTransaction.objects.filter(
            customer=self.customer,
            net_amount__gt=0
        ).values('product_class_id').distinct().count()

        self.customer.consumed_classes = classes_count

        # Clase más consumida en el trimestre anterior
        top_class = SaleTransaction.objects.filter(
            customer=self.customer,
            sale_date__gte=self.first_day_last_q,
            sale_date__lte=self.last_day_prev_month,
            net_amount__gt=0
        ).values(
            class_name=F('product_class__name') # O ajusta a 'product_class__name' si ese es tu campo
        ).annotate(
            total_net=Sum('net_amount')
        ).order_by('-total_net').first()

        if top_class and top_class['class_name']:
            self.customer.most_consumed_class_last_q = MockClass(top_class['class_name'])
        else:
            self.customer.most_consumed_class_last_q = MockClass('Sin consumo reciente')

    def _set_accounts_receivable(self):
        # Toma el registro más reciente de la tabla histórica de cobranza
        latest_ar = AccountsReceivable.objects.filter(
            customer=self.customer
        ).order_by('-period', '-id').first()

        if latest_ar:
            self.customer.total_balance = latest_ar.total_balance or Decimal('0.00')
            self.customer.overdue_balance = latest_ar.past_due or Decimal('0.00')
            self.customer.balance_15 = latest_ar.balance_15 or Decimal('0.00')
            self.customer.balance_30 = latest_ar.balance_30 or Decimal('0.00')
            self.customer.balance_60 = latest_ar.balance_60 or Decimal('0.00')
            self.customer.past_due = latest_ar.past_due or Decimal('0.00')
        else:
            self.customer.total_balance = Decimal('0.00')
            self.customer.overdue_balance = Decimal('0.00')
            self.customer.balance_15 = Decimal('0.00')
            self.customer.balance_30 = Decimal('0.00')
            self.customer.balance_60 = Decimal('0.00')
            self.customer.past_due = Decimal('0.00')

        credit_limit = self.customer.credit_limit or Decimal('0.00')
        if credit_limit > 0:
            self.customer.credit_usage = (self.customer.total_balance / credit_limit) * 100
        else:
            self.customer.credit_usage = Decimal('0.00')

    def _set_monthly_consumption(self):
        from django.db.models import Min, Max, Sum
        from django.db.models.functions import TruncMonth

        qs = SaleTransaction.objects.filter(customer=self.customer)
        
        date_start = self.filters.get('date_start')
        date_end = self.filters.get('date_end')
        
        if date_start:
            qs = qs.filter(sale_date__gte=date_start)
        if date_end:
            qs = qs.filter(sale_date__lte=date_end)
            
        warehouses = self.filters.get('warehouses')
        if warehouses:
            qs = qs.filter(route__warehouse_id__in=warehouses)
            
        regions = self.filters.get('regions')
        if regions:
            qs = qs.filter(route__warehouse__region_id__in=regions)
            
        product_classes = self.filters.get('product_classes')
        if product_classes:
            qs = qs.filter(product_class_id__in=product_classes)
            
        product_categories = self.filters.get('product_categories')
        if product_categories:
            qs = qs.filter(product_class__product_category_id__in=product_categories)

        agg = qs.aggregate(min_date=Min('sale_date'), max_date=Max('sale_date'))
        min_date = agg['min_date']
        max_date = agg['max_date']
        
        if not min_date or not max_date:
            self.customer.monthly_consumption_by_class = []
            self.customer.consumption_months = []
            self.customer.consumption_totals = {}
            return
            
        months_list = []
        current = date(min_date.year, min_date.month, 1)
        end_month = date(max_date.year, max_date.month, 1)
        while current <= end_month:
            months_list.append(current)
            current += relativedelta(months=1)

        grouped = qs.values(
            'product_class__id', 
            'product_class__name'
        ).annotate(
            month=TruncMonth('sale_date'),
            total=Sum('net_amount')
        )

        classes_dict = {}
        for row in grouped:
            c_id = row['product_class__id']
            c_name = row['product_class__name'] or 'Sin Clase'
            m = row['month']
            if hasattr(m, 'date'):
                m = m.date()
            m = date(m.year, m.month, 1)
            
            if c_id not in classes_dict:
                classes_dict[c_id] = {
                    'product_class': {'id': c_id, 'name': c_name},
                    'months': {mon: Decimal('0.00') for mon in months_list},
                    'total': Decimal('0.00')
                }
                
            val = row['total'] or Decimal('0.00')
            classes_dict[c_id]['months'][m] += val
            classes_dict[c_id]['total'] += val

        sorted_classes = sorted(classes_dict.values(), key=lambda x: x['total'], reverse=True)

        totals_row = {
            'months': {mon: Decimal('0.00') for mon in months_list},
            'grand_total': Decimal('0.00')
        }
        
        for pc in sorted_classes:
            for mon in months_list:
                totals_row['months'][mon] += pc['months'][mon]
            totals_row['grand_total'] += pc['total']
            pc['monthly_amounts'] = [pc['months'][mon] for mon in months_list]

        totals_row['monthly_amounts'] = [totals_row['months'][mon] for mon in months_list]
        
        self.customer.monthly_consumption_by_class = sorted_classes
        self.customer.consumption_months = months_list
        self.customer.consumption_totals = totals_row