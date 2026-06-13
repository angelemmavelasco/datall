from decimal import Decimal
from collections import defaultdict
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from typing import List, Dict, Any
import math
import statistics
from dateutil.relativedelta import relativedelta
from django.db.models import Sum

from apps.core.models import SaleTransaction, Customer

class CommercialRisk:
    def __init__(self, date_start: str = None, date_end: str = None, route_id: str = None):
        """
        params
        ------
        date_start: str
            Start date of the period.
        date_end: str
            End date of the period.
        route_id: str
            ID of the route wihcih is gonna be used for filter customers.
        """
        self.date_start = date_start
        self.date_end = date_end
        self.route_id = route_id

        #set base month timeline
        self.months_timeline = self._generate_months_timeline()

        #get customers only for this route and its registration date
        customers_qs = Customer.objects.filter(route_id=route_id).values('id', 'registration_date')
        self.customers_reg_dates = {c['id']: c['registration_date'] for c in customers_qs}

        #get trasnsactions, no matter who made it, just making sure is currently in the route
        self.transactions = SaleTransaction.objects.filter(
            sale_date__gte=date_start,
            sale_date__lte=date_end,
            customer__route_id=route_id
        ).values('sale_date', 'customer_id', 'net_amount')

        #group by month
        self.monthly_sales = defaultdict(lambda: defaultdict(Decimal))
        for tx in self.transactions:
            month_key = tx['sale_date'].strftime('%Y-%m')
            self.monthly_sales[month_key][tx['customer_id']] += tx['net_amount']



    def _generate_months_timeline(self) -> List[str]:
        """
        Generates a base timeline of months from the start date to the end date.
        
        returns:
        --------
        list[str]
            A list of months in the format 'YYYY-MM'.
        """
        months = []
        current = self.date_start.replace(day=1)
        while current <= self.date_end:
            months.append(current.strftime('%Y-%m'))
            current += relativedelta(months=1)
        return months


    def _customers_churn(self) -> Dict[str, List[int | str]]:
        """
        Calculate customers churn rate.

        return:
        --------
        dict
            A dictionary with the following keys:
            - months: list[str]
            - lost_customers: list[int]
            - won_customers: list[int]
            
        """
        won_customers = []
        lost_customers = []

        for i, current_month in enumerate(self.months_timeline):
            if i == 0:
                won_customers.append(0)
                lost_customers.append(0)
                continue
            
            prev_month = self.months_timeline[i - 1]
            
            prev_active = set(cid for cid, amount in self.monthly_sales[prev_month].items() if amount > 0)
            curr_active = set(cid for cid, amount in self.monthly_sales[current_month].items() if amount > 0)

            won = len(curr_active - prev_active)
            lost = len(prev_active - curr_active)

            won_customers.append(won)
            lost_customers.append(lost)

        return {
            'won_customers': won_customers,
            'lost_customers': lost_customers
        }

    def _new_and_active_customers(self) -> Dict[str, List[Any]]:
        """
        Calculate new customers and active customers percentage per month.

        returns:
        --------
        dict
            A dictionary with the following keys:
            - new_customers: list[int]
            - portfolio_scope: list[float]
        """
        new_customers_list = []
        portfolio_scope_list = []

        for month_str in self.months_timeline:
            new_count = sum(
                1 for reg_date in self.customers_reg_dates.values() 
                if reg_date.strftime('%Y-%m') == month_str
            )
            new_customers_list.append(new_count)


            total_portfolio_size = sum(
                1 for reg_date in self.customers_reg_dates.values() 
                if reg_date.strftime('%Y-%m') <= month_str
            )
            
            active_count = sum(1 for amount in self.monthly_sales[month_str].values() if amount > 0)

            if total_portfolio_size > 0:
                scope_percent = round((active_count / total_portfolio_size) * 100, 2)
            else:
                scope_percent = 0.0

            portfolio_scope_list.append(scope_percent)

        return {
            'new_customers': new_customers_list,
            'portfolio_scope': portfolio_scope_list
        }



    def _volatility_and_volume(self) -> Dict[str, Any]:
        scatter_data = []
        vol_list = []
        cv_list = []

        customer_sales = defaultdict(dict)
        for month, c_data in self.monthly_sales.items():
            for cid, amount in c_data.items():
                customer_sales[cid][month] = amount

        for cid, reg_date in self.customers_reg_dates.items():
            reg_month = reg_date.strftime('%Y-%m')
            
            valid_months = [m for m in self.months_timeline if m >= reg_month]
            n_months = len(valid_months)
            
            if n_months == 0:
                continue

            sales_data = [float(customer_sales[cid].get(m, 0)) for m in valid_months]
            total_sales = sum(sales_data)
            
            if total_sales == 0:
                continue

            mean_sales = total_sales / n_months

            variance = sum((s - mean_sales)**2 for s in sales_data) / n_months
            std_dev = math.sqrt(variance)
            cv = std_dev / mean_sales if mean_sales > 0 else 0
            recent_months = valid_months[-3:] if n_months >= 3 else valid_months
            recent_sales = [float(customer_sales[cid].get(m, 0)) for m in recent_months]
            recent_mean = sum(recent_sales) / len(recent_months)
            
            momentum = recent_mean / mean_sales if mean_sales > 0 else 0

            scatter_data.append([round(mean_sales, 2), round(cv, 4), round(momentum, 4), cid])
            vol_list.append(mean_sales)
            cv_list.append(cv)
        vol_threshold = 0
        cv_threshold = 0
        if vol_list:
            vol_list.sort()
            cv_list.sort()
            vol_threshold = vol_list[int(len(vol_list) * 0.75)]
            cv_threshold = cv_list[int(len(cv_list) * 0.50)]

        return {
            'scatter_data': scatter_data,
            'thresholds': {
                'volume': round(vol_threshold, 2),
                'volatility': round(cv_threshold, 4)
            }
        }

    def _growth_and_bias(self) -> Dict[str, Any]:
        scatter_data = []

        customer_sales = defaultdict(dict)
        for month, c_data in self.monthly_sales.items():
            for cid, amount in c_data.items():
                customer_sales[cid][month] = amount

        for cid, reg_date in self.customers_reg_dates.items():
            reg_month = reg_date.strftime('%Y-%m')
            
            valid_months = [m for m in self.months_timeline if m >= reg_month]
            n_months = len(valid_months)
            
            if n_months == 0:
                continue

            sales_data = [float(customer_sales[cid].get(m, 0)) for m in valid_months]
            total_sales = sum(sales_data)
            
            if total_sales == 0:
                continue

            mean_sales = total_sales / n_months
            median_sales = statistics.median(sales_data)

            bias = (mean_sales - median_sales) / abs(mean_sales) if mean_sales > 0 else 0

            recent_months = valid_months[-3:] if n_months >= 3 else valid_months
            recent_sales = [float(customer_sales[cid].get(m, 0)) for m in recent_months]
            recent_mean = sum(recent_sales) / len(recent_months)
            
            momentum = recent_mean / mean_sales if mean_sales > 0 else 0


            scatter_data.append([round(momentum, 4), round(bias, 4), round(mean_sales, 2), cid])

        return {
            'scatter_data': scatter_data,
            'thresholds': {
                'momentum': 1.0, # Umbral universal de crecimiento
                'bias': 0.0      # Umbral universal de estabilidad
            }
        }

    def get_global_kpis(self) -> Dict[str, Any]:
        """
        Calcula los KPIs absolutos del último trimestre móvil completado.
        Ignora self.date_start y self.date_end.
        """
        today = date.today()
        
        end_q_date = today.replace(day=1) - relativedelta(days=1)
        start_q_date = (end_q_date.replace(day=1) - relativedelta(months=2))

        #alcance y gini
        quarter_customer_sales = SaleTransaction.objects.filter(
            sale_date__gte=start_q_date,
            sale_date__lte=end_q_date,
            customer__route_id=self.route_id
        ).values('customer_id').annotate(total_sales=Sum('net_amount'))

        total_customers = sum(
            1 for reg_date in self.customers_reg_dates.values() 
            if reg_date <= end_q_date
        )

        active_customers = 0
        sales_list = []

        for item in quarter_customer_sales:
            amount = float(item['total_sales'] or 0)
            if amount > 0:
                active_customers += 1
                sales_list.append(amount)

        # Cálculo Alcance
        if total_customers > 0:
            portfolio_scope = active_customers / total_customers
        else:
            portfolio_scope = 0.0

        # Cálculo Gini
        gini_index = 0.0
        if sales_list:
            sales_sorted = sorted(sales_list)
            n = len(sales_sorted)
            cum_sales = sum(sales_sorted)
            if cum_sales > 0:

                sum_iy = sum((i + 1) * y for i, y in enumerate(sales_sorted))
                gini_index = (2.0 * sum_iy / (n * cum_sales)) - ((n + 1.0) / n)

        #momentum
        route_transactions = SaleTransaction.objects.filter(
            route_id=self.route_id,
            sale_date__lte=end_q_date 
        ).values('sale_date', 'net_amount')

        route_monthly_sales = defaultdict(float)
        for tx in route_transactions:
            month_key = tx['sale_date'].strftime('%Y-%m')
            route_monthly_sales[month_key] += float(tx['net_amount'])

        # Promedio histórico de la ruta
        total_historical_months = len(route_monthly_sales)
        historical_avg = sum(route_monthly_sales.values()) / total_historical_months if total_historical_months > 0 else 0

        # Promedio del último trimestre de la ruta
        q_months = [
            start_q_date.strftime('%Y-%m'),
            (start_q_date + relativedelta(months=1)).strftime('%Y-%m'),
            end_q_date.strftime('%Y-%m')
        ]
        quarter_avg = sum(route_monthly_sales.get(m, 0) for m in q_months) / 3

        momentum = (quarter_avg / historical_avg) if historical_avg > 0 else 0



        alpha = 0.5
        beta = 0.5
        
        commercial_risk = (alpha * (1 - portfolio_scope)) + (beta * gini_index)

        return {
            'gini_index': round(gini_index * 100, 2),
            'portafolio_scope': round(portfolio_scope * 100, 2),
            'momentum': round(momentum * 100, 2),
            'commercial_risk_index': round(commercial_risk * 100, 2)
        }


    def get_data(self) -> Dict[str, Any]:
        """
        Calculate all metrics all at once.

        returns:
        --------
        dict
            A dictionary with the following keys:
            - timeline_months: list[str]
            - won_customers: list[int]
            - lost_customers: list[int]
            - new_customers: list[int]
            - portfolio_scope: list[float]
        """

        churn_data = self._customers_churn()
        active_data = self._new_and_active_customers()
        volatility_data = self._volatility_and_volume()
        growth_bias_data = self._growth_and_bias()

        return {
            'timeline_months': self.months_timeline,
            'won_customers': churn_data['won_customers'],
            'lost_customers': churn_data['lost_customers'],
            'new_customers': active_data['new_customers'],
            'portfolio_scope': active_data['portfolio_scope'],
            'volatility_scatter': volatility_data['scatter_data'],
            'volatility_thresholds': volatility_data['thresholds'],
            'growth_bias_scatter': growth_bias_data['scatter_data'],
            'growth_bias_thresholds': growth_bias_data['thresholds'],
        }

    def get_data_report(self):
        """
        Get the data for the commercial risk report and returns an Excel file.

        returns:
        --------
        Binary file
            An Excel file with the following sheets:
            - clientes_ganados_perdidos
            - clientes_nuevos_alcance_de_cartera
            - distribucion_y_riesgo_comercial
        """

        pass
        
        