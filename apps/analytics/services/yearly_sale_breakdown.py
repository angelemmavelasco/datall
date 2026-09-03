from dataclasses import dataclass, field
from typing import Any
from django.db.models import Max, Min, QuerySet, Sum

from apps.customers.models import Customer
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
        l1_id = self.l1_id_field

        return (
            self.queryset.values(l1_id)
            .annotate(total_overall=Sum('net_amount'))
            .filter(total_overall__gt=0)
            .order_by('-total_overall')
        )

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
