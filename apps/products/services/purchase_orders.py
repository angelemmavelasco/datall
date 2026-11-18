import calendar
import datetime
import io
import math
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import ClassVar

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Q, QuerySet, Sum, Count
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.core.models import Reference, ActivityLog
from apps.core.services.users import UsersService
from apps.products.models import Product, ProductClass, Stock, PurchaseOrder, PurchaseOrderItem
from apps.sales.models import Warehouse, SaleTransaction
from .products import ServiceError, PermissionsError


class PurchaseOrderNotFound(ServiceError):
    pass


@dataclass
class PurchaseOrdersService(UsersService):
    purchase_order_model: type = PurchaseOrder
    purchase_order_item_model: type = PurchaseOrderItem
    product_model: type = Product
    product_class_model: type = ProductClass
    stock_model: type = Stock
    warehouse_model: type = Warehouse
    sale_transaction_model: type = SaleTransaction

    ACCESS_CONTEXTS: ClassVar[tuple[str, ...]] = (
        'acceso_total_ordenes_compra',
        'ordenes_compra',
        'logistica',
        'acceso_total_inventario',
        'acceso_total_productos',
        'acceso_total',
    )

    VALID_TRANSITIONS: ClassVar[dict[str, str]] = {
        PurchaseOrder.StatusChoices.REALIZADA: PurchaseOrder.StatusChoices.CONFIRMADA,
        PurchaseOrder.StatusChoices.CONFIRMADA: PurchaseOrder.StatusChoices.EN_TRANSITO,
        PurchaseOrder.StatusChoices.EN_TRANSITO: PurchaseOrder.StatusChoices.COMPLETADA,
    }

    def __post_init__(self):
        super().__post_init__()
        self.errors = []
        self.warnings = []

    def get_logistics_parameters(self) -> dict:
        defaults = {
            'capacidad_camion_lbs': '44000',
            'peso_tarima_madera_lbs': '75',
            'tarimas_maximas_camion': '22',
        }
        existing_refs = {
            ref.key.strip().lower(): ref.value.strip()
            for ref in Reference.objects.filter(context='parametro_logistica_ordenes')
            if ref.key and ref.value
        }
        for key, default_val in defaults.items():
            if key not in existing_refs:
                Reference.objects.create(
                    context='parametro_logistica_ordenes',
                    key=key,
                    value=default_val,
                )
                existing_refs[key] = default_val

        try:
            truck_capacity_lbs = Decimal(existing_refs.get('capacidad_camion_lbs', '44000'))
            if truck_capacity_lbs <= 0:
                truck_capacity_lbs = Decimal('44000')
        except Exception:
            truck_capacity_lbs = Decimal('44000')

        try:
            pallet_wood_weight_lbs = Decimal(existing_refs.get('peso_tarima_madera_lbs', '75'))
            if pallet_wood_weight_lbs < 0:
                pallet_wood_weight_lbs = Decimal('75')
        except Exception:
            pallet_wood_weight_lbs = Decimal('75')

        try:
            max_pallets_per_truck = int(float(existing_refs.get('tarimas_maximas_camion', '22')))
            if max_pallets_per_truck <= 0:
                max_pallets_per_truck = 22
        except Exception:
            max_pallets_per_truck = 22

        return {
            'truck_capacity_lbs': truck_capacity_lbs,
            'pallet_wood_weight_lbs': pallet_wood_weight_lbs,
            'max_pallets_per_truck': max_pallets_per_truck,
        }

    def get_available_warehouses(self) -> QuerySet:
        return self.warehouse_model.objects.filter(
            warehouse_type=self.warehouse_model.WarehouseTypeChoices.WAREHOUSE
        ).exclude(id='snc').order_by('name')

    def get_available_product_classes(self) -> QuerySet:
        return self.product_class_model.objects.all().order_by('name')

    def read_purchase_orders(self) -> QuerySet:
        return (
            self.purchase_order_model.objects.select_related('created_by')
            .prefetch_related('warehouses', 'items__product__product_class')
            .order_by('-created_at', '-id')
        )

    def read_purchase_order(self, *, pk: int) -> PurchaseOrder:
        order = self.read_purchase_orders().filter(pk=pk).first()
        if not order:
            raise PurchaseOrderNotFound(f'No se encontró ninguna orden de compra con el ID "{pk}".')
        return order

    def get_order_audit_logs(self, *, order: PurchaseOrder) -> QuerySet:
        ct = ContentType.objects.get_for_model(self.purchase_order_model)
        return (
            ActivityLog.objects.filter(content_type=ct, object_id=str(order.pk))
            .select_related('user')
            .order_by('-created_at')
        )

    def _parse_month(self, ym_str: str) -> datetime.date | None:
        if not ym_str:
            return None
        try:
            return datetime.datetime.strptime(ym_str.strip(), '%Y-%m').date()
        except (ValueError, TypeError):
            try:
                return datetime.datetime.strptime(ym_str.strip(), '%Y-%m-%d').date().replace(day=1)
            except (ValueError, TypeError):
                return None

    def _get_end_of_month(self, d: datetime.date) -> datetime.date:
        last_day = calendar.monthrange(d.year, d.month)[1]
        return datetime.date(d.year, d.month, last_day)

    def _months_diff(self, start_date: datetime.date, end_date: datetime.date) -> int:
        return (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month) + 1

    def _find_transit_warehouses_map(self, warehouse_ids: list[str]) -> dict[str, str]:
        clean_ids = [str(wid).strip().lower() for wid in warehouse_ids if wid]
        if not clean_ids:
            return {}
        transit_candidates = self.warehouse_model.objects.filter(
            warehouse_type=self.warehouse_model.WarehouseTypeChoices.TRANSFER
        )
        transit_by_id = {w.id.strip().lower(): w.id for w in transit_candidates}
        mapping = {}
        for wid in clean_ids:
            candidate_key = f't_{wid}'
            if candidate_key in transit_by_id:
                mapping[wid] = transit_by_id[candidate_key]
            else:
                for t_id_clean, t_id_real in transit_by_id.items():
                    if wid in t_id_clean:
                        mapping[wid] = t_id_real
                        break
        return mapping

    @staticmethod
    def calculate_pallet_rounding(
        *,
        requested_units: Decimal,
        pieces_per_box: int,
        boxes_per_pallet: int,
        unit_weight: Decimal,
    ) -> dict:
        ppb = max(int(pieces_per_box or 1), 1)
        bpp = max(int(boxes_per_pallet or 1), 1)
        units_per_pallet = ppb * bpp
        weight = Decimal(str(unit_weight or '0.0000'))
        req = max(Decimal(str(requested_units or '0.00')), Decimal('0.00'))

        if req > 0:
            pallets = int(math.ceil(req / Decimal(units_per_pallet)))
        else:
            pallets = 0

        boxes = pallets * bpp
        ordered_units = pallets * units_per_pallet
        total_weight = (Decimal(ordered_units) * weight).quantize(Decimal('0.01'))

        return {
            'pieces_per_box': ppb,
            'boxes_per_pallet': bpp,
            'units_per_pallet': units_per_pallet,
            'pallets_ordered': pallets,
            'boxes_ordered': boxes,
            'ordered_units': ordered_units,
            'unit_weight': weight,
            'total_weight': total_weight,
        }

    def calculate_order_preview(
        self,
        *,
        warehouse_ids: list[str],
        start_date_str: str,
        end_date_str: str,
        grouping_mode: str = PurchaseOrder.GroupingModeChoices.SEPARATED,
        coverage_months: float | Decimal = Decimal('1.00'),
        product_class_ids: list[str] | None = None,
        rotation_level_ids: list[str] | None = None,
    ) -> dict | None:
        self.errors = []
        self.warnings = []

        clean_warehouse_ids = [str(w).strip() for w in (warehouse_ids or []) if str(w).strip()]
        if not clean_warehouse_ids:
            self.errors.append('Debes seleccionar al menos un centro de distribución.')
            return None

        start_date = self._parse_month(start_date_str)
        end_date = self._parse_month(end_date_str)
        if not start_date or not end_date:
            self.errors.append('Las fechas de evaluación no tienen un formato válido (YYYY-MM).')
            return None

        if start_date > end_date:
            self.errors.append('La fecha de inicio debe ser anterior o igual a la fecha de fin.')
            return None

        end_date = self._get_end_of_month(end_date)
        months_count = max(self._months_diff(start_date, end_date), 1)

        try:
            cov_decimal = Decimal(str(coverage_months))
            if cov_decimal < 0:
                cov_decimal = Decimal('1.00')
        except Exception:
            cov_decimal = Decimal('1.00')

        selected_warehouses = list(
            self.warehouse_model.objects.filter(id__in=clean_warehouse_ids).order_by('name')
        )
        if not selected_warehouses:
            self.errors.append('Los centros de distribución seleccionados no son válidos.')
            return None

        selected_wh_ids = [w.id for w in selected_warehouses]

        products_qs = self.product_model.objects.filter(is_active=True).select_related('product_class')
        clean_class_ids = [str(cid).strip() for cid in (product_class_ids or []) if str(cid).strip()]
        if clean_class_ids:
            products_qs = products_qs.filter(product_class_id__in=clean_class_ids)

        products = list(products_qs.order_by('name', 'id'))
        product_ids = [p.id for p in products]
        if not product_ids:
            return {
                'groups': [],
                'warehouses': selected_warehouses,
                'grouping_mode': grouping_mode,
                'months_count': months_count,
                'coverage_months': cov_decimal,
                'logistics_params': self.get_logistics_parameters(),
                'summary': {
                    'total_requested_units': Decimal('0.00'),
                    'total_ordered_units': 0,
                    'total_boxes': 0,
                    'total_pallets': 0,
                    'total_product_weight': Decimal('0.00'),
                    'total_pallet_weight': Decimal('0.00'),
                    'estimated_trucks': Decimal('0.00'),
                },
            }

        sales_qs = (
            self.sale_transaction_model.objects.filter(
                warehouse_id__in=selected_wh_ids,
                product_id__in=product_ids,
                sale_date__gte=start_date,
                sale_date__lte=end_date,
            )
            .values('product_id', 'warehouse_id')
            .annotate(total_qty=Coalesce(Sum('quantity'), Decimal('0.00')))
        )
        sales_map = {(r['product_id'], r['warehouse_id']): r['total_qty'] for r in sales_qs}

        stock_qs = (
            self.stock_model.objects.filter(
                warehouse_id__in=selected_wh_ids,
                product_id__in=product_ids,
            )
            .values('product_id', 'warehouse_id')
            .annotate(total_qty=Coalesce(Sum('quantity'), Decimal('0.00')))
        )
        stock_map = {(r['product_id'], r['warehouse_id']): r['total_qty'] for r in stock_qs}

        transit_wh_map = self._find_transit_warehouses_map(selected_wh_ids)
        reverse_transit_map = {t_id: orig_id for orig_id, t_id in transit_wh_map.items()}
        transit_stock_map = {}
        if reverse_transit_map:
            transit_qs = (
                self.stock_model.objects.filter(
                    warehouse_id__in=list(reverse_transit_map.keys()),
                    product_id__in=product_ids,
                )
                .values('product_id', 'warehouse_id')
                .annotate(total_qty=Coalesce(Sum('quantity'), Decimal('0.00')))
            )
            for r in transit_qs:
                orig_wh = reverse_transit_map.get(r['warehouse_id'])
                if orig_wh:
                    key = (r['product_id'], orig_wh)
                    transit_stock_map[key] = transit_stock_map.get(key, Decimal('0.00')) + r['total_qty']

        valid_rotations = [str(r).strip() for r in (rotation_level_ids or []) if str(r).strip()]
        grouped_results = {}

        summary_requested_units = Decimal('0.00')
        summary_ordered_units = 0
        summary_boxes = 0
        summary_pallets = 0
        summary_product_weight = Decimal('0.00')

        for p in products:
            total_sold = Decimal('0.00')
            total_stock = Decimal('0.00')
            total_transit = Decimal('0.00')
            per_warehouse = []
            sum_separated_suggestions = Decimal('0.00')

            for w in selected_warehouses:
                w_sold = sales_map.get((p.id, w.id), Decimal('0.00'))
                w_stock = stock_map.get((p.id, w.id), Decimal('0.00'))
                w_transit = transit_stock_map.get((p.id, w.id), Decimal('0.00'))
                w_avg = w_sold / Decimal(months_count)

                if w_avg > 0:
                    w_cov_pct = ((w_stock + w_transit) / w_avg) * Decimal('100.0')
                    w_cov_months = (w_stock + w_transit) / w_avg
                elif (w_stock + w_transit) > 0:
                    w_cov_pct = Decimal('100.0')
                    w_cov_months = Decimal('1.0')
                else:
                    w_cov_pct = Decimal('0.00')
                    w_cov_months = Decimal('0.00')

                w_target = w_avg * cov_decimal
                w_suggestion = max(w_target - w_stock - w_transit, Decimal('0.00')).quantize(Decimal('1'))

                total_sold += w_sold
                total_stock += w_stock
                total_transit += w_transit
                sum_separated_suggestions += w_suggestion

                per_warehouse.append({
                    'warehouse_id': w.id,
                    'warehouse_name': w.name.title(),
                    'sold_qty': round(w_sold, 2),
                    'avg_monthly': round(w_avg, 2),
                    'current_stock': round(w_stock, 2),
                    'in_transit': round(w_transit, 2),
                    'coverage_pct': round(w_cov_pct, 1),
                    'coverage_months': round(w_cov_months, 2),
                    'suggested_units': int(w_suggestion),
                })

            if total_sold == 0 and total_stock == 0 and total_transit == 0:
                continue

            total_avg = total_sold / Decimal(months_count)

            if total_sold > 50:
                rotation_level = '1'
                rotation_name = 'Alta'
            elif total_sold >= 10:
                rotation_level = '2'
                rotation_name = 'Media'
            else:
                rotation_level = '3'
                rotation_name = 'Baja'

            if valid_rotations and rotation_level not in valid_rotations:
                continue

            if total_avg > 0:
                global_cov_pct = ((total_stock + total_transit) / total_avg) * Decimal('100.0')
                global_cov_months = (total_stock + total_transit) / total_avg
            elif (total_stock + total_transit) > 0:
                global_cov_pct = Decimal('100.0')
                global_cov_months = Decimal('1.0')
            else:
                global_cov_pct = Decimal('0.00')
                global_cov_months = Decimal('0.00')

            if grouping_mode == PurchaseOrder.GroupingModeChoices.ACCUMULATED:
                global_target = total_avg * cov_decimal
                initial_requested = max(global_target - total_stock - total_transit, Decimal('0.00')).quantize(Decimal('1'))
            else:
                initial_requested = sum_separated_suggestions

            rounding = self.calculate_pallet_rounding(
                requested_units=initial_requested,
                pieces_per_box=p.pieces_per_box,
                boxes_per_pallet=p.boxes_per_pallet,
                unit_weight=p.weight,
            )

            summary_requested_units += initial_requested
            summary_ordered_units += rounding['ordered_units']
            summary_boxes += rounding['boxes_ordered']
            summary_pallets += rounding['pallets_ordered']
            summary_product_weight += rounding['total_weight']

            class_id = p.product_class_id or 'otr'
            class_name = p.product_class.name.title() if p.product_class and p.product_class.name else 'Sin Clase'

            if class_id not in grouped_results:
                grouped_results[class_id] = {
                    'class_id': class_id,
                    'class_name': class_name,
                    'products': [],
                }

            grouped_results[class_id]['products'].append({
                'product_id': p.id,
                'product_name': (p.name or '').title(),
                'unit_of_measure': p.unit_of_measure or 'PIEZA',
                'sold_qty': round(total_sold, 2),
                'avg_monthly': round(total_avg, 2),
                'current_stock': round(total_stock, 2),
                'in_transit': round(total_transit, 2),
                'initial_coverage_pct': round(global_cov_pct, 1),
                'initial_coverage_months': round(global_cov_months, 2),
                'initial_requested_units': int(initial_requested),
                'pieces_per_box': rounding['pieces_per_box'],
                'boxes_per_pallet': rounding['boxes_per_pallet'],
                'units_per_pallet': rounding['units_per_pallet'],
                'pallets_ordered': rounding['pallets_ordered'],
                'boxes_ordered': rounding['boxes_ordered'],
                'ordered_units': rounding['ordered_units'],
                'unit_weight': round(rounding['unit_weight'], 4),
                'total_weight': round(rounding['total_weight'], 2),
                'rotation_name': rotation_name,
                'rotation_level': rotation_level,
                'warehouses_breakdown': per_warehouse,
            })

        final_groups = []
        for _, data in grouped_results.items():
            data['products'].sort(key=lambda x: x['sold_qty'], reverse=True)
            final_groups.append(data)
        final_groups.sort(key=lambda x: x['class_name'])

        logistics_params = self.get_logistics_parameters()
        wood_weight = Decimal(summary_pallets) * logistics_params['pallet_wood_weight_lbs']
        total_pallet_weight = (summary_product_weight + wood_weight).quantize(Decimal('0.01'))
        estimated_trucks = (
            (total_pallet_weight / logistics_params['truck_capacity_lbs']).quantize(Decimal('0.01'))
            if logistics_params['truck_capacity_lbs'] > 0
            else Decimal('0.00')
        )

        return {
            'groups': final_groups,
            'warehouses': selected_warehouses,
            'grouping_mode': grouping_mode,
            'months_count': months_count,
            'coverage_months': cov_decimal,
            'logistics_params': logistics_params,
            'summary': {
                'total_requested_units': summary_requested_units,
                'total_ordered_units': summary_ordered_units,
                'total_boxes': summary_boxes,
                'total_pallets': summary_pallets,
                'total_product_weight': summary_product_weight,
                'total_pallet_weight': total_pallet_weight,
                'estimated_trucks': estimated_trucks,
            },
        }

    def _generate_next_folio(self, origin_type: str = '') -> str:
        date_str = timezone.localdate().strftime('%Y%m%d')
        candidate = f'{date_str}_{uuid.uuid4().hex[:8]}'
        while self.purchase_order_model.objects.filter(folio=candidate).exists():
            candidate = f'{date_str}_{uuid.uuid4().hex[:8]}'
        return candidate

    def create_purchase_order(
        self,
        *,
        origin_type: str,
        grouping_mode: str,
        warehouse_ids: list[str],
        start_date_str: str,
        end_date_str: str,
        coverage_months: float | Decimal = Decimal('1.00'),
        product_class_ids: list[str] | None = None,
        rotation_level_ids: list[str] | None = None,
        requested_quantities: dict[str, Decimal] | None = None,
        warehouse_quantities: dict[str, dict[str, Decimal]] | None = None,
        product_coverages: dict[str, Decimal] | None = None,
        custom_folio: str | None = None,
        notes: str = '',
    ) -> PurchaseOrder:
        if not self.has_full_access:
            raise PermissionsError('No tienes permisos suficientes para generar órdenes de compra.')

        preview = self.calculate_order_preview(
            warehouse_ids=warehouse_ids,
            start_date_str=start_date_str,
            end_date_str=end_date_str,
            grouping_mode=grouping_mode,
            coverage_months=coverage_months,
            product_class_ids=product_class_ids,
            rotation_level_ids=rotation_level_ids,
        )
        if not preview:
            err_msg = '; '.join(self.errors) if self.errors else 'Parámetros inválidos para generar la orden.'
            raise ServiceError(err_msg)

        req_map = requested_quantities or {}
        wh_qty_map = warehouse_quantities or {}
        cov_map = product_coverages or {}

        start_date = self._parse_month(start_date_str)
        end_date = self._get_end_of_month(self._parse_month(end_date_str))

        items_payload = []
        total_req_units = Decimal('0.00')
        total_ord_units = 0
        total_boxes = 0
        total_pallets = 0
        total_prod_weight = Decimal('0.00')

        for group in preview['groups']:
            for row in group['products']:
                pid = row['product_id']
                wh_breakdown = {}

                if pid in wh_qty_map and wh_qty_map[pid]:
                    prod_req = Decimal('0.00')
                    for wid, qval in wh_qty_map[pid].items():
                        clean_q = max(Decimal(str(qval or '0')), Decimal('0.00'))
                        wh_breakdown[wid] = float(clean_q)
                        prod_req += clean_q
                elif pid in req_map:
                    prod_req = max(Decimal(str(req_map[pid] or '0')), Decimal('0.00'))
                    for w_item in row['warehouses_breakdown']:
                        wh_breakdown[w_item['warehouse_id']] = float(w_item['suggested_units'])
                else:
                    prod_req = Decimal(str(row['initial_requested_units']))
                    for w_item in row['warehouses_breakdown']:
                        wh_breakdown[w_item['warehouse_id']] = float(w_item['suggested_units'])

                if prod_req <= 0:
                    continue

                rounding = self.calculate_pallet_rounding(
                    requested_units=prod_req,
                    pieces_per_box=row['pieces_per_box'],
                    boxes_per_pallet=row['boxes_per_pallet'],
                    unit_weight=Decimal(str(row['unit_weight'])),
                )

                if rounding['ordered_units'] <= 0:
                    continue

                prod_cov = cov_map.get(pid, preview['coverage_months'])

                total_req_units += prod_req
                total_ord_units += rounding['ordered_units']
                total_boxes += rounding['boxes_ordered']
                total_pallets += rounding['pallets_ordered']
                total_prod_weight += rounding['total_weight']

                items_payload.append({
                    'product_id': pid,
                    'sold_qty': Decimal(str(row['sold_qty'])),
                    'avg_monthly': Decimal(str(row['avg_monthly'])),
                    'current_stock': Decimal(str(row['current_stock'])),
                    'in_transit_stock': Decimal(str(row['in_transit'])),
                    'coverage_months': Decimal(str(prod_cov)),
                    'suggested_units': Decimal(str(row['initial_requested_units'])),
                    'requested_units': prod_req,
                    'pieces_per_box': rounding['pieces_per_box'],
                    'boxes_per_pallet': rounding['boxes_per_pallet'],
                    'units_per_pallet': rounding['units_per_pallet'],
                    'pallets_ordered': rounding['pallets_ordered'],
                    'boxes_ordered': rounding['boxes_ordered'],
                    'ordered_units': rounding['ordered_units'],
                    'unit_weight': rounding['unit_weight'],
                    'total_weight': rounding['total_weight'],
                    'warehouse_breakdown': wh_breakdown,
                })

        if not items_payload:
            raise ServiceError('La orden debe contener al menos un producto con cantidad mayor a cero.')

        logistics_params = preview['logistics_params']
        wood_weight = Decimal(total_pallets) * logistics_params['pallet_wood_weight_lbs']
        total_pallet_weight = (total_prod_weight + wood_weight).quantize(Decimal('0.01'))

        clean_folio = (custom_folio or '').strip().upper()
        if clean_folio:
            if self.purchase_order_model.objects.filter(folio=clean_folio).exists():
                raise ServiceError(f'Ya existe una orden de compra con el folio "{clean_folio}".')
        else:
            clean_folio = self._generate_next_folio(origin_type)

        with transaction.atomic():
            order = self.purchase_order_model.objects.create(
                folio=clean_folio,
                origin_type=origin_type,
                status=PurchaseOrder.StatusChoices.REALIZADA,
                grouping_mode=grouping_mode,
                evaluation_start_date=start_date,
                evaluation_end_date=end_date,
                coverage_months=preview['coverage_months'],
                total_requested_units=total_req_units,
                total_ordered_units=total_ord_units,
                total_boxes=total_boxes,
                total_pallets=total_pallets,
                total_product_weight=total_prod_weight,
                total_pallet_weight=total_pallet_weight,
                notes=(notes or '').strip(),
                created_by=self.user,
            )
            order.warehouses.set(preview['warehouses'])

            order_items = [
                self.purchase_order_item_model(purchase_order=order, **item_data)
                for item_data in items_payload
            ]
            self.purchase_order_item_model.objects.bulk_create(order_items, batch_size=500)

        return order

    def update_order_status(
        self,
        *,
        pk: int,
        new_status: str,
        notes: str = '',
    ) -> tuple[PurchaseOrder, dict]:
        if not self.has_full_access:
            raise PermissionsError('No tienes permisos suficientes para cambiar el estatus de la orden.')

        with transaction.atomic():
            order = self.purchase_order_model.objects.select_for_update().filter(pk=pk).first()
            if not order:
                raise PurchaseOrderNotFound(f'No se encontró ninguna orden de compra con el ID "{pk}".')

            previous_status = order.status
            previous_label = order.get_status_display()

            expected_next = self.VALID_TRANSITIONS.get(previous_status)
            if new_status != expected_next:
                raise ServiceError(
                    f'Transición inválida: una orden en estatus "{previous_label}" no puede cambiar directamente a "{new_status}".'
                )

            now = timezone.now()
            order.status = new_status
            if new_status == PurchaseOrder.StatusChoices.CONFIRMADA:
                order.confirmed_at = now
            elif new_status == PurchaseOrder.StatusChoices.EN_TRANSITO:
                order.in_transit_at = now
            elif new_status == PurchaseOrder.StatusChoices.COMPLETADA:
                order.completed_at = now

            clean_notes = (notes or '').strip()
            if clean_notes:
                timestamp_str = timezone.localtime(now).strftime('%Y-%m-%d %H:%M')
                entry = f'[{timestamp_str} - { order.get_status_display() }] {clean_notes}'
                order.notes = f'{order.notes}\n{entry}'.strip() if order.notes else entry

            order.save()

            new_label = order.get_status_display()
            change_payload = {
                'folio': order.folio,
                'previous_status': previous_status,
                'previous_status_label': previous_label,
                'new_status': new_status,
                'new_status_label': new_label,
                'notes': clean_notes,
                'summary': f'Cambio de estatus de "{previous_label}" a "{new_label}"',
            }
            return order, change_payload


