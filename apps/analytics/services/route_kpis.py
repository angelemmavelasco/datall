from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any
import calendar
from collections import defaultdict
from django.db.models import QuerySet, Sum, Q, Count
from django.utils import timezone

from apps.products.models import ProductClass
from apps.sales.services.sale_targets import SaleTargetsService

@dataclass
class RouteKpisService:
    user: Any
    route: Any
    customers_qs: QuerySet
    transactions_qs: QuerySet
    ars_qs: QuerySet
    targets_qs: QuerySet | None = None
    date_start: date | str | None = None
    date_end: date | str | None = None
    cleaned_data: dict[str, Any] | None = None

    today: date = field(init=False)
    current_year: int = field(init=False)
    route_id: str | None = field(init=False)

    def __post_init__(self):
        self._init_dates()

        if hasattr(self.route, 'id'):
            self.route_id = str(self.route.id)
        elif self.route:
            self.route_id = str(self.route)
        else:
            self.route_id = None

    def _init_dates(self) -> None:
        """
        normalizes date_start and date_end with dynamic parsing.
        defaults to current full month if not provided.
        """
        self.today = timezone.localdate()
        self.current_year = self.today.year

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

        if not self.date_start:
            self.date_start = date(self.today.year, self.today.month, 1)
        if not self.date_end:
            _, last_day = calendar.monthrange(self.today.year, self.today.month)
            self.date_end = date(self.today.year, self.today.month, last_day)

        if self.date_start > self.date_end:
            self.date_start, self.date_end = self.date_end, self.date_start

    def _get_achievement_by_month(self) -> dict[str, list]:
        """
        calculates monthly sales, targets, and percentage achievement for the route.
        if the selected date range is within a single month, displays months from January of the current year up to the current date/month.
        otherwise, displays only the months comprised within the selected range.
        returns {
            'months': ['Ene', 'Feb', ...],
            'sales': [123.45, ...],
            'targets': [150.00, ...],
            'scopes': [82.30, ...]
        }
        """
        if not self.route_id:
            return {'months': [], 'sales': [], 'targets': [], 'scopes': []}

        #dynamic verification check if range is within a single month
        month_span = (self.date_end.year - self.date_start.year) * 12 + (self.date_end.month - self.date_start.month)
        is_less_than_a_month = (month_span == 0)

        target_periods: list[tuple[int, int]] = []

        if is_less_than_a_month:
            for m in range(1, self.today.month + 1):
                target_periods.append((self.current_year, m))
        else:
            curr = self.date_start.replace(day=1)
            end_m = self.date_end.replace(day=1)
            while curr <= end_m:
                target_periods.append((curr.year, curr.month))
                if curr.month == 12:
                    curr = curr.replace(year=curr.year + 1, month=1)
                else:
                    curr = curr.replace(month=curr.month + 1)

        if not target_periods:
            return {'months': [], 'sales': [], 'targets': [], 'scopes': []}

        start_bound = date(target_periods[0][0], target_periods[0][1], 1)
        _, last_day_end = calendar.monthrange(target_periods[-1][0], target_periods[-1][1])
        end_bound = date(target_periods[-1][0], target_periods[-1][1], last_day_end)

        sales_agg = (
            self.transactions_qs
            .filter(
                route_id=self.route_id,
                sale_date__gte=start_bound,
                sale_date__lte=end_bound
            )
            .order_by()
            .values('sale_date__year', 'sale_date__month')
            .annotate(total_sales=Sum('net_amount'))
        )
        sales_map = {
            (row['sale_date__year'], row['sale_date__month']): float(row['total_sales'] or 0.0)
            for row in sales_agg
        }

        if self.targets_qs is not None:
            t_qs = self.targets_qs
        else:
            targets_service = SaleTargetsService(user=self.user)
            t_qs = targets_service.read_sale_targets()

        targets_agg = (
            t_qs
            .filter(
                route_id=self.route_id,
                period__gte=start_bound,
                period__lte=end_bound
            )
            .order_by()
            .values('period__year', 'period__month')
            .annotate(total_target=Sum('target_amount'))
        )
        targets_map = {
            (row['period__year'], row['period__month']): float(row['total_target'] or 0.0)
            for row in targets_agg
        }

        month_names = {
            1: 'Ene', 2: 'Feb', 3: 'Mar', 4: 'Abr', 5: 'May', 6: 'Jun',
            7: 'Jul', 8: 'Ago', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dic'
        }

        has_multiple_years = len(set(y for y, _ in target_periods)) > 1

        months: list[str] = []
        sales: list[float] = []
        targets: list[float] = []
        scopes: list[float] = []

        for y, m in target_periods:
            m_label = f"{month_names[m]} '{str(y)[-2:]}" if has_multiple_years else month_names[m]
            s_val = round(sales_map.get((y, m), 0.0), 2)
            t_val = round(targets_map.get((y, m), 0.0), 2)
            scope_val = round((s_val / t_val * 100.0), 2) if t_val > 0 else 0.0

            months.append(m_label)
            sales.append(s_val)
            targets.append(t_val)
            scopes.append(scope_val)

        return {
            'months': months,
            'sales': sales,
            'targets': targets,
            'scopes': scopes,
        }

    def _get_sale_by_product_class(self) -> dict[str, Any]:
        """
        calculates net sales, target amount, difference, and scope per product class for the route in the selected date range.
        delegates the ordering of the classes to the service (ordered by highest sales and targets).
        returns:
            {
                'classes': [
                    {'id': 'dmd', 'name': 'Diamond', 'net_sales': 1000.0, 'target': 800.0, 'difference': 200.0, 'scope': 125.0},
                    ...
                ],
                'total': {
                    'name': 'Total',
                    'net_sales': 5000.0,
                    'target': 4000.0,
                    'difference': 1000.0,
                    'scope': 125.0,
                }
            }
        """
        if not self.route_id:
            return {'classes': [], 'total': {}}

        sales_agg = (
            self.transactions_qs
            .filter(
                route_id=self.route_id,
                sale_date__gte=self.date_start,
                sale_date__lte=self.date_end
            )
            .order_by()
            .values('product_class_id')
            .annotate(total_sales=Sum('net_amount'))
        )
        sales_map = {
            (row['product_class_id'] or 'otr').lower(): float(row['total_sales'] or 0.0)
            for row in sales_agg
        }

        if self.targets_qs is not None:
            t_qs = self.targets_qs
        else:
            targets_service = SaleTargetsService(user=self.user)
            t_qs = targets_service.read_sale_targets()

        targets_agg = (
            t_qs
            .filter(
                route_id=self.route_id,
                period__gte=self.date_start.replace(day=1),
                period__lte=self.date_end
            )
            .order_by()
            .values('product_class_id')
            .annotate(total_target=Sum('target_amount'))
        )
        targets_map = {
            (row['product_class_id'] or 'otr').lower(): float(row['total_target'] or 0.0)
            for row in targets_agg
        }

        classes_qs = ProductClass.objects.all()
        class_names_map = {
            pc.id.lower(): (pc.name or pc.id).strip().title()
            for pc in classes_qs
        }

        all_class_ids = list(class_names_map.keys())
        for cid in list(sales_map.keys()) + list(targets_map.keys()):
            if cid not in class_names_map:
                class_names_map[cid] = cid.title()
                all_class_ids.append(cid)

        class_items: list[dict[str, Any]] = []
        total_sales = 0.0
        total_target = 0.0

        for cid in all_class_ids:
            s_val = round(sales_map.get(cid, 0.0), 2)
            t_val = round(targets_map.get(cid, 0.0), 2)
            diff_val = round(s_val - t_val, 2)
            scope_val = round((s_val / t_val * 100.0), 2) if t_val > 0 else 0.0

            total_sales += s_val
            total_target += t_val

            class_items.append({
                'id': cid,
                'name': class_names_map.get(cid, cid.title()),
                'net_sales': s_val,
                'target': t_val,
                'difference': diff_val,
                'scope': scope_val,
            })

        class_items.sort(key=lambda x: x['name'].lower())

        total_difference = round(total_sales - total_target, 2)
        total_scope = round((total_sales / total_target * 100.0), 2) if total_target > 0 else 0.0

        total_data = {
            'name': 'Total',
            'net_sales': round(total_sales, 2),
            'target': round(total_target, 2),
            'difference': total_difference,
            'scope': total_scope,
        }

        return {
            'classes': class_items,
            'total': total_data,
        }

    def _get_collections(self) -> dict[str, Any]:
        """
        aggregates credit limits and accounts receivable breakdown for the route.
        """
        if not self.route_id:
            return {
                'total_credit': 0.0,
                'credit_usage': 0.0,
                'total_balance': 0.0,
                'current_balance': 0.0,
                'overdue_balance': 0.0,
                'days_1_15': 0.0,
                'days_16_30': 0.0,
                'days_31_60': 0.0,
                'days_60_over': 0.0,
            }

        route_customers = self.customers_qs.filter(
            assignments__route_id=self.route_id,
            assignments__end_date__isnull=True
        ).distinct()

        total_credit = float(route_customers.aggregate(total=Sum('credit_limit'))['total'] or 0.0)

        ar_base = self.ars_qs.filter(customer__in=route_customers)
        if self.date_end:
            ar_base = ar_base.filter(Q(issue_date__lte=self.date_end) | Q(issue_date__isnull=True))

        ar_agg = ar_base.aggregate(
            tot_bal=Sum('total_balance'),
            curr_bal=Sum('current_balance'),
            b15=Sum('balance_15'),
            b30=Sum('balance_30'),
            b60=Sum('balance_60'),
            p_due=Sum('past_due'),
        )

        total_balance = float(ar_agg['tot_bal'] or 0.0)
        current_balance = float(ar_agg['curr_bal'] or 0.0)
        days_1_15 = float(ar_agg['b15'] or 0.0)
        days_16_30 = float(ar_agg['b30'] or 0.0)
        days_31_60 = float(ar_agg['b60'] or 0.0)
        days_60_over = float(ar_agg['p_due'] or 0.0)

        overdue_balance = days_1_15 + days_16_30 + days_31_60 + days_60_over
        credit_usage = round((total_balance / total_credit * 100.0), 2) if total_credit > 0 else 0.0

        return {
            'total_credit': round(total_credit, 2),
            'credit_usage': credit_usage,
            'total_balance': round(total_balance, 2),
            'current_balance': round(current_balance, 2),
            'overdue_balance': round(overdue_balance, 2),
            'days_1_15': round(days_1_15, 2),
            'days_16_30': round(days_16_30, 2),
            'days_31_60': round(days_31_60, 2),
            'days_60_over': round(days_60_over, 2),
        }

    def _get_sale_by_customer_category(self) -> list[dict[str, Any]]:
        """
        calculates sales and customer counts grouped by customer category/type for the selected route in the date range.
        returns:
            [
                {
                    'id': 'VET',
                    'name': 'Veterinaria',
                    'value': 12345.67,
                    'percent': 45.2,
                    'customer_count': 15,
                    'customer_ids': ['C001', 'C002', ...]
                },
                ...
            ]
        """
        if not self.route_id:
            return []

        tx_categories = (
            self.transactions_qs
            .filter(
                route_id=self.route_id,
                sale_date__gte=self.date_start,
                sale_date__lte=self.date_end
            )
            .order_by()
            .values('customer__customer_type_id', 'customer__customer_type__name', 'customer_id', 'net_amount')
        )

        type_sales: dict[str, float] = defaultdict(float)
        type_names: dict[str, str] = {}
        type_customers: dict[str, set[str]] = defaultdict(set)
        total_sales = 0.0

        for row in tx_categories:
            tid = row['customer__customer_type_id'] or 'sin_tipo'
            tname = (row['customer__customer_type__name'] or 'Sin tipo').title()
            type_names[tid] = tname

            amt = float(row['net_amount'] or 0.0)
            type_sales[tid] += amt
            total_sales += amt

            cid = row['customer_id']
            if cid:
                type_customers[tid].add(str(cid))

        category_items: list[dict[str, Any]] = []
        for tid, s_val in type_sales.items():
            s_val = round(s_val, 2)
            cust_ids = sorted(list(type_customers[tid]))
            pct = round((s_val / total_sales * 100.0), 2) if total_sales > 0 else 0.0

            category_items.append({
                'id': tid,
                'name': type_names.get(tid, tid.title()),
                'value': s_val,
                'percent': pct,
                'customer_count': len(cust_ids),
                'customer_ids': cust_ids,
            })

        category_items.sort(key=lambda x: x['value'], reverse=True)
        return category_items

    def _get_customer_churn(self) -> dict[str, Any]:
        """
        calculates lost and won customers month by month.
        a customer is 'won' in month M if they purchased in month M but not in M-1.
        a customer is 'lost' in month M if they purchased in month M-1 but not in month M.
        also stores customer IDs for each month to allow interactive navigation.
        returns:
            {
                'months': ['Ene', 'Feb', ...],
                'lost': [2, 5, ...],
                'won': [4, 1, ...],
                'lost_customer_ids': [['id1', 'id2'], ...],
                'won_customer_ids': [['id3', 'id4'], ...],
            }
        """
        if not self.route_id:
            return {'months': [], 'lost': [], 'won': [], 'lost_customer_ids': [], 'won_customer_ids': []}

        month_span = (self.date_end.year - self.date_start.year) * 12 + (self.date_end.month - self.date_start.month)
        is_less_than_a_month = (month_span == 0)

        eval_periods: list[tuple[int, int]] = []

        if is_less_than_a_month:
            for m in range(1, self.today.month + 1):
                eval_periods.append((self.current_year, m))
        else:
            curr = self.date_start.replace(day=1)
            end_m = self.date_end.replace(day=1)
            while curr <= end_m:
                eval_periods.append((curr.year, curr.month))
                if curr.month == 12:
                    curr = curr.replace(year=curr.year + 1, month=1)
                else:
                    curr = curr.replace(month=curr.month + 1)

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
                sale_date__lte=end_bound
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

    def _get_photo_url(self) -> str | None:
        if not self.route_id:
            return None
        try:
            from apps.sales.models import RouteAssignment
            assignment = (
                RouteAssignment.objects
                .filter(route_id=self.route_id, date_end__isnull=True)
                .select_related('employee__user')
                .first()
            )
            if assignment and assignment.employee and assignment.employee.user:
                user_obj = assignment.employee.user
                if getattr(user_obj, 'photo', None):
                    return user_obj.photo.url
        except Exception:
            pass
        return None

    def read_route_kpis(self) -> dict[str, Any]:
        sale_by_product_class = self._get_sale_by_product_class()
        collections = self._get_collections()
        photo_url = self._get_photo_url()

        data = {
            'photo_url': photo_url,
            'achievement_by_month': self._get_achievement_by_month(),
            'sale_by_product_class': sale_by_product_class,
            'product_class_performance': sale_by_product_class,
            'collections': collections,
            'sale_by_customer_category': self._get_sale_by_customer_category(),
            'customer_churn': self._get_customer_churn(),
            'total_credit': collections['total_credit'],
            'credit_usage': collections['credit_usage'],
            'total_balance': collections['total_balance'],
            'current_balance': collections['current_balance'],
            'overdue_balance': collections['overdue_balance'],
            'days_1_15': collections['days_1_15'],
            'days_16_30': collections['days_16_30'],
            'days_31_60': collections['days_31_60'],
            'days_60_over': collections['days_60_over'],
        }
        print(f'service read_route_kpis executed successfully by {self.user} for route {self.route}')
        return data

    def stats(self) -> dict[str, Any]:
        """
        calculates summary metrics (BANs) for route sales performance, collections, and customer portfolio.
        """
        if not self.route_id:
            return {
                'net_amount': 0.0,
                'sale_target': 0.0,
                'target_achivement': 0.0,
                'target_achievement': 0.0,
                'diff_amount': 0.0,
                'total_balance': 0.0,
                'current_balance': 0.0,
                'overdue_balance': 0.0,
                'overdue_amount': 0.0,
                'accounts_receivable': 0.0,
                'registered_customers': 0,
                'new_customers': 0,
                'customers_with_purchases': 0,
                'portfolio_coverage': 0.0,
            }

        sales_agg = (
            self.transactions_qs
            .filter(
                route_id=self.route_id,
                sale_date__gte=self.date_start,
                sale_date__lte=self.date_end
            )
            .aggregate(total=Sum('net_amount'))
        )
        net_amount = float(sales_agg['total'] or 0.0)

        if self.targets_qs is not None:
            t_qs = self.targets_qs
        else:
            t_qs = SaleTargetsService(user=self.user).read_sale_targets()

        target_agg = (
            t_qs
            .filter(
                route_id=self.route_id,
                period__gte=self.date_start.replace(day=1),
                period__lte=self.date_end
            )
            .aggregate(total=Sum('target_amount'))
        )
        sale_target = float(target_agg['total'] or 0.0)
        target_achievement = round((net_amount / sale_target * 100.0), 2) if sale_target > 0 else 0.0
        diff_amount = round(net_amount - sale_target, 2)

        collections = self._get_collections()
        total_bal = collections['total_balance']
        curr_bal = collections['current_balance']
        overdue_amt = collections['overdue_balance']

        route_customers = self.customers_qs.filter(
            assignments__route_id=self.route_id,
            assignments__end_date__isnull=True
        ).distinct()

        ar_base = self.ars_qs.filter(customer__in=route_customers)
        
        if self.date_end:
            ar_base = ar_base.filter(Q(issue_date__lte=self.date_end) | Q(issue_date__isnull=True))

        accounts_with_debt = (
            ar_base
            .filter(total_balance__gt=0)
            .values('customer_id')
            .distinct()
            .count()
        )

        if self.date_end:
            active_customers = route_customers.filter(registration_date__lte=self.date_end)
        else:
            active_customers = route_customers

        registered_count = active_customers.count()

        new_count = route_customers.filter(
            registration_date__gte=self.date_start,
            registration_date__lte=self.date_end
        ).count()

        purchased_count = (
            self.transactions_qs
            .filter(
                route_id=self.route_id,
                sale_date__gte=self.date_start,
                sale_date__lte=self.date_end
            )
            .values('customer_id')
            .distinct()
            .count()
        )

        portfolio_coverage = round((purchased_count / registered_count * 100.0), 2) if registered_count > 0 else 0.0

        stats_data = {
            'net_amount': round(net_amount, 2),
            'sale_target': round(sale_target, 2),
            'target_achivement': target_achievement,
            'target_achievement': target_achievement,
            'diff_amount': diff_amount,

            'total_balance': round(total_bal, 2),
            'current_balance': round(curr_bal, 2),
            'overdue_balance': round(overdue_amt, 2),
            'overdue_amount': round(overdue_amt, 2),
            'accounts_receivable': accounts_with_debt,

            'registered_customers': registered_count,
            'new_customers': new_count,
            'customers_with_purchases': purchased_count,
            'portfolio_coverage': portfolio_coverage,
        }

        print(f'service stats executed successfully by {self.user} for route {self.route}')
        return stats_data