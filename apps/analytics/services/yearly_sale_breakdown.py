import csv
import io
from dataclasses import dataclass, field
from typing import Any
from collections import defaultdict
from django.db.models import Max, Min, QuerySet, Sum

from apps.customers.models import Customer, CustomerAssignment
from apps.human_resources.models import BusinessUnit
from apps.products.models import Product, ProductClass
from apps.sales.models import Route


@dataclass
class YearlySaleBreakdownService:
    queryset: QuerySet
    dimension: str = 'customer_productclass_product'
    user: Any | None = None
    cleaned_data: dict[str, Any] | None = None

    dimension_config: dict[str, Any] = field(init=False)
    sorted_years: list[int] = field(default_factory=list, init=False)

    DIMENSION_CONFIG = {
        'customer_productclass_product': {
            'label': 'Cliente → Clase de producto → Producto',
            'perspective': 'customers',
            'depth': 3,
            'l1_id': 'customer_id',
            'l1_model': Customer,
            'l1_label': 'Cliente',
            'l2_id': 'product_class_id',
            'l2_model': ProductClass,
            'l2_label': 'Clase de Producto',
            'l3_id': 'product_id',
            'l3_model': Product,
            'l3_label': 'Producto',
        },
        'productclass_customer_product': {
            'label': 'Clase de producto → Cliente → Producto',
            'perspective': 'customers',
            'depth': 3,
            'l1_id': 'product_class_id',
            'l1_model': ProductClass,
            'l1_label': 'Clase de Producto',
            'l2_id': 'customer_id',
            'l2_model': Customer,
            'l2_label': 'Cliente',
            'l3_id': 'product_id',
            'l3_model': Product,
            'l3_label': 'Producto',
        },
        'productclass_product': {
            'label': 'Clase de producto → Producto',
            'perspective': 'routes',
            'depth': 2,
            'l1_id': 'product_class_id',
            'l1_model': ProductClass,
            'l1_label': 'Clase de Producto',
            'l2_id': 'product_id',
            'l2_model': Product,
            'l2_label': 'Producto',
        },
        'management_productclass_product': {
            'label': 'Gerencia → Clase de producto → Producto',
            'perspective': 'routes',
            'depth': 3,
            'l1_id': 'route__business_unit_id',
            'l1_model': BusinessUnit,
            'l1_label': 'Gerencia',
            'l2_id': 'product_class_id',
            'l2_model': ProductClass,
            'l2_label': 'Clase de Producto',
            'l3_id': 'product_id',
            'l3_model': Product,
            'l3_label': 'Producto',
        },
        'management_route_productclass_product': {
            'label': 'Gerencia → Ruta → Clase de producto → Producto',
            'perspective': 'routes',
            'depth': 4,
            'l1_id': 'route__business_unit_id',
            'l1_model': BusinessUnit,
            'l1_label': 'Gerencia',
            'l2_id': 'route_id',
            'l2_model': Route,
            'l2_label': 'Ruta',
            'l3_id': 'product_class_id',
            'l3_model': ProductClass,
            'l3_label': 'Clase de Producto',
            'l4_id': 'product_id',
            'l4_model': Product,
            'l4_label': 'Producto',
        },
        'route_productclass_product': {
            'label': 'Ruta → Clase de producto → Producto',
            'perspective': 'routes',
            'depth': 3,
            'l1_id': 'route_id',
            'l1_model': Route,
            'l1_label': 'Ruta',
            'l2_id': 'product_class_id',
            'l2_model': ProductClass,
            'l2_label': 'Clase de Producto',
            'l3_id': 'product_id',
            'l3_model': Product,
            'l3_label': 'Producto',
        },
        'product_customer': {
            'label': 'Producto → Cliente',
            'perspective': 'customers',
            'depth': 2,
            'l1_id': 'product_id',
            'l1_model': Product,
            'l1_label': 'Producto',
            'l2_id': 'customer_id',
            'l2_model': Customer,
            'l2_label': 'Cliente',
        },
        'product_management': {
            'label': 'Producto → Gerencia',
            'perspective': 'routes',
            'depth': 2,
            'l1_id': 'product_id',
            'l1_model': Product,
            'l1_label': 'Producto',
            'l2_id': 'route__business_unit_id',
            'l2_model': BusinessUnit,
            'l2_label': 'Gerencia',
        },
        'product_route': {
            'label': 'Producto → Ruta',
            'perspective': 'routes',
            'depth': 2,
            'l1_id': 'product_id',
            'l1_model': Product,
            'l1_label': 'Producto',
            'l2_id': 'route_id',
            'l2_model': Route,
            'l2_label': 'Ruta',
        },
    }

    def __post_init__(self):
        self.queryset = self.queryset.order_by()
        if self.dimension not in self.DIMENSION_CONFIG:
            self.dimension = 'customer_productclass_product'
        self.dimension_config = self.DIMENSION_CONFIG[self.dimension]
        self.sorted_years = self._extract_sorted_years()

    @classmethod
    def get_perspective(cls, dimension: str) -> str:
        config = cls.DIMENSION_CONFIG.get(
            dimension, cls.DIMENSION_CONFIG['customer_productclass_product']
        )
        return config.get('perspective', 'customers')

    @property
    def l1_id_field(self) -> str:
        return self.dimension_config['l1_id']

    def _extract_sorted_years(self) -> list[int]:
        dates = self.queryset.aggregate(
            min_date=Min('sale_date'),
            max_date=Max('sale_date'),
        )
        min_date, max_date = dates.get('min_date'), dates.get('max_date')
        if not min_date or not max_date:
            return []
        return list(range(min_date.year, max_date.year + 1))

    def _init_annual_totals(self) -> dict[int, dict[str, float]]:
        return {y: {'net': 0.0, 'profit': 0.0} for y in self.sorted_years}

    def _add_annual_totals(
        self, target: dict[int, dict[str, float]], source: dict[int, dict[str, float]]
    ) -> None:
        for y in self.sorted_years:
            target[y]['net'] += source[y]['net']
            target[y]['profit'] += source[y]['profit']

    def _flatten_annual_totals(
        self, totals_dict: dict[int, dict[str, float]]
    ) -> list[dict[str, Any]]:
        result = []
        prev_net = None

        for y in self.sorted_years:
            net = totals_dict[y]['net']
            profit = totals_dict[y]['profit']

            margin = (profit / net * 100.0) if net > 0 else 0.0
            if prev_net is not None and prev_net > 0:
                growth = (net - prev_net) / prev_net * 100.0
            else:
                growth = 0.0

            #precomputed qualitative evaluation for margins
            if margin >= 43:
                margin_label = 'Excelente'
                margin_class = 'text-emerald-600'
            elif margin >= 40:
                margin_label = 'Óptimo'
                margin_class = 'text-emerald-500'
            elif margin >= 37:
                margin_label = 'Regular'
                margin_class = 'text-yellow-500'
            elif margin >= 35:
                margin_label = 'Malo'
                margin_class = 'text-red-500'
            else:
                margin_label = 'Muy malo'
                margin_class = 'text-red-500'

            #precomputed classes for growth badges
            if growth > 0:
                growth_badge_class = 'border border-emerald-500 text-emerald-500 bg-emerald-500/10'
            elif growth < 0:
                growth_badge_class = 'border border-red-500 text-red-500 bg-red-500/10'
            else:
                growth_badge_class = 'border border-border text-muted bg-page'

            result.append(
                {
                    'year': y,
                    'net': round(net, 2),
                    'profit': round(profit, 2),
                    'margin': round(margin, 2),
                    'growth': round(growth, 2),
                    'margin_label': margin_label,
                    'margin_class': margin_class,
                    'growth_badge_class': growth_badge_class,
                }
            )
            prev_net = net

        return result

    def get_level_1_queryset(self) -> QuerySet:
        """returns queryset of distinct level 1 ids ordered by overall total net sales"""
        l1_id = self.l1_id_field

        return (
            self.queryset.values(l1_id)
            .annotate(total_overall=Sum('net_amount'))
            .filter(total_overall__gt=0)
            .order_by('-total_overall')
        )

    def get_level_1_items(self, top_l1_ids: list[Any]) -> list[dict[str, Any]]:
        """
        fetches and returns level 1 items with their annual totals for the initial page load
        """
        if not top_l1_ids:
            return []

        l1_id = self.l1_id_field
        l1_model = self.dimension_config['l1_model']
        depth = self.dimension_config['depth']

        data_list = (
            self.queryset
            .filter(**{f'{l1_id}__in': top_l1_ids})
            .values(l1_id, 'sale_date__year')
            .annotate(
                total_net=Sum('net_amount'),
                total_profit=Sum('profit'),
            )
            .order_by()
        )

        l1_names = dict(
            l1_model.objects.filter(id__in=top_l1_ids).values_list('id', 'name')
        )

        totals_map: dict[Any, dict[int, dict[str, float]]] = {
            cid: self._init_annual_totals() for cid in top_l1_ids
        }

        for row in data_list:
            k1_id = row.get(l1_id)
            y = row.get('sale_date__year')
            net = float(row.get('total_net') or 0.0)
            profit = float(row.get('total_profit') or 0.0)

            if y in self.sorted_years and k1_id in totals_map:
                totals_map[k1_id][y]['net'] += net
                totals_map[k1_id][y]['profit'] += profit

        # preserve pagination order from top_l1_ids
        result = []
        is_route = 'route' in l1_id and l1_model == Route
        is_customer = 'customer' in l1_id and l1_model == Customer
        is_product = 'product' in l1_id and l1_model == Product
        is_class = l1_model == ProductClass
        is_management = l1_model == BusinessUnit

        for k1_id in top_l1_ids:
            name = l1_names.get(k1_id) or 'Sin registro'
            node_id = f"n1_{k1_id}"
            result.append({
                'id': k1_id,
                'name': name,
                'is_route': is_route,
                'is_customer': is_customer,
                'is_product': is_product,
                'is_class': is_class,
                'is_management': is_management,
                'level': 1,
                'next_level': 2,
                'depth': depth,
                'has_children': depth > 1,
                'node_id': node_id,
                'l1_id': k1_id,
                'totals': self._flatten_annual_totals(totals_map[k1_id]),
            })

        return result

    def get_level_children(self, target_level: int, parent_filters: dict[str, Any]) -> list[dict[str, Any]]:
        """
        fetches and returns child items for a given level and parent filter criteria
        """
        depth = self.dimension_config['depth']
        if target_level > depth:
            return []

        target_id_field = self.dimension_config[f'l{target_level}_id']
        target_model = self.dimension_config[f'l{target_level}_model']

        # build filter criteria for transactions from parent identifiers
        tx_filters = {}
        for lvl in range(1, target_level):
            parent_val = parent_filters.get(f'l{lvl}_id')
            if parent_val is not None and str(parent_val).strip() != '' and str(parent_val) != 'otros':
                field_name = self.dimension_config[f'l{lvl}_id']
                tx_filters[field_name] = parent_val

        data_list = (
            self.queryset
            .filter(**tx_filters)
            .values(target_id_field, 'sale_date__year')
            .annotate(
                total_net=Sum('net_amount'),
                total_profit=Sum('profit'),
            )
            .order_by()
        )

        # aggregate into totals per child
        child_totals: dict[Any, dict[int, dict[str, float]]] = defaultdict(self._init_annual_totals)
        child_net_sum: dict[Any, float] = defaultdict(float)

        for row in data_list:
            c_id = row.get(target_id_field)
            if c_id is None:
                continue
            y = row.get('sale_date__year')
            net = float(row.get('total_net') or 0.0)
            profit = float(row.get('total_profit') or 0.0)

            if y in self.sorted_years:
                child_totals[c_id][y]['net'] += net
                child_totals[c_id][y]['profit'] += profit
                child_net_sum[c_id] += net

        # sort children by sales descending
        sorted_children = sorted(child_net_sum.items(), key=lambda x: x[1], reverse=True)

        # limit by level
        if target_level == 2:
            limit = 100 if depth >= 3 else 50
        elif target_level == 3:
            limit = 50 if depth >= 4 else 50
        else:
            limit = 25

        top_pairs = sorted_children[:limit]
        other_pairs = sorted_children[limit:]

        top_ids = [c_id for c_id, _ in top_pairs]
        target_names = dict(
            target_model.objects.filter(id__in=top_ids).values_list('id', 'name')
        )

        is_route = 'route' in target_id_field and target_model == Route
        is_customer = 'customer' in target_id_field and target_model == Customer
        is_product = 'product' in target_id_field and target_model == Product
        is_class = target_model == ProductClass
        is_management = target_model == BusinessUnit

        parent_node_id = parent_filters.get('parent_node_id', '')

        def _build_ancestor_classes(p_node_id: str) -> str:
            if not p_node_id:
                return ''
            parts = p_node_id.split('_')
            classes = []
            for i in range(2, len(parts) + 1):
                prefix = '_'.join(parts[:i])
                classes.append(f'child-{prefix}')
            return ' '.join(classes)

        ancestor_classes = _build_ancestor_classes(parent_node_id)
        result = []

        for c_id, _ in top_pairs:
            name = target_names.get(c_id) or 'Sin registro'
            node_id = f"{parent_node_id}_{c_id}" if parent_node_id else f"n{target_level}_{c_id}"

            item_data = {
                'id': c_id,
                'name': name,
                'is_route': is_route,
                'is_customer': is_customer,
                'is_product': is_product,
                'is_class': is_class,
                'is_management': is_management,
                'level': target_level,
                'next_level': target_level + 1,
                'depth': depth,
                'has_children': target_level < depth,
                'node_id': node_id,
                'parent_node_id': parent_node_id,
                'ancestor_classes': ancestor_classes,
                'l1_id': parent_filters.get('l1_id'),
                'totals': self._flatten_annual_totals(child_totals[c_id]),
            }
            if target_level >= 2:
                item_data['l2_id'] = c_id if target_level == 2 else parent_filters.get('l2_id')
            if target_level >= 3:
                item_data['l3_id'] = c_id if target_level == 3 else parent_filters.get('l3_id')

            result.append(item_data)

        # add aggregated 'otros' row if threshold was exceeded
        if other_pairs:
            other_totals = self._init_annual_totals()
            for o_id, _ in other_pairs:
                self._add_annual_totals(other_totals, child_totals[o_id])

            label_otros = (
                'OTROS PRODUCTOS'
                if 'product' in target_id_field
                else 'OTROS REGISTROS'
            )
            node_id = f"{parent_node_id}_otros" if parent_node_id else f"n{target_level}_otros"
            result.append({
                'id': 'otros',
                'name': label_otros,
                'is_route': False,
                'is_customer': False,
                'is_product': is_product,
                'is_class': is_class,
                'is_management': is_management,
                'level': target_level,
                'next_level': target_level + 1,
                'depth': depth,
                'has_children': False,
                'node_id': node_id,
                'parent_node_id': parent_node_id,
                'ancestor_classes': ancestor_classes,
                'totals': self._flatten_annual_totals(other_totals),
            })

        return result

    def get_pivot_data(self, top_l1_ids: list[Any]) -> dict[str, Any]:
        if not top_l1_ids:
            return {}

        depth = self.dimension_config.get('depth', 3)
        l1_id = self.dimension_config['l1_id']
        l2_id = self.dimension_config['l2_id']

        if depth == 4:
            l3_id = self.dimension_config['l3_id']
            l4_id = self.dimension_config['l4_id']
            group_fields = [l1_id, l2_id, l3_id, l4_id, 'sale_date__year']
        elif depth == 3:
            l3_id = self.dimension_config['l3_id']
            l4_id = None
            group_fields = [l1_id, l2_id, l3_id, 'sale_date__year']
        else:
            l3_id = None
            l4_id = None
            group_fields = [l1_id, l2_id, 'sale_date__year']

        data_list = list(
            self.queryset.filter(**{f'{l1_id}__in': top_l1_ids})
            .values(*group_fields)
            .annotate(
                total_net=Sum('net_amount'),
                total_profit=Sum('profit'),
            )
            .order_by()
        )

        l1_model = self.dimension_config['l1_model']
        l2_model = self.dimension_config['l2_model']

        l1_names = dict(
            l1_model.objects.filter(id__in=top_l1_ids).values_list('id', 'name')
        )

        l2_ids = list(set(r[l2_id] for r in data_list if r[l2_id] is not None))
        l2_names = dict(
            l2_model.objects.filter(id__in=l2_ids).values_list('id', 'name')
        )

        if depth >= 3 and l3_id:
            l3_model = self.dimension_config['l3_model']
            l3_ids = list(set(r[l3_id] for r in data_list if r[l3_id] is not None))
            l3_names = dict(
                l3_model.objects.filter(id__in=l3_ids).values_list('id', 'name')
            )
        else:
            l3_names = {}

        if depth >= 4 and l4_id:
            l4_model = self.dimension_config['l4_model']
            l4_ids = list(set(r[l4_id] for r in data_list if r[l4_id] is not None))
            l4_names = dict(
                l4_model.objects.filter(id__in=l4_ids).values_list('id', 'name')
            )
        else:
            l4_names = {}

        raw_pivot: dict[Any, Any] = {}

        if depth == 4:
            for row in data_list:
                k1_id = row.get(l1_id)
                k2_id = row.get(l2_id)
                k3_id = row.get(l3_id)
                k4_id = row.get(l4_id)

                y = row.get('sale_date__year')
                net = float(row.get('total_net') or 0.0)
                profit = float(row.get('total_profit') or 0.0)

                if y not in self.sorted_years:
                    continue

                if k1_id not in raw_pivot:
                    raw_pivot[k1_id] = {
                        'id': k1_id,
                        'name': l1_names.get(k1_id) or 'Sin registro',
                        't_o': 0.0,
                        'totals': self._init_annual_totals(),
                        'children': {},
                    }
                raw_pivot[k1_id]['t_o'] += net
                raw_pivot[k1_id]['totals'][y]['net'] += net
                raw_pivot[k1_id]['totals'][y]['profit'] += profit

                l1_children = raw_pivot[k1_id]['children']
                if k2_id not in l1_children:
                    l1_children[k2_id] = {
                        'id': k2_id,
                        'name': l2_names.get(k2_id) or 'Sin registro',
                        't_o': 0.0,
                        'totals': self._init_annual_totals(),
                        'children': {},
                    }
                l1_children[k2_id]['t_o'] += net
                l1_children[k2_id]['totals'][y]['net'] += net
                l1_children[k2_id]['totals'][y]['profit'] += profit

                l2_children = l1_children[k2_id]['children']
                if k3_id not in l2_children:
                    l2_children[k3_id] = {
                        'id': k3_id,
                        'name': l3_names.get(k3_id) or 'Sin registro',
                        't_o': 0.0,
                        'totals': self._init_annual_totals(),
                        'children': {},
                    }
                l2_children[k3_id]['t_o'] += net
                l2_children[k3_id]['totals'][y]['net'] += net
                l2_children[k3_id]['totals'][y]['profit'] += profit

                l3_children = l2_children[k3_id]['children']
                if k4_id not in l3_children:
                    l3_children[k4_id] = {
                        'id': k4_id,
                        'name': l4_names.get(k4_id) or 'Sin registro',
                        't_o': 0.0,
                        'totals': self._init_annual_totals(),
                    }
                l3_children[k4_id]['t_o'] += net
                l3_children[k4_id]['totals'][y]['net'] += net
                l3_children[k4_id]['totals'][y]['profit'] += profit

            final_pivot: dict[str, Any] = {}
            TOP_L2 = 100
            TOP_L3 = 50
            TOP_L4 = 25

            sorted_l1 = sorted(
                raw_pivot.items(), key=lambda x: x[1]['t_o'], reverse=True
            )
            for k1_id, l1_data in sorted_l1:
                l1_entry = {
                    'id': l1_data['id'],
                    'name': l1_data['name'],
                    'totals': self._flatten_annual_totals(l1_data['totals']),
                    'children': {},
                }

                sorted_l2 = sorted(
                    l1_data['children'].items(),
                    key=lambda x: x[1]['t_o'],
                    reverse=True,
                )
                for k2_id, l2_data in sorted_l2[:TOP_L2]:
                    l2_entry = {
                        'id': l2_data['id'],
                        'name': l2_data['name'],
                        'totals': self._flatten_annual_totals(l2_data['totals']),
                        'children': {},
                    }

                    sorted_l3 = sorted(
                        l2_data['children'].items(),
                        key=lambda x: x[1]['t_o'],
                        reverse=True,
                    )
                    for k3_id, l3_data in sorted_l3[:TOP_L3]:
                        l3_entry = {
                            'id': l3_data['id'],
                            'name': l3_data['name'],
                            'totals': self._flatten_annual_totals(l3_data['totals']),
                            'children': {},
                        }

                        sorted_l4 = sorted(
                            l3_data['children'].items(),
                            key=lambda x: x[1]['t_o'],
                            reverse=True,
                        )
                        for k4_id, l4_data in sorted_l4[:TOP_L4]:
                            l3_entry['children'][f'{k4_id}'] = {
                                'id': l4_data['id'],
                                'name': l4_data['name'],
                                'totals': self._flatten_annual_totals(l4_data['totals']),
                            }

                        otros_l4 = sorted_l4[TOP_L4:]
                        if otros_l4:
                            o_totals = self._init_annual_totals()
                            for _, ol4_data in otros_l4:
                                self._add_annual_totals(o_totals, ol4_data['totals'])
                            l4_label_otros = (
                                'OTROS PRODUCTOS'
                                if 'product' in self.dimension_config['l4_id']
                                else 'OTROS REGISTROS'
                            )
                            l3_entry['children']['otros_l4'] = {
                                'id': 'otros',
                                'name': l4_label_otros,
                                'totals': self._flatten_annual_totals(o_totals),
                            }

                        l2_entry['children'][f'{k3_id}'] = l3_entry

                    l1_entry['children'][f'{k2_id}'] = l2_entry

                final_pivot[f'{k1_id}'] = l1_entry

            return final_pivot

        elif depth == 3:
            for row in data_list:
                k1_id = row.get(l1_id)
                k2_id = row.get(l2_id)
                k3_id = row.get(l3_id)

                y = row.get('sale_date__year')
                net = float(row.get('total_net') or 0.0)
                profit = float(row.get('total_profit') or 0.0)

                if y not in self.sorted_years:
                    continue

                if k1_id not in raw_pivot:
                    raw_pivot[k1_id] = {
                        'id': k1_id,
                        'name': l1_names.get(k1_id) or 'Sin registro',
                        't_o': 0.0,
                        'totals': self._init_annual_totals(),
                        'children': {},
                    }
                raw_pivot[k1_id]['t_o'] += net
                raw_pivot[k1_id]['totals'][y]['net'] += net
                raw_pivot[k1_id]['totals'][y]['profit'] += profit

                l1_children = raw_pivot[k1_id]['children']
                if k2_id not in l1_children:
                    l1_children[k2_id] = {
                        'id': k2_id,
                        'name': l2_names.get(k2_id) or 'Sin registro',
                        't_o': 0.0,
                        'totals': self._init_annual_totals(),
                        'children': {},
                    }
                l1_children[k2_id]['t_o'] += net
                l1_children[k2_id]['totals'][y]['net'] += net
                l1_children[k2_id]['totals'][y]['profit'] += profit

                l2_children = l1_children[k2_id]['children']
                if k3_id not in l2_children:
                    l2_children[k3_id] = {
                        'id': k3_id,
                        'name': l3_names.get(k3_id) or 'Sin registro',
                        't_o': 0.0,
                        'totals': self._init_annual_totals(),
                    }
                l2_children[k3_id]['t_o'] += net
                l2_children[k3_id]['totals'][y]['net'] += net
                l2_children[k3_id]['totals'][y]['profit'] += profit

            final_pivot: dict[str, Any] = {}
            TOP_L2 = 100
            TOP_L3 = 50

            sorted_l1 = sorted(
                raw_pivot.items(), key=lambda x: x[1]['t_o'], reverse=True
            )
            for k1_id, l1_data in sorted_l1:
                l1_entry = {
                    'id': l1_data['id'],
                    'name': l1_data['name'],
                    'totals': self._flatten_annual_totals(l1_data['totals']),
                    'children': {},
                }

                sorted_l2 = sorted(
                    l1_data['children'].items(),
                    key=lambda x: x[1]['t_o'],
                    reverse=True,
                )
                for k2_id, l2_data in sorted_l2[:TOP_L2]:
                    l2_entry = {
                        'id': l2_data['id'],
                        'name': l2_data['name'],
                        'totals': self._flatten_annual_totals(l2_data['totals']),
                        'children': {},
                    }

                    sorted_l3 = sorted(
                        l2_data['children'].items(),
                        key=lambda x: x[1]['t_o'],
                        reverse=True,
                    )
                    for k3_id, l3_data in sorted_l3[:TOP_L3]:
                        l2_entry['children'][f'{k3_id}'] = {
                            'id': l3_data['id'],
                            'name': l3_data['name'],
                            'totals': self._flatten_annual_totals(l3_data['totals']),
                        }

                    otros_l3 = sorted_l3[TOP_L3:]
                    if otros_l3:
                        o_totals = self._init_annual_totals()
                        for _, ol3_data in otros_l3:
                            self._add_annual_totals(o_totals, ol3_data['totals'])
                        l3_label_otros = (
                            'OTROS PRODUCTOS'
                            if 'product' in self.dimension_config['l3_id']
                            else 'OTROS REGISTROS'
                        )
                        l2_entry['children']['otros_l3'] = {
                            'id': 'otros',
                            'name': l3_label_otros,
                            'totals': self._flatten_annual_totals(o_totals),
                        }

                    l1_entry['children'][f'{k2_id}'] = l2_entry

                final_pivot[f'{k1_id}'] = l1_entry

            return final_pivot

        else:
            for row in data_list:
                k1_id = row.get(l1_id)
                k2_id = row.get(l2_id)

                y = row.get('sale_date__year')
                net = float(row.get('total_net') or 0.0)
                profit = float(row.get('total_profit') or 0.0)

                if y not in self.sorted_years:
                    continue

                if k1_id not in raw_pivot:
                    raw_pivot[k1_id] = {
                        'id': k1_id,
                        'name': l1_names.get(k1_id) or 'Sin registro',
                        't_o': 0.0,
                        'totals': self._init_annual_totals(),
                        'children': {},
                    }
                raw_pivot[k1_id]['t_o'] += net
                raw_pivot[k1_id]['totals'][y]['net'] += net
                raw_pivot[k1_id]['totals'][y]['profit'] += profit

                l1_children = raw_pivot[k1_id]['children']
                if k2_id not in l1_children:
                    l1_children[k2_id] = {
                        'id': k2_id,
                        'name': l2_names.get(k2_id) or 'Sin registro',
                        't_o': 0.0,
                        'totals': self._init_annual_totals(),
                    }
                l1_children[k2_id]['t_o'] += net
                l1_children[k2_id]['totals'][y]['net'] += net
                l1_children[k2_id]['totals'][y]['profit'] += profit

            final_pivot = {}
            TOP_L2 = 50

            sorted_l1 = sorted(
                raw_pivot.items(), key=lambda x: x[1]['t_o'], reverse=True
            )
            for k1_id, l1_data in sorted_l1:
                l1_entry = {
                    'id': l1_data['id'],
                    'name': l1_data['name'],
                    'totals': self._flatten_annual_totals(l1_data['totals']),
                    'children': {},
                }

                sorted_l2 = sorted(
                    l1_data['children'].items(),
                    key=lambda x: x[1]['t_o'],
                    reverse=True,
                )
                for k2_id, l2_data in sorted_l2[:TOP_L2]:
                    l1_entry['children'][f'{k2_id}'] = {
                        'id': l2_data['id'],
                        'name': l2_data['name'],
                        'totals': self._flatten_annual_totals(l2_data['totals']),
                    }

                otros_l2 = sorted_l2[TOP_L2:]
                if otros_l2:
                    o_totals = self._init_annual_totals()
                    for _, ol2_data in otros_l2:
                        self._add_annual_totals(o_totals, ol2_data['totals'])

                    l2_label_otros = (
                        'OTROS PRODUCTOS'
                        if 'product' in self.dimension_config['l2_id']
                        else 'OTROS REGISTROS'
                    )
                    l1_entry['children']['otros_l2'] = {
                        'id': 'otros',
                        'name': l2_label_otros,
                        'totals': self._flatten_annual_totals(o_totals),
                    }

                final_pivot[f'{k1_id}'] = l1_entry

            return final_pivot