@dataclass
class PurchaseOrdersStats:
    purchase_orders_service: PurchaseOrdersService

    def stats(self, *, qs: QuerySet = None) -> dict:
        base_qs = qs if qs is not None else self.purchase_orders_service.read_purchase_orders()
        return self.purchase_orders_service.purchase_order_model.objects.filter(
            pk__in=base_qs.values('pk')
        ).aggregate(
            total_orders=Count('pk', distinct=True),
            pending_orders=Count(
                'pk',
                filter=Q(status__in=[
                    PurchaseOrder.StatusChoices.REALIZADA,
                    PurchaseOrder.StatusChoices.CONFIRMADA,
                ]),
                distinct=True,
            ),
            in_transit_orders=Count(
                'pk',
                filter=Q(status=PurchaseOrder.StatusChoices.EN_TRANSITO),
                distinct=True,
            ),
            completed_orders=Count(
                'pk',
                filter=Q(status=PurchaseOrder.StatusChoices.COMPLETADA),
                distinct=True,
            ),
            ordered_pallets=Coalesce(Sum('total_pallets'), 0),
            in_transit_pallets=Coalesce(
                Sum('total_pallets', filter=Q(status=PurchaseOrder.StatusChoices.EN_TRANSITO)),
                0,
            ),
            total_ordered_units=Coalesce(Sum('total_ordered_units'), 0),
            total_weight_lbs=Coalesce(Sum('total_product_weight'), Decimal('0.00')),
        )


