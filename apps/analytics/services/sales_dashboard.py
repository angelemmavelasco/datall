from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any
import calendar

from django.db.models import QuerySet, Q, Sum, Count
from django.db.models.functions import TruncMonth
from django.utils import timezone

from apps.sales.services.sale_transactions import SaleTransactionsService
from apps.sales.services.sale_targets import SaleTargetsService
from apps.human_resources.models import BusinessUnit

if TYPE_CHECKING:
    from apps.core.models import User as UserType

class SalesDashboardServiceError(Exception):
    pass

@dataclass
class SalesDashboardService:
    """
    Service responsible for aggregating and transforming sales dashboard metrics.
    Receives an already filtered transactions queryset (e.g. from SalesDashboardFilter.qs)
    along with the user for security validation.
    """
    user: Any
    transactions_qs: QuerySet | None = None
    targets_qs: QuerySet | None = None
    date_start: date | None = None
    date_end: date | None = None
    cleaned_data: dict[str, Any] | None = None

    _resolved_transactions_qs: QuerySet | None = field(default=None, init=False, repr=False)
    _resolved_targets_qs: QuerySet | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        self._init_dates()

    def _init_dates(self) -> None:
        """
        Normalizes date_start and date_end.
        Defaults to current full month if not specified.
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

        if not self.date_start:
            self.date_start = date(today.year, today.month, 1)
        if not self.date_end:
            _, last_day = calendar.monthrange(today.year, today.month)
            self.date_end = date(today.year, today.month, last_day)

    def _base_qs(self) -> tuple[QuerySet, QuerySet]:
        """
        Returns a tuple of (transactions_qs, targets_qs).
        
        If transactions_qs was passed in (e.g. from DjangoFilter.qs), it is used directly.
        Otherwise, falls back to the default allowed transactions for the user.
        Targets are aligned to the matching date range and user permissions.
        """
        if self._resolved_transactions_qs is not None and self._resolved_targets_qs is not None:
            return self._resolved_transactions_qs, self._resolved_targets_qs

        if self.transactions_qs is not None:
            tx_qs = self.transactions_qs
        else:
            tx_service = SaleTransactionsService(user=self.user)
            tx_qs = tx_service.read_transactions_by_allowed_routes()
            if self.date_start:
                tx_qs = tx_qs.filter(sale_date__gte=self.date_start)
            if self.date_end:
                tx_qs = tx_qs.filter(sale_date__lte=self.date_end)

        if self.targets_qs is not None:
            target_qs = self.targets_qs
        else:
            target_service = SaleTargetsService(user=self.user)
            target_qs = target_service.read_sale_targets()
            if self.date_start:
                target_qs = target_qs.filter(period__gte=self.date_start.replace(day=1))
            if self.date_end:
                target_qs = target_qs.filter(period__lte=self.date_end.replace(day=1))

            if self.cleaned_data:
                #filter by route
                routes = self.cleaned_data.get('route') or self.cleaned_data.get('routes')
                if routes:
                    target_qs = target_qs.filter(route__in=routes)

                #filter by Region 
                regions = self.cleaned_data.get('region') or self.cleaned_data.get('regions')
                if regions:
                    selected_region_ids = set(r.pk if hasattr(r, 'pk') else r for r in regions)
                    all_bu_ids = set(selected_region_ids)
                    current_parents = set(selected_region_ids)
                    while current_parents:
                        child_ids = set(BusinessUnit.objects.filter(parent_id__in=current_parents).values_list('id', flat=True))
                        new_ids = child_ids - all_bu_ids
                        if not new_ids:
                            break
                        all_bu_ids.update(new_ids)
                        current_parents = new_ids
                    target_qs = target_qs.filter(route__business_unit_id__in=all_bu_ids)

                #filter by business_unit
                business_units = self.cleaned_data.get('business_unit') or self.cleaned_data.get('business_units')
                if business_units:
                    bu_ids = [b.pk if hasattr(b, 'pk') else b for b in business_units]
                    target_qs = target_qs.filter(route__business_unit_id__in=bu_ids)

                #filter by product class
                product_classes = self.cleaned_data.get('product_class') or self.cleaned_data.get('product_classes')
                if product_classes:
                    target_qs = target_qs.filter(product_class__in=product_classes)

        self._resolved_transactions_qs = tx_qs
        self._resolved_targets_qs = target_qs

        return self._resolved_transactions_qs, self._resolved_targets_qs

    def get_stats(self) -> dict[str, Any]:
        """
        Calculates top-level KPI metrics aggregated directly in PostgreSQL.
        Returns:
            net_amount: Sum of net_amount
            sale_target: Sum of target_amount
            target_achivement: (net_amount / sale_target) * 100
            diff_amount: net_amount - sale_target
            gross_amount: Sum of gross_amount
            quantity: Sum of quantity
            occupied_positions_count: Distinct count of customer_id
            margin: (profit / net_amount) * 100
        """
        tx_qs, target_qs = self._base_qs()

        tx_agg = tx_qs.aggregate(
            total_net=Sum('net_amount'),
            total_gross=Sum('gross_amount'),
            total_quantity=Sum('quantity'),
            total_profit=Sum('profit'),
            unique_customers=Count('customer_id', distinct=True)
        )

        target_agg = target_qs.aggregate(
            total_target=Sum('target_amount')
        )

        net_amount = float(tx_agg['total_net'] or 0.0)
        gross_amount = float(tx_agg['total_gross'] or 0.0)
        quantity = float(tx_agg['total_quantity'] or 0.0)
        profit = float(tx_agg['total_profit'] or 0.0)
        unique_customers = int(tx_agg['unique_customers'] or 0)

        sale_target = float(target_agg['total_target'] or 0.0)

        target_achievement = round((net_amount / sale_target * 100.0), 2) if sale_target > 0 else 0.0
        diff_amount = round(net_amount - sale_target, 2)
        margin = round((profit / net_amount * 100.0), 2) if net_amount > 0 else 0.0

        return {
            'net_amount': round(net_amount, 2),
            'sale_target': round(sale_target, 2),
            'target_achivement': target_achievement,
            'diff_amount': diff_amount,
            'gross_amount': round(gross_amount, 2),
            'quantity': quantity,
            'occupied_positions_count': unique_customers,
            'margin': margin,
        }

    def get_kpis(self) -> dict[str, Any]:
        """Alias for get_stats"""
        return self.get_stats()

    def get_timeline(self) -> dict[str, list]:
        """
        calculates timeline data aggregated directly in the database (daily or monthly).
        ensures continuous categories without missing gaps (fills missing dates with 0.0).
        """
        tx_qs, target_qs = self._base_qs()

        #total target across the selected quota periods
        target_agg = target_qs.aggregate(total_target=Sum('target_amount'))
        total_target = float(target_agg['total_target'] or 0.0)

        #determine granularity, daily if within same month and year, else monthly
        is_daily = (
            self.date_start.year == self.date_end.year
            and self.date_start.month == self.date_end.month
        )

        categories: list[str] = []
        sales_map: dict[str, float] = {}
        units_map: dict[str, float] = {}

        if is_daily:
            #pre-populate all continuous days in range
            curr_date = self.date_start
            while curr_date <= self.date_end:
                date_key = curr_date.strftime('%Y-%m-%d')
                categories.append(date_key)
                sales_map[date_key] = 0.0
                units_map[date_key] = 0.0
                curr_date += timedelta(days=1)

            #db agg grouped by sale_date (order_by clears default model ordering for correct GROUP BY)
            daily_aggs = (
                tx_qs.order_by('sale_date')
                .values('sale_date')
                .annotate(
                    total_sales=Sum('net_amount'),
                    total_units=Sum('quantity')
                )
            )
            for row in daily_aggs:
                d_key = row['sale_date'].strftime('%Y-%m-%d') if row.get('sale_date') else None
                if d_key and d_key in sales_map:
                    sales_map[d_key] += float(row['total_sales'] or 0.0)
                    units_map[d_key] += float(row['total_units'] or 0.0)

        else:
            #pre-populate all continuous months in range
            curr_date = self.date_start.replace(day=1)
            while curr_date <= self.date_end or (
                curr_date.year == self.date_end.year and curr_date.month == self.date_end.month
            ):
                date_key = curr_date.strftime('%Y-%m')
                categories.append(date_key)
                sales_map[date_key] = 0.0
                units_map[date_key] = 0.0
                if curr_date.month == 12:
                    curr_date = curr_date.replace(year=curr_date.year + 1, month=1)
                else:
                    curr_date = curr_date.replace(month=curr_date.month + 1)

            #db aggregation grouped by month using TruncMonth
            monthly_aggs = (
                tx_qs.annotate(month=TruncMonth('sale_date'))
                .order_by('month')
                .values('month')
                .annotate(
                    total_sales=Sum('net_amount'),
                    total_units=Sum('quantity')
                )
            )
            for row in monthly_aggs:
                if row.get('month'):
                    m_key = row['month'].strftime('%Y-%m')
                    if m_key in sales_map:
                        sales_map[m_key] += float(row['total_sales'] or 0.0)
                        units_map[m_key] += float(row['total_units'] or 0.0)

        # Calculate cumulative metrics for reach and progress
        cumulative_sales = 0.0
        cumulative_sales_list: list[float] = []
        target_achievement_list: list[float] = []

        for c in categories:
            s_val = sales_map[c]
            cumulative_sales += s_val
            cumulative_sales_list.append(round(cumulative_sales, 2))

            if total_target > 0:
                ach = round((cumulative_sales / total_target) * 100.0, 2)
            else:
                ach = 0.0
            target_achievement_list.append(ach)

        return {
            'categories': categories,
            'sales': [round(sales_map[c], 2) for c in categories],
            'units': [round(units_map[c], 2) for c in categories],
            'cumulative_sales': cumulative_sales_list,
            'target_achievement': target_achievement_list,
            'total_target': round(total_target, 2),
        }

    def get_business_unit_chart(self) -> dict[str, list]:
        """
        calculates net sales and targets grouped by the route's business unit (gerencia).
        """
        tx_qs, target_qs = self._base_qs()

        #agg sales by route's business unit
        bu_aggs = (
            tx_qs.order_by('route__business_unit__name')
            .values('route__business_unit_id', 'route__business_unit__name')
            .annotate(total_sales=Sum('net_amount'))
        )

        #agg targets by business unit
        target_map: dict[str, float] = defaultdict(float)
        target_bu_aggs = (
            target_qs.order_by('business_unit_id')
            .values('business_unit_id')
            .annotate(total_target=Sum('target_amount'))
        )
        for row in target_bu_aggs:
            bu_id = row.get('business_unit_id')
            if bu_id:
                target_map[bu_id] += float(row['total_target'] or 0.0)

        bu_data = defaultdict(lambda: {'name': '', 'sales': 0.0, 'targets': 0.0})

        for row in bu_aggs:
            b_id = str(row.get('route__business_unit_id') or 'sin_gerencia')
            b_name = (row.get('route__business_unit__name') or (b_id.upper() if b_id != 'sin_gerencia' else 'Sin Gerencia')).strip().title()
            bu_data[b_id]['name'] = b_name
            bu_data[b_id]['sales'] += float(row['total_sales'] or 0.0)

        for b_id, target_amt in target_map.items():
            if target_amt > 0 and b_id not in bu_data:
                bu_obj = BusinessUnit.objects.filter(id=b_id).first()
                b_name = bu_obj.name.strip().title() if bu_obj else b_id.upper()
                bu_data[b_id]['name'] = b_name

        for b_id, data in bu_data.items():
            target_amt = target_map.get(b_id, 0.0)
            if target_amt == 0.0 and b_id == 'cdmx':
                target_amt = target_map.get('cdmx1', 0.0) + target_map.get('cdmx2', 0.0)
            data['targets'] = target_amt

        data_rows = []
        for b_id, data in bu_data.items():
            if data['sales'] == 0 and data['targets'] == 0:
                continue
            data_rows.append({
                'id': b_id,
                'name': data['name'],
                'sales': round(data['sales'], 2),
                'targets': round(data['targets'], 2),
            })

        data_rows.sort(key=lambda x: x['sales'])

        return {
            'categories': [r['name'] for r in data_rows],
            'sales': [r['sales'] for r in data_rows],
            'targets': [r['targets'] for r in data_rows],
            'target_achievement': [
                round((r['sales'] / r['targets'] * 100.0), 2) if r['targets'] > 0 else 0.0
                for r in data_rows
            ],
        }

    def get_route_table(self) -> list[dict[str, Any]]:
        """
        Calculates sales, targets, difference, reach, and margin by route.
        """
        tx_qs, target_qs = self._base_qs()

        route_data = defaultdict(lambda: {
            'name': '',
            'sale': 0.0,
            'target': 0.0,
            'profit': 0.0
        })

        tx_aggs = (
            tx_qs.order_by('route_id')
            .values('route_id', 'route__name')
            .annotate(
                total_sale=Sum('net_amount'),
                total_profit=Sum('profit')
            )
        )
        for row in tx_aggs:
            r_id = str(row['route_id']) if row.get('route_id') is not None else 'N/A'
            name = (row.get('route__name') or '').strip()
            route_data[r_id]['name'] = name
            route_data[r_id]['sale'] += float(row['total_sale'] or 0.0)
            route_data[r_id]['profit'] += float(row['total_profit'] or 0.0)

        target_aggs = (
            target_qs.order_by('route_id')
            .values('route_id', 'route__name')
            .annotate(total_target=Sum('target_amount'))
        )
        for row in target_aggs:
            r_id = str(row['route_id']) if row.get('route_id') is not None else 'N/A'
            name = (row.get('route__name') or '').strip()
            if not route_data[r_id]['name'] and name:
                route_data[r_id]['name'] = name
            route_data[r_id]['target'] += float(row['total_target'] or 0.0)

        table = []
        for r_id, data in route_data.items():
            diff = data['sale'] - data['target']
            scope = (data['sale'] / data['target'] * 100.0) if data['target'] > 0 else 0.0
            margin = (data['profit'] / data['sale'] * 100.0) if data['sale'] > 0 else 0.0
            table.append({
                'id': r_id,
                'name': data['name'].title() if data['name'] else f'Ruta {r_id}',
                'total_net_sale': round(data['sale'], 2),
                'total_target': round(data['target'], 2),
                'total_difference': round(diff, 2),
                'total_scope': round(scope, 2),
                'total_margin': round(margin, 2)
            })

        table.sort(key=lambda x: x['total_net_sale'], reverse=True)
        return table

    def get_product_class_chart(self) -> dict[str, list]:
        """
        calculates net sales, target, reach, and contribution percentage by product class.
        """
        tx_qs, target_qs = self._base_qs()
        pc_aggs = (
            tx_qs.order_by('product_class__name')
            .values('product_class_id', 'product_class__name')
            .annotate(total_sales=Sum('net_amount'))
        )
        target_aggs = (
            target_qs.order_by('product_class__name')
            .values('product_class_id', 'product_class__name')
            .annotate(total_target=Sum('target_amount'))
        )

        class_data = defaultdict(lambda: {'name': '', 'sales': 0.0, 'targets': 0.0})

        for row in pc_aggs:
            cid = str(row.get('product_class_id') or 'sin_clase')
            name = (row.get('product_class__name') or cid).strip().title()
            class_data[cid]['name'] = name
            class_data[cid]['sales'] += float(row['total_sales'] or 0.0)

        for row in target_aggs:
            cid = str(row.get('product_class_id') or 'sin_clase')
            name = (row.get('product_class__name') or cid).strip().title()
            if not class_data[cid]['name']:
                class_data[cid]['name'] = name
            class_data[cid]['targets'] += float(row['total_target'] or 0.0)

        total_filtered_sales = sum(d['sales'] for d in class_data.values())

        rows = []
        for cid, data in class_data.items():
            if data['sales'] == 0 and data['targets'] == 0:
                continue
            sales = round(data['sales'], 2)
            targets = round(data['targets'], 2)
            scope = round((sales / targets * 100.0), 2) if targets > 0 else 0.0
            contribution = round((sales / total_filtered_sales * 100.0), 2) if total_filtered_sales > 0 else 0.0
            rows.append({
                'id': cid.upper(),
                'name': data['name'],
                'sales': sales,
                'targets': targets,
                'target_achievement': scope,
                'contribution': contribution,
            })

        rows.sort(key=lambda x: x['sales'])
        return {
            'categories': [r['id'] for r in rows],
            'names': [r['name'] for r in rows],
            'sales': [r['sales'] for r in rows],
            'targets': [r['targets'] for r in rows],
            'target_achievement': [r['target_achievement'] for r in rows],
            'contributions': [r['contribution'] for r in rows],
        }

    def get_product_category_chart(self) -> list[dict[str, Any]]:
        """
        Calculates net sales by product category for pie/donut chart.
        """
        tx_qs, _ = self._base_qs()
        cat_aggs = (
            tx_qs.order_by('product_class__product_category__name')
            .values('product_class__product_category__name')
            .annotate(total_sales=Sum('net_amount'))
        )
        rows = []
        for row in cat_aggs:
            name = (row.get('product_class__product_category__name') or 'Sin Categoría').strip()
            rows.append({
                'name': name.title(),
                'value': round(float(row['total_sales'] or 0.0), 2)
            })
        rows.sort(key=lambda x: x['value'], reverse=True)
        return rows

    def get_top_products(self, limit: int = 50) -> list[dict[str, Any]]:
        """
        Calculates top products by net sales.
        """
        tx_qs, _ = self._base_qs()
        prod_aggs = (
            tx_qs.values('product_id', 'product__name')
            .annotate(
                total_units=Sum('quantity'),
                total_net_sale=Sum('net_amount'),
                total_gross_sale=Sum('gross_amount'),
                total_profit=Sum('profit')
            )
            .order_by('-total_net_sale')[:limit]
        )
        table = []
        for row in prod_aggs:
            p_id = str(row.get('product_id') or 'N/A')
            name = (row.get('product__name') or '').strip()
            net_sale = float(row.get('total_net_sale') or 0.0)
            profit = float(row.get('total_profit') or 0.0)
            margin = (profit / net_sale * 100.0) if net_sale > 0 else 0.0
            table.append({
                'id': p_id,
                'name': name.title() if name else f'Producto {p_id}',
                'total_units': round(float(row.get('total_units') or 0.0), 2),
                'total_net_sale': round(net_sale, 2),
                'total_gross_sale': round(float(row.get('total_gross_sale') or 0.0), 2),
                'total_margin': round(margin, 2)
            })
        return table

    def get_top_customers(self, limit: int = 50) -> list[dict[str, Any]]:
        """
        Calculates top customers by net sales.
        """
        tx_qs, _ = self._base_qs()
        cust_aggs = (
            tx_qs.values('customer_id', 'customer__name')
            .annotate(
                total_units=Sum('quantity'),
                total_net_sale=Sum('net_amount'),
                total_gross_sale=Sum('gross_amount'),
                total_profit=Sum('profit')
            )
            .order_by('-total_net_sale')[:limit]
        )
        table = []
        for row in cust_aggs:
            c_id = str(row.get('customer_id') or 'N/A')
            name = (row.get('customer__name') or '').strip()
            net_sale = float(row.get('total_net_sale') or 0.0)
            profit = float(row.get('total_profit') or 0.0)
            margin = (profit / net_sale * 100.0) if net_sale > 0 else 0.0
            table.append({
                'id': c_id,
                'name': name.title() if name else f'Cliente {c_id}',
                'total_net_sale': round(net_sale, 2),
                'total_gross_sale': round(float(row.get('total_gross_sale') or 0.0), 2),
                'total_units': round(float(row.get('total_units') or 0.0), 2),
                'total_margin': round(margin, 2)
            })
        return table