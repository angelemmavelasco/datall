from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from collections import defaultdict
from django.db.models import QuerySet, Sum, Count, Q
from django.utils import timezone

from apps.products.models import ProductClass


@dataclass
class TargetAchievementService:
    user: Any
    targets_qs: QuerySet
    transactions_qs: QuerySet
    customers_qs: QuerySet
    routes_qs: QuerySet
    date_start: date | str | None = None
    date_end: date | str | None = None
    cleaned_data: dict[str, Any] | None = None

    today: date = field(init=False)
    date_start_dt: date = field(init=False)
    date_end_dt: date = field(init=False)
    total_b_days: int = field(init=False)
    elapsed_b_days: int = field(init=False)

    VALID_CORE_CLASSES: tuple[str, ...] = (
        'diamond',
        'diamond naturals',
        'care',
        'taste of the wild',
        'msd',
        'vetoquinol',
        'zoetis'
    )

    def __post_init__(self):
        self._init_dates()
        self.total_b_days, self.elapsed_b_days = self._get_business_days(self.date_start_dt, self.date_end_dt)

    def _init_dates(self) -> None:
        """
        normalize the dates from request, if not provided by default will be the current month
        """
        self.today = timezone.localdate()
        first_day_curr_month = self.today.replace(day=1)
        if self.today.month == 12:
            last_day_curr_month = date(self.today.year, 12, 31)
        else:
            last_day_curr_month = date(self.today.year, self.today.month + 1, 1) - timedelta(days=1)

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

        parsed_start = _parse_val(self.date_start)
        parsed_end = _parse_val(self.date_end)

        self.date_start_dt = parsed_start or first_day_curr_month
        self.date_end_dt = parsed_end or last_day_curr_month
        self.date_start = self.date_start_dt
        self.date_end = self.date_end_dt

    def _get_business_days(self, date_start_dt: date, date_end_dt: date) -> tuple[int, int]:
        """
        calculate total business days (monday to friday) of the range and business days elapsed until yesterday/today.
        """
        if not date_start_dt or not date_end_dt or date_start_dt > date_end_dt:
            return 1, 1

        total_days = 0
        curr = date_start_dt
        while curr <= date_end_dt:
            if curr.weekday() < 5:  # Monday to Friday
                total_days += 1
            curr += timedelta(days=1)

        yesterday = self.today - timedelta(days=1)
        end_elapsed = min(yesterday, date_end_dt)

        elapsed_days = 0
        curr = date_start_dt
        while curr <= end_elapsed:
            if curr.weekday() < 5:
                elapsed_days += 1
            curr += timedelta(days=1)

        total_safe = max(1, total_days)
        elapsed_safe = max(1, elapsed_days)
        return total_safe, elapsed_safe

    def _get_display_product_classes(self) -> list[str]:
        """
        normalize product class names to show in columns
        """
        db_classes = list(
            ProductClass.objects.all()
            .values_list('name', flat=True)
            .order_by('name')
        )
        normalized_db = [c.strip().lower() for c in db_classes if c and c.strip()]
        
        ordered_list = []
        for vc in self.VALID_CORE_CLASSES:
            ordered_list.append(vc)
            
        for c in ('country value', 'nutriforce'):
            if c not in ordered_list:
                ordered_list.append(c)

        for c in normalized_db:
            if c not in ordered_list and c != 'otros':
                ordered_list.append(c)

        if 'otros' not in ordered_list:
            ordered_list.append('otros')

        return ordered_list

    def _get_customer_metrics_by_route(self) -> dict[str, dict[str, Any]]:
        """
        calculate registered customers, new customers in the period and active customers with purchases by route.
        """
        today = self.today
        base_assignments = self.customers_qs.filter(
            Q(assignments__end_date__isnull=True) | Q(assignments__end_date__gte=today)
        )

        customer_qs = base_assignments
        if self.date_end_dt:
            customer_qs = customer_qs.filter(registration_date__lte=self.date_end_dt)

        customers_per_route = customer_qs.order_by().values('assignments__route_id').annotate(
            registered=Count('id', distinct=True)
        )

        new_customers_qs = base_assignments.filter(
            registration_date__gte=self.date_start_dt,
            registration_date__lte=self.date_end_dt
        )
        new_customers_per_route = new_customers_qs.order_by().values('assignments__route_id').annotate(
            nuevos=Count('id', distinct=True)
        )

        active_tx = self.transactions_qs.filter(
            sale_date__gte=self.date_start_dt,
            sale_date__lte=self.date_end_dt
        )
        active_customers_qs = active_tx.order_by().values('route_id').annotate(
            active=Count('customer_id', distinct=True)
        )

        route_customers_dict = defaultdict(lambda: {'registered': 0, 'new': 0, 'active': 0, 'portfolio_scope': 0.0})
        for row in customers_per_route:
            rid = str(row['assignments__route_id']) if row['assignments__route_id'] is not None else 'sn'
            route_customers_dict[rid]['registered'] = row['registered'] or 0

        for row in new_customers_per_route:
            rid = str(row['assignments__route_id']) if row['assignments__route_id'] is not None else 'sn'
            route_customers_dict[rid]['new'] = row['nuevos'] or 0

        for row in active_customers_qs:
            rid = str(row['route_id']) if row['route_id'] is not None else 'sn'
            route_customers_dict[rid]['active'] = row['active'] or 0

        for rid, cdict in route_customers_dict.items():
            reg = cdict['registered']
            act = cdict['active']
            cdict['portfolio_scope'] = round((act / reg * 100.0), 2) if reg > 0 else 0.00

        return route_customers_dict

    def _get_product_class_prf_by_route(self) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, str], list[str]]:
        """
        calculate quotas, sales, difference, scope and projection by route and by product class.
        the target's assigned business unit dictates where the route appears.
        if a route has no targets in the period, it appears in its base business unit only if is_active is true.
        """
        display_classes = self._get_display_product_classes()

        target_qs = self.targets_qs.filter(
            period__gte=self.date_start_dt,
            period__lte=self.date_end_dt
        )

        tx_qs = self.transactions_qs.filter(
            sale_date__gte=self.date_start_dt,
            sale_date__lte=self.date_end_dt
        )

        route_targets = target_qs.order_by().values(
            'route_id',
            'route__name',
            'route__is_active',
            'route__business_unit_id',
            'route__business_unit__name',
            'business_unit_id',
            'business_unit__name',
            'product_class__name'
        ).annotate(
            total_target=Sum('target_amount')
        )

        route_sales = tx_qs.order_by().values(
            'route_id',
            'product_class__name'
        ).annotate(
            total_sale=Sum('net_amount')
        )

        def _empty_class_dict():
            return {
                'target': Decimal('0.00'),
                'net_amount': Decimal('0.00'),
                'difference': Decimal('0.00'),
                'scope': Decimal('0.00'),
                'scope_forecast': Decimal('0.00')
            }

        routes_raw_dict: dict[tuple[str, str], dict[str, Any]] = {}
        business_unit_names: dict[str, str] = {}
        routes_with_targets: set[str] = set()
        route_assigned_bus: dict[str, set[str]] = defaultdict(set)

        #process targets grouped by route and target business_unit
        for row in route_targets:
            rid = str(row['route_id']) if row['route_id'] is not None else 'sn'
            target_amount = row['total_target'] or Decimal('0.00')

            buid = str(row['business_unit_id'] or row['route__business_unit_id'] or 'general')
            buname = row['business_unit__name'] or row['route__business_unit__name'] or 'General'
            business_unit_names[buid] = buname

            cname = (row['product_class__name'] or 'otros').strip().lower()
            if cname not in display_classes:
                cname = 'otros'

            key = (rid, buid)
            if key not in routes_raw_dict:
                routes_raw_dict[key] = {
                    'route_id': rid,
                    'route_name': row['route__name'] or rid,
                    'business_unit_id': buid,
                    'classes': defaultdict(_empty_class_dict)
                }

            routes_raw_dict[key]['classes'][cname]['target'] += target_amount
            if target_amount > 0:
                routes_with_targets.add(rid)
                route_assigned_bus[rid].add(buid)

        #process allowed routes without targets (fallback to base business_unit only if is_active is True)
        for r in self.routes_qs:
            rid = str(r.id)
            if rid not in routes_with_targets:
                if getattr(r, 'is_active', True):
                    base_buid = str(r.business_unit_id) if r.business_unit_id is not None else 'general'
                    base_buname = r.business_unit.name if r.business_unit else 'General'
                    business_unit_names[base_buid] = base_buname

                    key = (rid, base_buid)
                    if key not in routes_raw_dict:
                        routes_raw_dict[key] = {
                            'route_id': rid,
                            'route_name': r.name or rid,
                            'business_unit_id': base_buid,
                            'classes': defaultdict(_empty_class_dict)
                        }
                    route_assigned_bus[rid].add(base_buid)

        #map sales transactions to the corresponding (route_id, business_unit_id) entries
        for row in route_sales:
            rid = str(row['route_id']) if row['route_id'] is not None else 'sn'
            sale_amount = row['total_sale'] or Decimal('0.00')

            cname = (row['product_class__name'] or 'otros').strip().lower()
            if cname not in display_classes:
                cname = 'otros'

            # If route has established (rid, buid) entries, apply sales to them
            assigned_bus = route_assigned_bus.get(rid, set())
            for buid in assigned_bus:
                key = (rid, buid)
                if key in routes_raw_dict:
                    routes_raw_dict[key]['classes'][cname]['net_amount'] += sale_amount

        #calculate details by route
        customer_metrics = self._get_customer_metrics_by_route()
        routes_processed: dict[tuple[str, str], dict[str, Any]] = {}

        for (rid, buid), rdata in routes_raw_dict.items():
            c_info = customer_metrics.get(rid, {'registered': 0, 'new': 0, 'active': 0, 'portfolio_scope': 0.0})
            reg = c_info['registered']
            act = c_info['active']
            new = c_info['new']
            port_scope = c_info['portfolio_scope']

            r_target_total = Decimal('0.00')
            r_net_total = Decimal('0.00')
            completed_families = 0
            classes_breakdown = []

            for cname in display_classes:
                cdict = rdata['classes'][cname]
                target = cdict['target']
                net = cdict['net_amount']
                diff = target - net
                cdict['difference'] = diff

                if target > 0:
                    scope = (net / target) * Decimal('100.00')
                else:
                    scope = Decimal('0.00')
                cdict['scope'] = scope

                forecast = (net / Decimal(self.elapsed_b_days)) * Decimal(self.total_b_days)
                if target > 0:
                    scope_forecast = (forecast / target) * Decimal('100.00')
                else:
                    scope_forecast = Decimal('0.00')
                cdict['scope_forecast'] = scope_forecast

                if cname in self.VALID_CORE_CLASSES:
                    if target > 0 and net >= target:
                        completed_families += 1

                r_target_total += target
                r_net_total += net

                classes_breakdown.append({
                    'product_class_name': cname,
                    'target': target,
                    'net_amount': net,
                    'difference': diff,
                    'scope': scope,
                    'scope_forecast': scope_forecast,
                })

            diff_total = r_target_total - r_net_total
            if r_target_total > 0:
                scope_total = (r_net_total / r_target_total) * Decimal('100.00')
            else:
                scope_total = Decimal('0.00')

            proyeccion_r = (r_net_total / Decimal(self.elapsed_b_days)) * Decimal(self.total_b_days)
            if r_target_total > 0:
                scope_forecast_total = (proyeccion_r / r_target_total) * Decimal('100.00')
            else:
                scope_forecast_total = Decimal('0.00')

            routes_processed[(rid, buid)] = {
                'route_id': rid,
                'route_name': rdata['route_name'],
                'business_unit_id': buid,
                'registered_customers': reg,
                'active_customers': act,
                'portfolio_scope': port_scope,
                'new_customers': new,
                'completed_product_classes': completed_families,
                'target': r_target_total,
                'net_amount': r_net_total,
                'difference': diff_total,
                'scope': scope_total,
                'scope_forecast': scope_forecast_total,
                'classes_dict': rdata['classes'],
                'route_product_classes_breakdown': classes_breakdown,
                'rank_sale': 0,
                'rank_scope': 0,
            }

        return routes_processed, business_unit_names, display_classes

    def _get_product_class_prf_by_business_unit(self) -> list[dict[str, Any]]:
        """
        aggregate results by business unit and rank routes by net sales and scope
        """
        routes_processed, business_unit_names, display_classes = self._get_product_class_prf_by_route()

        def _empty_class_dict():
            return {
                'target': Decimal('0.00'),
                'net_amount': Decimal('0.00'),
                'difference': Decimal('0.00'),
                'scope': Decimal('0.00'),
                'scope_forecast': Decimal('0.00')
            }

        bu_summaries = defaultdict(lambda: {
            'business_unit_id': '',
            'business_unit_name': '',
            'registered_customers': 0,
            'active_customers': 0,
            'portfolio_scope': 0.0,
            'new_customers': 0,
            'completed_product_classes': 0,
            'target': Decimal('0.00'),
            'net_amount': Decimal('0.00'),
            'difference': Decimal('0.00'),
            'scope': Decimal('0.00'),
            'scope_forecast': Decimal('0.00'),
            'classes': defaultdict(_empty_class_dict),
            'routes_data': []
        })

        for (rid, buid), rdata in routes_processed.items():
            buid = rdata['business_unit_id']
            bu_sum = bu_summaries[buid]
            bu_sum['business_unit_id'] = buid
            bu_sum['business_unit_name'] = business_unit_names.get(buid, buid).title()

            bu_sum['registered_customers'] += rdata['registered_customers']
            bu_sum['active_customers'] += rdata['active_customers']
            bu_sum['new_customers'] += rdata['new_customers']
            bu_sum['target'] += rdata['target']
            bu_sum['net_amount'] += rdata['net_amount']

            for cname in display_classes:
                cdict = rdata['classes_dict'][cname]
                wdict = bu_sum['classes'][cname]
                wdict['target'] += cdict['target']
                wdict['net_amount'] += cdict['net_amount']
                wdict['difference'] += cdict['difference']

            bu_sum['routes_data'].append(rdata)

        # Consolidate totals and rankings for each business unit
        final_bu_list = []
        for buid, bu_sum in bu_summaries.items():
            reg = bu_sum['registered_customers']
            act = bu_sum['active_customers']
            bu_sum['portfolio_scope'] = round((act / reg * 100.0), 2) if reg > 0 else 0.00

            bu_comp_fams = 0
            bu_classes_breakdown = []

            for cname in display_classes:
                wdict = bu_sum['classes'][cname]
                t = wdict['target']
                n = wdict['net_amount']
                diff = t - n
                wdict['difference'] = diff

                if t > 0:
                    wdict['scope'] = (n / t) * Decimal('100.00')
                else:
                    wdict['scope'] = Decimal('0.00')

                p = (n / Decimal(self.elapsed_b_days)) * Decimal(self.total_b_days)
                if t > 0:
                    wdict['scope_forecast'] = (p / t) * Decimal('100.00')
                else:
                    wdict['scope_forecast'] = Decimal('0.00')

                if cname in self.VALID_CORE_CLASSES:
                    if t > 0 and n >= t:
                        bu_comp_fams += 1

                bu_classes_breakdown.append({
                    'product_class_name': cname,
                    'target': t,
                    'net_amount': n,
                    'difference': diff,
                    'scope': wdict['scope'],
                    'scope_forecast': wdict['scope_forecast']
                })

            bu_sum['completed_product_classes'] = bu_comp_fams

            t_total = bu_sum['target']
            n_total = bu_sum['net_amount']
            bu_sum['difference'] = t_total - n_total
            if t_total > 0:
                bu_sum['scope'] = (n_total / t_total) * Decimal('100.00')
            else:
                bu_sum['scope'] = Decimal('0.00')

            p_total = (n_total / Decimal(self.elapsed_b_days)) * Decimal(self.total_b_days)
            if t_total > 0:
                bu_sum['scope_forecast'] = (p_total / t_total) * Decimal('100.00')
            else:
                bu_sum['scope_forecast'] = Decimal('0.00')

            # calculate internal rankings of routes by sale and by scope
            routes = bu_sum['routes_data']
            routes_by_scope = sorted(routes, key=lambda x: x['scope'], reverse=True)
            routes_by_sale = sorted(routes, key=lambda x: x['net_amount'], reverse=True)

            for rank, r in enumerate(routes_by_scope, start=1):
                r['rank_scope'] = rank
            for rank, r in enumerate(routes_by_sale, start=1):
                r['rank_sale'] = rank

            # sort routes by id
            bu_sum['routes_data'].sort(key=lambda x: int(x['route_id']) if str(x['route_id']).isdigit() else str(x['route_id']))

            final_bu_list.append({
                'total_business_unit_data': {
                    'business_unit_id': buid,
                    'business_unit_name': bu_sum['business_unit_name'],
                    'registered_customers': bu_sum['registered_customers'],
                    'active_customers': bu_sum['active_customers'],
                    'portfolio_scope': bu_sum['portfolio_scope'],
                    'new_customers': bu_sum['new_customers'],
                    'completed_product_classes': bu_sum['completed_product_classes'],
                    'target': bu_sum['target'],
                    'net_amount': bu_sum['net_amount'],
                    'difference': bu_sum['difference'],
                    'scope': bu_sum['scope'],
                    'scope_forecast': bu_sum['scope_forecast'],
                    'business_unit_product_classes_breakdown': bu_classes_breakdown,
                },
                'routes_data': bu_sum['routes_data'],
                'display_classes': display_classes,
            })

        final_bu_list.sort(key=lambda x: x['total_business_unit_data']['business_unit_name'])
        return final_bu_list

    def get_target_achievement_data(self) -> list[dict[str, Any]]:
        """
        Método orquestador principal que coordina el cálculo
        y entrega la estructura consolidada para la vista y templates.
        """
        return self._get_product_class_prf_by_business_unit()