class PurchaseOrderExports:

    @staticmethod
    def export_order_excel(
        *,
        order: PurchaseOrder,
        logistics_params: dict,
    ) -> bytes | None:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = f"Orden {order.folio}"[:31]

        header_es_fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
        header_en_fill = PatternFill(start_color="334155", end_color="334155", fill_type="solid")
        class_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
        total_fill = PatternFill(start_color="E2E8F0", end_color="E2E8F0", fill_type="solid")

        white_bold = Font(name="Calibri", color="FFFFFF", bold=True, size=10)
        white_italic = Font(name="Calibri", color="E2E8F0", italic=True, size=9)
        title_font = Font(name="Calibri", color="0F172A", bold=True, size=13)
        bold_font = Font(name="Calibri", color="0F172A", bold=True, size=10)
        regular_font = Font(name="Calibri", color="0F172A", size=10)
        muted_font = Font(name="Calibri", color="475569", size=9)

        thin_side = Side(style='thin', color='CBD5E1')
        thin_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

        warehouses = list(order.warehouses.all().order_by('name'))
        wh_names = ', '.join([w.name.title() for w in warehouses]) or 'Global'

        ws.append([f"ORDEN DE COMPRA / PURCHASE ORDER: {order.folio.upper()}"])
        ws.cell(row=ws.max_row, column=1).font = title_font

        ws.append([
            "Origen / Origin:",
            order.get_origin_type_display(),
            "Estatus / Status:",
            order.get_status_display(),
            "Fecha / Date:",
            timezone.localtime(order.created_at).strftime('%Y-%m-%d %H:%M'),
        ])
        for c_idx in (1, 3, 5):
            ws.cell(row=ws.max_row, column=c_idx).font = bold_font

        ws.append([
            "CEDIS / Warehouses:",
            wh_names,
            "Cobertura (Meses) / Coverage (Months):",
            float(order.coverage_months),
            "Modo / Mode:",
            order.get_grouping_mode_display(),
        ])
        for c_idx in (1, 3, 5):
            ws.cell(row=ws.max_row, column=c_idx).font = bold_font

        ws.append([])

        headers_es = [
            "Clave",
            "Producto",
            "Clase",
            "Peso Unitario (lbs)",
            "Piezas / Caja",
            "Cajas / Tarima",
            "Unidades / Tarima",
            "Ventas Periodo",
            "Promedio Mensual",
            "Existencia Física",
            "En Tránsito",
        ]
        headers_en = [
            "Item ID",
            "Product",
            "Class",
            "Unit Weight (lbs)",
            "Pieces / Box",
            "Boxes / Pallet",
            "Units / Pallet",
            "Period Sales",
            "Monthly Average",
            "Current Stock",
            "In Transit",
        ]

        for w in warehouses:
            headers_es.append(f"Pedido {w.name.title()}")
            headers_en.append(f"{w.name.title()} Ordered")

        headers_es.extend([
            "Unidades Requeridas",
            "Tarimas Ordenadas",
            "Cajas Ordenadas",
            "Total Unidades Ordenadas",
            "Peso Total (lbs)",
        ])
        headers_en.extend([
            "Requested Units",
            "Pallets Ordered",
            "Boxes Ordered",
            "Total Qty Ordered",
            "Total Weight (lbs)",
        ])

        items = list(
            order.items.select_related('product', 'product__product_class')
            .order_by('product__product_class__name', 'product__name', 'product__id')
        )

        grouped_items = {}
        for item in items:
            cls_name = (
                item.product.product_class.name.title()
                if item.product and item.product.product_class and item.product.product_class.name
                else 'Otros'
            )
            grouped_items.setdefault(cls_name, []).append(item)

        wh_count = len(warehouses)
        col_req = 12 + wh_count
        col_pal = 13 + wh_count
        col_box = 14 + wh_count
        col_ord = 15 + wh_count
        col_wgt = 16 + wh_count

        data_rows = []
        class_weight_rows = []

        for cls_name, cls_items in grouped_items.items():
            ws.append([f"Línea / Brand: {cls_name}"])
            cls_header_row = ws.max_row
            ws.cell(row=cls_header_row, column=1).font = bold_font
            ws.cell(row=cls_header_row, column=1).fill = class_fill

            ws.append(headers_es)
            r_es = ws.max_row
            for idx in range(1, len(headers_es) + 1):
                c = ws.cell(row=r_es, column=idx)
                c.font = white_bold
                c.fill = header_es_fill
                c.border = thin_border
                c.alignment = Alignment(horizontal="center", vertical="center")

            ws.append(headers_en)
            r_en = ws.max_row
            for idx in range(1, len(headers_en) + 1):
                c = ws.cell(row=r_en, column=idx)
                c.font = white_italic
                c.fill = header_en_fill
                c.border = thin_border
                c.alignment = Alignment(horizontal="center", vertical="center")

            first_cls_row = ws.max_row + 1
            for item in cls_items:
                breakdown = item.warehouse_breakdown or {}
                row_vals = [
                    item.product_id,
                    (item.product.name or '').title(),
                    cls_name,
                    float(item.unit_weight),
                    int(item.pieces_per_box),
                    int(item.boxes_per_pallet),
                    0,
                    float(item.sold_qty),
                    float(item.avg_monthly),
                    float(item.current_stock),
                    float(item.in_transit_stock),
                ]
                for w in warehouses:
                    row_vals.append(float(breakdown.get(w.id, 0)))

                row_vals.extend([
                    float(item.requested_units),
                    int(item.pallets_ordered),
                    0,
                    0,
                    0,
                ])
                ws.append(row_vals)
                d_row = ws.max_row
                data_rows.append(d_row)

                req_letter = get_column_letter(col_req)
                pal_letter = get_column_letter(col_pal)
                box_letter = get_column_letter(col_box)
                ord_letter = get_column_letter(col_ord)

                ws.cell(row=d_row, column=7, value=f"=E{d_row}*F{d_row}")
                if wh_count > 0:
                    first_wh_letter = get_column_letter(12)
                    last_wh_letter = get_column_letter(11 + wh_count)
                    ws.cell(row=d_row, column=col_req, value=f"=SUM({first_wh_letter}{d_row}:{last_wh_letter}{d_row})")

                ws.cell(row=d_row, column=col_pal, value=f"=IF({req_letter}{d_row}>0, CEILING({req_letter}{d_row}/G{d_row}, 1), 0)")
                ws.cell(row=d_row, column=col_box, value=f"={pal_letter}{d_row}*F{d_row}")
                ws.cell(row=d_row, column=col_ord, value=f"={pal_letter}{d_row}*G{d_row}")
                ws.cell(row=d_row, column=col_wgt, value=f"={ord_letter}{d_row}*D{d_row}")

                for c_idx in range(1, len(headers_es) + 1):
                    c = ws.cell(row=d_row, column=c_idx)
                    c.font = regular_font
                    c.border = thin_border
                    if c_idx in (1, 2, 3):
                        c.alignment = Alignment(horizontal="left", vertical="center")
                    elif c_idx in (4, 8, 9, 10, 11, col_wgt):
                        c.number_format = '#,##0.00'
                        c.alignment = Alignment(horizontal="right", vertical="center")
                    else:
                        c.number_format = '#,##0'
                        c.alignment = Alignment(horizontal="right", vertical="center")
                        if c_idx in (col_pal, col_ord):
                            c.font = bold_font

            last_cls_row = ws.max_row
            pal_letter = get_column_letter(col_pal)
            box_letter = get_column_letter(col_box)
            ord_letter = get_column_letter(col_ord)
            wgt_letter = get_column_letter(col_wgt)

            sub_row_vals = [''] * len(headers_es)
            sub_row_vals[1] = f"Subtotal {cls_name} / {cls_name} Subtotal"
            ws.append(sub_row_vals)
            sub_row = ws.max_row
            ws.cell(row=sub_row, column=col_pal, value=f"=SUM({pal_letter}{first_cls_row}:{pal_letter}{last_cls_row})")
            ws.cell(row=sub_row, column=col_box, value=f"=SUM({box_letter}{first_cls_row}:{box_letter}{last_cls_row})")
            ws.cell(row=sub_row, column=col_ord, value=f"=SUM({ord_letter}{first_cls_row}:{ord_letter}{last_cls_row})")
            ws.cell(row=sub_row, column=col_wgt, value=f"=SUM({wgt_letter}{first_cls_row}:{wgt_letter}{last_cls_row})")
            for c_idx in range(1, len(headers_es) + 1):
                c = ws.cell(row=sub_row, column=c_idx)
                c.font = bold_font
                c.fill = total_fill
                c.border = thin_border
                if c_idx == col_wgt:
                    c.number_format = '#,##0.00'
                elif c_idx in (col_pal, col_box, col_ord):
                    c.number_format = '#,##0'

            class_weight_rows.append((cls_name, sub_row))
            ws.append([])

        ws.append(["RESUMEN DE ORDEN / ORDER SUMMARY", "Valor / Value"])
        r_sum_head = ws.max_row
        ws.cell(row=r_sum_head, column=1).font = white_bold
        ws.cell(row=r_sum_head, column=1).fill = header_es_fill
        ws.cell(row=r_sum_head, column=2).font = white_bold
        ws.cell(row=r_sum_head, column=2).fill = header_es_fill

        pal_letter = get_column_letter(col_pal)
        wgt_letter = get_column_letter(col_wgt)
        pal_refs = '+'.join([f"{pal_letter}{r}" for _, r in class_weight_rows]) or '0'

        for cls_name, sub_r in class_weight_rows:
            ws.append([f"Libras {cls_name} / {cls_name} Pounds", f"={wgt_letter}{sub_r}"])
            ws.cell(row=ws.max_row, column=1).font = regular_font
            ws.cell(row=ws.max_row, column=2).font = regular_font
            ws.cell(row=ws.max_row, column=2).number_format = '#,##0.00'

        wood_lbs = float(logistics_params.get('pallet_wood_weight_lbs', 75))
        truck_lbs = float(logistics_params.get('truck_capacity_lbs', 44000))

        ws.append(["Total Tarimas / Total Pallets", f"={pal_refs}"])
        total_pal_summary_row = ws.max_row
        ws.cell(row=total_pal_summary_row, column=1).font = bold_font
        ws.cell(row=total_pal_summary_row, column=2).font = bold_font
        ws.cell(row=total_pal_summary_row, column=2).number_format = '#,##0'

        ws.append([f"Peso de Tarimas ({wood_lbs:g} lbs) / Pallets Weight", f"=B{total_pal_summary_row}*{wood_lbs}"])
        pal_weight_row = ws.max_row
        ws.cell(row=pal_weight_row, column=1).font = regular_font
        ws.cell(row=pal_weight_row, column=2).font = regular_font
        ws.cell(row=pal_weight_row, column=2).number_format = '#,##0.00'

        wgt_refs = '+'.join([f"{wgt_letter}{r}" for _, r in class_weight_rows]) or '0'
        ws.append(["Total Libras Ordenadas / Total Pounds Ordered", f"={wgt_refs}+B{pal_weight_row}"])
        grand_total_wgt_row = ws.max_row
        ws.cell(row=grand_total_wgt_row, column=1).font = bold_font
        ws.cell(row=grand_total_wgt_row, column=1).fill = total_fill
        ws.cell(row=grand_total_wgt_row, column=2).font = bold_font
        ws.cell(row=grand_total_wgt_row, column=2).fill = total_fill
        ws.cell(row=grand_total_wgt_row, column=2).number_format = '#,##0.00'

        ws.append([f"Camiones Estimados ({truck_lbs:,.0f} lbs) / Estimated Trucks", f"=B{grand_total_wgt_row}/{truck_lbs}"])
        truck_row = ws.max_row
        ws.cell(row=truck_row, column=1).font = bold_font
        ws.cell(row=truck_row, column=2).font = bold_font
        ws.cell(row=truck_row, column=2).number_format = '0.00'

        ws.column_dimensions['A'].width = 16
        ws.column_dimensions['B'].width = 40
        ws.column_dimensions['C'].width = 18
        for col_idx in range(4, len(headers_es) + 1):
            ws.column_dimensions[get_column_letter(col_idx)].width = 18

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return output.getvalue()
