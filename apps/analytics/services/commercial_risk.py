import calendar
import math
import statistics
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from dateutil.relativedelta import relativedelta
from collections import defaultdict
from django.db.models import QuerySet, Sum, Q
from django.utils import timezone

@dataclass
class CommercialRiskService:
    user: Any
    route: Any
    customers_qs: QuerySet
    transactions_qs: QuerySet
    date_start: date | str | None = None
    date_end: date | str | None = None
    cleaned_data: dict[str, Any] | None = None

    today: date = field(init=False)
    route_id: str | None = field(init=False)
    start_q_date: date = field(init=False)
    end_q_date: date = field(init=False)

    def __post_init__(self):
        self._init_dates()
        self._init_route()

    def _init_dates(self) -> None:
        self.today = timezone.localdate()

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

        first_day_curr_month = self.today.replace(day=1)
        default_end = first_day_curr_month - relativedelta(days=1)
        default_start = default_end.replace(day=1) - relativedelta(months=11)

        if not self.date_end:
            self.date_end = default_end
        if not self.date_start:
            self.date_start = default_start

        if self.date_start > self.date_end:
            self.date_start, self.date_end = self.date_end, self.date_start

        self.end_q_date = self.date_end
        self.start_q_date = self.end_q_date.replace(day=1) - relativedelta(months=2)

    def _init_route(self) -> None:
        if hasattr(self.route, 'id'):
            self.route_id = str(self.route.id)
        elif self.route:
            self.route_id = str(self.route)
        else:
            self.route_id = None

    def stats(self) -> dict[str, Any]:
        return CommercialRiskStats(commercial_risk_service=self).stats()

    def _get_timeline_chart(self) -> dict[str, Any]:
        """
        generates timeline chart data for commercial risk evolution evaluated month by month
        using rolling closed quarters (e.g. for Jan 2025: Oct, Nov, Dec 2024; for Feb 2025: Nov, Dec 2024, Jan 2025).
        Returns:
            - timeline_months: ['2025-08', '2025-09', ...]
            - months_labels: ['Ago 2025', 'Sep 2025', ...]
            - commercial_risk_index: [81.64, 80.88, ...]
            - gini: [76.49, 75.18, ...]
            - portfolio_scope_complement: [86.78, 86.57, ...] (Clientes desatendidos)
            - portfolio_scope: [13.22, 13.43, ...] (Alcance de cartera)
        """
        if not self.route_id:
            return {
                'timeline_months': [],
                'months_labels': [],
                'commercial_risk_index': [],
                'gini': [],
                'portfolio_scope_complement': [],
                'portfolio_scope': [],
            }

        curr = self.date_start.replace(day=1)
        end_m = self.date_end.replace(day=1)
        timeline_months = []
        months_labels = []

        month_abbr_es = {
            1: 'Ene', 2: 'Feb', 3: 'Mar', 4: 'Abr', 5: 'May', 6: 'Jun',
            7: 'Jul', 8: 'Ago', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dic'
        }

        while curr <= end_m:
            timeline_months.append(curr.strftime('%Y-%m'))
            months_labels.append(f"{month_abbr_es[curr.month]} {curr.year}")
            curr += relativedelta(months=1)

        if not timeline_months:
            return {
                'timeline_months': [],
                'months_labels': [],
                'commercial_risk_index': [],
                'gini': [],
                'portfolio_scope_complement': [],
                'portfolio_scope': [],
            }

        customers_qs = (
            self.customers_qs
            .filter(assignments__route_id=self.route_id)
            .values('id', 'registration_date')
            .distinct()
        )
        customers_map = {c['id']: c['registration_date'] for c in customers_qs}

        extended_start = self.date_start.replace(day=1) - relativedelta(months=4)
        tx_qs = (
            self.transactions_qs
            .filter(
                route_id=self.route_id,
                sale_date__gte=extended_start,
                sale_date__lte=self.date_end,
                net_amount__gt=0
            )
            .values('sale_date', 'customer_id', 'net_amount')
        )

        monthly_customer_sales = defaultdict(lambda: defaultdict(float))
        for tx in tx_qs:
            m_key = tx['sale_date'].strftime('%Y-%m')
            monthly_customer_sales[m_key][tx['customer_id']] += float(tx['net_amount'])

        gini_list = []
        unattended_list = []
        scope_list = []
        irc_list = []

        for m_str in timeline_months:
            target_date = datetime.strptime(m_str, '%Y-%m').date()
            end_q = target_date.replace(day=1) - relativedelta(days=1)
            q_months = [(end_q.replace(day=1) - relativedelta(months=i)).strftime('%Y-%m') for i in (2, 1, 0)]

            portfolio_cids = [
                cid for cid, reg_date in customers_map.items()
                if reg_date and reg_date <= end_q
            ]
            total_portfolio = len(portfolio_cids)

            quarter_customer_sales = defaultdict(float)
            for qm in q_months:
                for cid, amount in monthly_customer_sales[qm].items():
                    quarter_customer_sales[cid] += amount

            active_count = sum(1 for cid in portfolio_cids if quarter_customer_sales.get(cid, 0.0) > 0.0)

            if total_portfolio > 0:
                scope = active_count / total_portfolio
            else:
                scope = 0.0

            unattended = 1.0 - scope

            sales_arr = sorted([amt for amt in quarter_customer_sales.values() if amt > 0.0])
            n = len(sales_arr)
            cum_sales = sum(sales_arr)

            if n > 0 and cum_sales > 0:
                sum_iy = sum((i + 1) * y for i, y in enumerate(sales_arr))
                gini = (2.0 * sum_iy / (n * cum_sales)) - ((n + 1.0) / n)
                gini = max(min(gini, 1.0), 0.0)
            else:
                gini = 0.0

            irc = (0.5 * gini) + (0.5 * unattended)

            gini_list.append(round(gini * 100.0, 2))
            unattended_list.append(round(unattended * 100.0, 2))
            scope_list.append(round(scope * 100.0, 2))
            irc_list.append(round(irc * 100.0, 2))

        return {
            'timeline_months': timeline_months,
            'months_labels': months_labels,
            'commercial_risk_index': irc_list,
            'gini': gini_list,
            'portfolio_scope_complement': unattended_list,
            'portfolio_scope': scope_list,
        }

    def _get_customer_churn(self) -> dict[str, Any]:
        """
        calculates lost and won customers month by month.
        a customer is 'won' in month M if they purchased in month M but not in M-1.
        a customer is 'lost' in month M if they purchased in month M-1 but not in month M.
        also stores customer IDs for each month to allow interactive navigation.
        returns:
            {
                'months': ['ene', 'feb', ...],
                'lost': [2, 5, ...],
                'won': [4, 1, ...],
                'lost_customer_ids': [['id1', 'id2'], ...],
                'won_customer_ids': [['id3', 'id4'], ...],
            }
        """
        if not self.route_id:
            return {'months': [], 'lost': [], 'won': [], 'lost_customer_ids': [], 'won_customer_ids': []}

        curr = self.date_start.replace(day=1)
        end_m = self.date_end.replace(day=1)
        eval_periods: list[tuple[int, int]] = []
        while curr <= end_m:
            eval_periods.append((curr.year, curr.month))
            curr += relativedelta(months=1)

        if not eval_periods:
            return {'months': [], 'lost': [], 'won': [], 'lost_customer_ids': [], 'won_customer_ids': []}

        first_y, first_m = eval_periods[0]
        baseline_period = (first_y - 1, 12) if first_m == 1 else (first_y, first_m - 1)
        all_periods = [baseline_period] + eval_periods

        start_bound = date(all_periods[0][0], all_periods[0][1], 1)
        _, last_day_end = calendar.monthrange(all_periods[-1][0], all_periods[-1][1])
        end_bound = date(all_periods[-1][0], all_periods[-1][1], last_day_end)

        tx_churn = (
            self.transactions_qs
            .filter(
                route_id=self.route_id,
                sale_date__gte=start_bound,
                sale_date__lte=end_bound,
                net_amount__gt=0
            )
            .order_by()
            .values('sale_date__year', 'sale_date__month', 'customer_id')
            .distinct()
        )

        cust_by_period: dict[tuple[int, int], set[Any]] = defaultdict(set)
        for row in tx_churn:
            y = row['sale_date__year']
            m = row['sale_date__month']
            cid = row['customer_id']
            if cid:
                cust_by_period[(y, m)].add(cid)

        month_names = {
            1: 'Ene', 2: 'Feb', 3: 'Mar', 4: 'Abr', 5: 'May', 6: 'Jun',
            7: 'Jul', 8: 'Ago', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dic'
        }
        has_multiple_years = len(set(y for y, _ in eval_periods)) > 1

        months: list[str] = []
        lost_counts: list[int] = []
        won_counts: list[int] = []
        lost_customer_ids: list[list[str]] = []
        won_customer_ids: list[list[str]] = []

        for i in range(1, len(all_periods)):
            prev_p = all_periods[i - 1]
            curr_p = all_periods[i]

            prev_custs = cust_by_period[prev_p]
            curr_custs = cust_by_period[curr_p]

            lost_set = prev_custs - curr_custs
            won_set = curr_custs - prev_custs

            m_label = f"{month_names[curr_p[1]]} '{str(curr_p[0])[-2:]}" if has_multiple_years else month_names[curr_p[1]]

            months.append(m_label)
            lost_counts.append(len(lost_set))
            won_counts.append(len(won_set))
            lost_customer_ids.append(sorted([str(c) for c in lost_set]))
            won_customer_ids.append(sorted([str(c) for c in won_set]))

        return {
            'months': months,
            'lost': lost_counts,
            'won': won_counts,
            'lost_customer_ids': lost_customer_ids,
            'won_customer_ids': won_customer_ids,
        } 

    def _get_monthly_new_customers(self) -> dict[str, Any]:
        """
        calculates the count of new customers registered in this route month by month.
        returns:
            {
                'months': ["Ago '25", "Sep '25", ...],
                'new_customers': [3, 1, 5, ...],
                'new_customer_ids': [['id1', 'id2'], ...],
            }
        """
        if not self.route_id:
            return {'months': [], 'new_customers': [], 'new_customer_ids': []}

        curr = self.date_start.replace(day=1)
        end_m = self.date_end.replace(day=1)
        eval_periods: list[tuple[int, int]] = []
        month_labels: list[str] = []

        month_names = {
            1: 'Ene', 2: 'Feb', 3: 'Mar', 4: 'Abr', 5: 'May', 6: 'Jun',
            7: 'Jul', 8: 'Ago', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dic'
        }

        while curr <= end_m:
            eval_periods.append((curr.year, curr.month))
            curr += relativedelta(months=1)

        has_multiple_years = len(set(y for y, _ in eval_periods)) > 1
        for y, m in eval_periods:
            m_label = f"{month_names[m]} '{str(y)[-2:]}" if has_multiple_years else month_names[m]
            month_labels.append(m_label)

        customers_qs = (
            self.customers_qs
            .filter(assignments__route_id=self.route_id)
            .values('id', 'registration_date')
            .distinct()
        )

        counts = []
        cids_list = []
        for y, m in eval_periods:
            m_cids = [
                str(c['id']) for c in customers_qs
                if c['registration_date'] and c['registration_date'].year == y and c['registration_date'].month == m
            ]
            counts.append(len(m_cids))
            cids_list.append(m_cids)

        return {
            'months': month_labels,
            'new_customers': counts,
            'new_customer_ids': cids_list,
        }

    def _get_monthly_portafolio_coverage(self) -> dict[str, Any]:
        """
        calculates portfolio coverage percentage (active customers with purchases / cumulative registered portfolio) month by month.
        returns:
            {
                'months': ["Ago '25", "Sep '25", ...],
                'portfolio_coverage': [8.60, 8.33, ...],
                'active_customers': [25, 24, ...],
                'active_customer_ids': [['id1', ...], ...],
                'total_portfolio': [290, 291, ...],
            }
        """
        if not self.route_id:
            return {'months': [], 'portfolio_coverage': [], 'active_customers': [], 'active_customer_ids': [], 'total_portfolio': []}

        curr = self.date_start.replace(day=1)
        end_m = self.date_end.replace(day=1)
        eval_periods: list[tuple[int, int]] = []
        month_labels: list[str] = []

        month_names = {
            1: 'Ene', 2: 'Feb', 3: 'Mar', 4: 'Abr', 5: 'May', 6: 'Jun',
            7: 'Jul', 8: 'Ago', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dic'
        }

        while curr <= end_m:
            eval_periods.append((curr.year, curr.month))
            curr += relativedelta(months=1)

        has_multiple_years = len(set(y for y, _ in eval_periods)) > 1
        for y, m in eval_periods:
            m_label = f"{month_names[m]} '{str(y)[-2:]}" if has_multiple_years else month_names[m]
            month_labels.append(m_label)

        customers_qs = (
            self.customers_qs
            .filter(assignments__route_id=self.route_id)
            .values('id', 'registration_date')
            .distinct()
        )
        cust_reg = {str(c['id']): c['registration_date'] for c in customers_qs if c['registration_date']}

        tx_qs = (
            self.transactions_qs
            .filter(
                route_id=self.route_id,
                sale_date__gte=self.date_start,
                sale_date__lte=self.date_end,
                net_amount__gt=0
            )
            .values('sale_date__year', 'sale_date__month', 'customer_id')
            .distinct()
        )

        active_by_period = defaultdict(set)
        for tx in tx_qs:
            active_by_period[(tx['sale_date__year'], tx['sale_date__month'])].add(str(tx['customer_id']))

        coverage_list = []
        active_counts = []
        active_cids_list = []
        total_port_list = []

        for y, m in eval_periods:
            _, last_day = calendar.monthrange(y, m)
            end_month_date = date(y, m, last_day)

            portfolio_cids = [cid for cid, reg in cust_reg.items() if reg <= end_month_date]
            tot_port = len(portfolio_cids)
            total_port_list.append(tot_port)

            active_in_month = active_by_period.get((y, m), set())
            active_port = [cid for cid in portfolio_cids if cid in active_in_month]
            active_count = len(active_port)

            cov = round((active_count / tot_port * 100.0), 2) if tot_port > 0 else 0.0

            coverage_list.append(cov)
            active_counts.append(active_count)
            active_cids_list.append(active_port)

        return {
            'months': month_labels,
            'portfolio_coverage': coverage_list,
            'active_customers': active_counts,
            'active_customer_ids': active_cids_list,
            'total_portfolio': total_port_list,
        }

    def _get_sale_volume_by_customer(self) -> dict[str, dict[str, Any]]:
        """
        calculates monthly sales volume, active months, median, and momentum per customer
        respecting registration date.
        """
        if not self.route_id:
            return {}

        curr = self.date_start.replace(day=1)
        end_m = self.date_end.replace(day=1)
        timeline_months = []
        while curr <= end_m:
            timeline_months.append(curr.strftime('%Y-%m'))
            curr += relativedelta(months=1)

        month_names = {
            1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril', 5: 'Mayo', 6: 'Junio',
            7: 'Julio', 8: 'Agosto', 9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre'
        }
        last_month_key = timeline_months[-1] if timeline_months else ''
        if last_month_key:
            ly, lm = int(last_month_key[:4]), int(last_month_key[5:7])
            last_month_label = f"{month_names[lm]} '{str(ly)[-2:]}"
        else:
            last_month_label = 'Último mes'

        customers_qs = (
            self.customers_qs
            .filter(assignments__route_id=self.route_id)
            .values('id', 'name', 'registration_date')
            .distinct()
        )
        cust_map = {
            str(c['id']): {
                'name': (c['name'] or f"Cliente {c['id']}").title(),
                'reg_date': c['registration_date']
            }
            for c in customers_qs
        }

        tx_qs = (
            self.transactions_qs
            .filter(
                route_id=self.route_id,
                sale_date__gte=self.date_start,
                sale_date__lte=self.date_end,
                net_amount__gt=0
            )
            .values('sale_date', 'customer_id', 'net_amount')
        )

        monthly_sales = defaultdict(lambda: defaultdict(float))
        for t in tx_qs:
            m = t['sale_date'].strftime('%Y-%m')
            monthly_sales[m][str(t['customer_id'])] += float(t['net_amount'])

        result = {}
        for cid, info in cust_map.items():
            reg_date = info['reg_date']
            reg_month = reg_date.strftime('%Y-%m') if reg_date else timeline_months[0]
            valid_months = [m for m in timeline_months if m >= reg_month]
            n_months = len(valid_months)
            if n_months == 0:
                continue

            sales_data = [monthly_sales[m].get(cid, 0.0) for m in valid_months]
            total_sales = sum(sales_data)
            if total_sales <= 0:
                continue

            mean_sales = total_sales / n_months
            median_sales = statistics.median(sales_data) if sales_data else 0.0

            recent_months = valid_months[-3:] if n_months >= 3 else valid_months
            recent_mean = sum(monthly_sales[m].get(cid, 0.0) for m in recent_months) / len(recent_months)
            momentum = (recent_mean / mean_sales) if mean_sales > 0 else 0.0
            bias = ((mean_sales - median_sales) / abs(mean_sales)) if mean_sales > 0 else 0.0

            if len(recent_months) >= 3:
                m_start = month_names[int(recent_months[0][5:7])][:3]
                m_end = month_names[int(recent_months[-1][5:7])][:3]
                recent_label = f"Venta prom. trimestral ({m_start} - {m_end})"
            elif len(recent_months) == 2:
                m_start = month_names[int(recent_months[0][5:7])][:3]
                m_end = month_names[int(recent_months[-1][5:7])][:3]
                recent_label = f"Venta prom. bimestral ({m_start} - {m_end})"
            else:
                m_single = month_names[int(recent_months[0][5:7])][:3]
                recent_label = f"Venta {m_single}"

            months_with_purchases = sum(1 for s in sales_data if s > 0)
            last_month_sale = float(monthly_sales[last_month_key].get(cid, 0.0)) if last_month_key else 0.0

            result[cid] = {
                'customer_id': cid,
                'customer_name': info['name'],
                'total_sales': total_sales,
                'mean_sales': mean_sales,
                'median_sales': median_sales,
                'recent_mean': recent_mean,
                'recent_label': recent_label,
                'momentum': momentum,
                'bias': bias,
                'valid_months': valid_months,
                'sales_data': sales_data,
                'months_with_purchases': months_with_purchases,
                'last_month_sale': last_month_sale,
                'last_month_label': last_month_label,
            }

        return result

    def _get_cv_by_customer(self) -> dict[str, dict[str, Any]]:
        """
        calculates coefficient of variation (CV = std_dev / mean) for each customer.
        correctly handles customers with 1 month of purchase history.
        """
        volume_data = self._get_sale_volume_by_customer()
        result = {}

        for cid, vinfo in volume_data.items():
            sales_data = vinfo['sales_data']
            n_months = len(sales_data)
            mean_sales = vinfo['mean_sales']

            if n_months <= 1:
                cv = 1.0 if vinfo['months_with_purchases'] == 1 else 0.0
                std_dev = 0.0
                is_single_month = True
            else:
                variance = sum((s - mean_sales)**2 for s in sales_data) / n_months
                std_dev = math.sqrt(variance)
                cv = std_dev / mean_sales if mean_sales > 0 else 0.0
                is_single_month = (vinfo['months_with_purchases'] == 1)

            result[cid] = {
                'customer_id': cid,
                'customer_name': vinfo['customer_name'],
                'cv': cv,
                'std_dev': std_dev,
                'mean_sales': mean_sales,
                'momentum': vinfo['momentum'],
                'bias': vinfo['bias'],
                'total_sales': vinfo['total_sales'],
                'is_single_month': is_single_month,
                'last_month_sale': vinfo['last_month_sale'],
                'last_month_label': vinfo['last_month_label'],
                'recent_mean': vinfo['recent_mean'],
                'recent_label': vinfo['recent_label'],
            }

        return result

    def _get_volatility_and_volume(self) -> dict[str, Any]:
        """
        calculates scatter data, thresholds, and quadrant customer IDs for volatility and volume analysis.
        """
        cv_dict = self._get_cv_by_customer()
        if not cv_dict:
            return {
                'scatter_data': [],
                'thresholds': {'volume': 0.0, 'volatility': 0.0},
                'quadrants': {
                    'low_cv_high_vol': [],
                    'low_cv_low_vol': [],
                    'high_cv_high_vol': [],
                    'high_cv_low_vol': [],
                }
            }

        scatter_data = []
        vol_list = []
        cv_list = []

        for cid, info in cv_dict.items():
            mean_sales = info['mean_sales']
            cv = info['cv']
            momentum = info['momentum']
            bias = info['bias']
            name = info['customer_name']
            is_single = info['is_single_month']
            last_sale = info['last_month_sale']
            last_label = info['last_month_label']
            recent_mean = info['recent_mean']
            recent_label = info['recent_label']

            scatter_data.append([
                round(mean_sales, 2),
                round(cv, 4),
                round(momentum, 4),
                cid,
                name,
                is_single,
                round(bias, 4),
                round(last_sale, 2),
                last_label,
                round(recent_mean, 2),
                recent_label,
            ])
            vol_list.append(mean_sales)
            cv_list.append(cv)

        vol_list.sort()
        cv_list.sort()
        vol_threshold = vol_list[len(vol_list)//2] if vol_list else 0.0
        cv_threshold = cv_list[len(cv_list)//2] if cv_list else 0.0

        low_cv_high_vol_cids = [item[3] for item in scatter_data if item[0] >= vol_threshold and item[1] <= cv_threshold]
        low_cv_low_vol_cids = [item[3] for item in scatter_data if item[0] < vol_threshold and item[1] <= cv_threshold]
        high_cv_high_vol_cids = [item[3] for item in scatter_data if item[0] >= vol_threshold and item[1] > cv_threshold]
        high_cv_low_vol_cids = [item[3] for item in scatter_data if item[0] < vol_threshold and item[1] > cv_threshold]

        return {
            'scatter_data': scatter_data,
            'thresholds': {
                'volume': round(vol_threshold, 2),
                'volatility': round(cv_threshold, 4),
            },
            'quadrants': {
                'low_cv_high_vol': low_cv_high_vol_cids,
                'low_cv_low_vol': low_cv_low_vol_cids,
                'high_cv_high_vol': high_cv_high_vol_cids,
                'high_cv_low_vol': high_cv_low_vol_cids,
            }
        }


@dataclass
class CommercialRiskStats:
    commercial_risk_service: CommercialRiskService

    def _get_target_customers_registered(self) -> list[str]:
        """Returns customer IDs assigned to this route registered on or before end_q_date"""
        service = self.commercial_risk_service
        if not service.route_id:
            return []

        target_qs = (
            service.customers_qs
            .filter(
                assignments__route_id=service.route_id,
                registration_date__lte=service.end_q_date
            )
            .filter(
                Q(assignments__end_date__isnull=True) | Q(assignments__end_date__gte=service.today)
            )
            .values_list('id', flat=True)
            .distinct()
        )
        return list(target_qs)

    def _get_quarter_customer_sales(self) -> dict[str, Decimal]:
        """Returns {customer_id: total_net_amount} for transactions in the closed quarter with net_amount > 0"""
        service = self.commercial_risk_service
        if not service.route_id:
            return {}

        sales_qs = (
            service.transactions_qs
            .filter(
                route_id=service.route_id,
                sale_date__gte=service.start_q_date,
                sale_date__lte=service.end_q_date,
                net_amount__gt=0
            )
            .values('customer_id')
            .annotate(total=Sum('net_amount'))
        )
        return {row['customer_id']: (row['total'] or Decimal('0.00')) for row in sales_qs}

    def _get_gini(self) -> Decimal:
        """
        returns the gini index (0.0 to 100.0) from last closed quarter among purchasing clients.
        Evaluates concentration and dependency on few top clients.
        """
        customer_sales = self._get_quarter_customer_sales()
        sales_list = sorted([float(amt) for amt in customer_sales.values() if amt > 0])
        n = len(sales_list)
        cum_sales = sum(sales_list)

        if n <= 0 or cum_sales <= 0:
            return Decimal('0.00')

        sum_iy = sum((i + 1) * y for i, y in enumerate(sales_list))
        gini_coeff = (2.0 * sum_iy / (n * cum_sales)) - ((n + 1.0) / n)
        gini_pct = max(min(gini_coeff * 100.0, 100.0), 0.0)
        return Decimal(str(round(gini_pct, 2)))

    def _get_portafolio_coverage(self) -> dict[str, Decimal]:
        """
        returns the portfolio coverage from last closed quarter.
        coverage = (customers_with_consumption / registered_customers) * 100
        """
        registered_cids = set(self._get_target_customers_registered())
        total_registered = len(registered_cids)

        customer_sales = self._get_quarter_customer_sales()
        active_customers = sum(1 for cid, amt in customer_sales.items() if amt > 0)

        if total_registered > 0:
            coverage_pct = (Decimal(active_customers) / Decimal(total_registered)) * Decimal('100.00')
        else:
            coverage_pct = Decimal('0.00')

        return {
            'registered_customers': Decimal(str(total_registered)),
            'customers_with_consumption': Decimal(str(active_customers)),
            'coverage': Decimal(str(round(coverage_pct, 2))),
        }

    def _get_momentum(self) -> dict[str, Decimal]:
        """
        returns the momentum (growth factor) from last closed quarter compared to historical average.
        momentum = ((quarter_avg / history_avg) - 1) * 100
        """
        service = self.commercial_risk_service
        if not service.route_id:
            return {
                'momentum': Decimal('0.00'),
                'history': Decimal('0.00'),
                'current': Decimal('0.00'),
            }

        tx_historical = (
            service.transactions_qs
            .filter(
                route_id=service.route_id,
                sale_date__gte=service.date_start,
                sale_date__lte=service.date_end
            )
            .values('sale_date', 'net_amount')
        )

        monthly_sales = defaultdict(Decimal)
        for tx in tx_historical:
            m_key = tx['sale_date'].strftime('%Y-%m')
            monthly_sales[m_key] += (tx['net_amount'] or Decimal('0.00'))

        total_months = len(monthly_sales)
        history_avg = (sum(monthly_sales.values()) / total_months) if total_months > 0 else Decimal('0.00')

        q_months = [
            (service.start_q_date + relativedelta(months=i)).strftime('%Y-%m')
            for i in range(3)
        ]
        quarter_total = sum(monthly_sales.get(m, Decimal('0.00')) for m in q_months)
        quarter_avg = quarter_total / Decimal('3.0')

        if history_avg > Decimal('0.00'):
            momentum_pct = ((quarter_avg / history_avg) - Decimal('1.00')) * Decimal('100.00')
        else:
            momentum_pct = Decimal('0.00')

        return {
            'momentum': Decimal(str(round(momentum_pct, 2))),
            'history': Decimal(str(round(history_avg, 2))),
            'current': Decimal(str(round(quarter_avg, 2))),
        }

    def _get_commercial_risk_index(self, gini: Decimal, coverage: Decimal) -> Decimal:
        """
        calculates commercial risk index as a weighted composite of:
        - structural concentration (Gini index: higher = more risk)
        - portfolio inactivity / non-coverage ((100 - Coverage): higher = more risk)
        formula: 0.5 * (100 - coverage) + 0.5 * gini
        """
        inactivity = Decimal('100.00') - coverage
        risk = (Decimal('0.5') * inactivity) + (Decimal('0.5') * gini)
        bounded_risk = max(min(risk, Decimal('100.00')), Decimal('0.00'))
        return Decimal(str(round(bounded_risk, 2)))

    def stats(self) -> dict[str, Any]:
        gini = self._get_gini()
        portafolio_data = self._get_portafolio_coverage()
        coverage = portafolio_data['coverage']
        momentum_data = self._get_momentum()
        momentum = momentum_data['momentum']
        risk_index = self._get_commercial_risk_index(gini=gini, coverage=coverage)

        churn_data = self.commercial_risk_service._get_customer_churn()
        won_customers = sum(churn_data.get('won', []))
        lost_customers = sum(churn_data.get('lost', []))

        service = self.commercial_risk_service
        new_customers_count = (
            service.customers_qs
            .filter(
                assignments__route_id=service.route_id,
                registration_date__gte=service.date_start,
                registration_date__lte=service.date_end
            )
            .distinct()
            .count()
        ) if service.route_id else 0

        cov_data = self.commercial_risk_service._get_monthly_portafolio_coverage()
        cov_list = cov_data.get('portfolio_coverage', [])
        if cov_list:
            history_cov_avg = sum(cov_list) / len(cov_list)
            last_month_cov = cov_list[-1]
            if history_cov_avg > 0:
                coverage_momentum = Decimal(str(round(((last_month_cov / history_cov_avg) - 1.0) * 100.0, 2)))
            else:
                coverage_momentum = Decimal('0.00')
        else:
            coverage_momentum = Decimal('0.00')

        vol_data = self.commercial_risk_service._get_volatility_and_volume()
        quadrants = vol_data.get('quadrants', {})
        low_cv_high_vol = quadrants.get('low_cv_high_vol', [])
        low_cv_low_vol = quadrants.get('low_cv_low_vol', [])
        high_cv_high_vol = quadrants.get('high_cv_high_vol', [])
        high_cv_low_vol = quadrants.get('high_cv_low_vol', [])

        return {
            'gini_index': gini,
            'portfolio_coverage': coverage,
            'registered_customers': portafolio_data['registered_customers'],
            'customers_with_consumption': portafolio_data['customers_with_consumption'],
            'sales_momentum': momentum,
            'history_avg': momentum_data['history'],
            'quarter_avg': momentum_data['current'],
            'commercial_risk_index': risk_index,
            'won_customers': won_customers,
            'lost_customers': lost_customers,
            'new_customers': new_customers_count,
            'coverage_momentum': coverage_momentum,
            'low_cv_high_vol': len(low_cv_high_vol),
            'low_cv_low_vol': len(low_cv_low_vol),
            'high_cv_high_vol': len(high_cv_high_vol),
            'high_cv_low_vol': len(high_cv_low_vol),
            'low_cv_high_vol_ids': low_cv_high_vol,
            'low_cv_low_vol_ids': low_cv_low_vol,
            'high_cv_high_vol_ids': high_cv_high_vol,
            'high_cv_low_vol_ids': high_cv_low_vol,
            'volatility_thresholds': vol_data.get('thresholds', {}),
            'start_q_date': self.commercial_risk_service.start_q_date,
            'end_q_date': self.commercial_risk_service.end_q_date,
        }


@dataclass
class CommercialRiskExports:
    commercial_risk_service: CommercialRiskService