@dataclass
class YearlySaleBreakdownExports:
    breakdown_service: YearlySaleBreakdownService

    def export_yearly_sale_breakdown_csv(self, is_seller: bool = False) -> io.BytesIO:
        """
        exports the full yearly sale breakdown dataset to a csv buffer with utf-8-sig encoding.
        respects active filters, user permissions for seller margin, and includes assigned route
        and route business unit for customer entities.
        """
        config = self.breakdown_service.dimension_config
        depth = config['depth']
        years = self.breakdown_service.sorted_years

        level_keys = [config[f'l{i}_id'] for i in range(1, depth + 1)]
        group_fields = [*level_keys, 'sale_date__year']

        data_list = (
            self.breakdown_service.queryset
            .values(*group_fields)
            .annotate(
                total_net=Sum('net_amount'),
                total_profit=Sum('profit'),
            )
            .order_by(*level_keys)
        )

        combos: dict[tuple, dict[int, dict[str, float]]] = defaultdict(
            lambda: {y: {'net': 0.0, 'profit': 0.0} for y in years}
        )
        combo_total_net: dict[tuple, float] = defaultdict(float)
        level_ids = {i: set() for i in range(1, depth + 1)}

        for row in data_list:
            combo_key = tuple(row[k] for k in level_keys)
            y = row['sale_date__year']
            if y in years:
                net = float(row['total_net'] or 0.0)
                profit = float(row['total_profit'] or 0.0)
                combos[combo_key][y]['net'] += net
                combos[combo_key][y]['profit'] += profit
                combo_total_net[combo_key] += net

                for i, k in enumerate(level_keys, start=1):
                    val = row[k]
                    if val is not None:
                        level_ids[i].add(val)

        # batch fetch entity names for each hierarchy level
        names_map: dict[int, dict[Any, str]] = {}
        customer_assignment_map: dict[str, dict[str, str]] = {}

        for i in range(1, depth + 1):
            model = config[f'l{i}_model']
            ids = level_ids[i]
            if ids:
                names_map[i] = dict(model.objects.filter(id__in=ids).values_list('id', 'name'))
                # if the entity is customer, also fetch active route assignment and route business unit
                if model == Customer:
                    active_assignments = (
                        CustomerAssignment.objects
                        .filter(customer_id__in=ids, end_date__isnull=True)
                        .values('customer_id', 'route_id', 'route__name', 'route__business_unit__name')
                    )
                    for assign in active_assignments:
                        cid = assign['customer_id']
                        r_id = assign.get('route_id') or ''
                        r_name = assign.get('route__name') or ''
                        bu_name = assign.get('route__business_unit__name') or ''
                        customer_assignment_map[cid] = {
                            'route_id': r_id,
                            'route_name': r_name.strip(),
                            'business_unit': bu_name.strip(),
                        }
            else:
                names_map[i] = {}

        # build dynamic csv headers
        headers: list[str] = []
        for i in range(1, depth + 1):
            model = config[f'l{i}_model']
            label = config[f'l{i}_label']
            if model == Customer:
                headers.extend([
                    'ID Cliente',
                    'Cliente',
                    'ID Ruta Asignada',
                    'Ruta Asignada',
                    'Gerencia de Ruta',
                ])
            elif model == BusinessUnit:
                headers.append(label)
            else:
                headers.extend([f'ID {label}', label])

        for y in years:
            headers.append(f'Venta Neta {y}')
            headers.append(f'Crecimiento % {y}')
            if is_seller:
                headers.append(f'Margen {y}')
            else:
                headers.append(f'Margen % {y}')
                headers.append(f'Clasificación Margen {y}')

        # sort combinations by total net sales descending
        sorted_combos = sorted(combos.items(), key=lambda x: combo_total_net[x[0]], reverse=True)

        buffer = io.BytesIO()
        buffer.write(b'\xef\xbb\xbf')  # utf-8 bom for seamless excel compatibility
        text_wrapper = io.TextIOWrapper(buffer, encoding='utf-8', newline='')
        writer = csv.writer(text_wrapper)
        writer.writerow(headers)

        for combo_key, totals in sorted_combos:
            row_data: list[Any] = []
            for i, val in enumerate(combo_key, start=1):
                model = config[f'l{i}_model']
                val_str = str(val) if val is not None else ''
                name_str = names_map[i].get(val) or ('Sin registro' if val is not None else '')

                if model == Customer:
                    assign = customer_assignment_map.get(val_str, {})
                    r_id = assign.get('route_id', '')
                    r_name = assign.get('route_name', '')
                    bu_name = assign.get('business_unit', '')
                    row_data.extend([
                        val_str,
                        name_str.title() if name_str else '',
                        r_id,
                        r_name.title() if r_name else 'Sin asignación',
                        bu_name.title() if bu_name else 'Sin gerencia',
                    ])
                elif model == BusinessUnit:
                    row_data.append(name_str.title() if name_str else '')
                else:
                    row_data.extend([
                        val_str,
                        name_str.title() if name_str else '',
                    ])

            prev_net = None
            for y in years:
                net = totals[y]['net']
                profit = totals[y]['profit']
                margin = (profit / net * 100.0) if net > 0 else 0.0
                if prev_net is not None and prev_net > 0:
                    growth = (net - prev_net) / prev_net * 100.0
                else:
                    growth = 0.0

                if margin >= 43:
                    m_label = 'Excelente'
                elif margin >= 40:
                    m_label = 'Óptimo'
                elif margin >= 37:
                    m_label = 'Regular'
                elif margin >= 35:
                    m_label = 'Malo'
                else:
                    m_label = 'Muy malo'

                if is_seller:
                    row_data.extend([round(net, 2), round(growth, 2), m_label])
                else:
                    row_data.extend([round(net, 2), round(growth, 2), round(margin, 2), m_label])

                prev_net = net

            writer.writerow(row_data)

        text_wrapper.flush()
        text_wrapper.detach()
        buffer.seek(0)
        return buffer

