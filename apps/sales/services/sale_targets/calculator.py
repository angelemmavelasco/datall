# apps/sales/services/sale_targets/calculator.py
import datetime
from decimal import Decimal
from django.db.models import Sum, Q
from apps.core.models import SaleTarget, SaleTransaction, Route, ProductClass, Customer
from dateutil.relativedelta import relativedelta

class SaleTargetsCalculatorService:
    def __init__(self, mode, origin_route_id, destination_route_id=None, customer_ids=None):
        self.mode = mode
        self.origin_route_id = origin_route_id
        self.destination_route_id = destination_route_id
        self.customer_ids = customer_ids or []
        self.errors = []
        
    def _parse_month(self, ym_str):
        if not ym_str: return None
        try:
            return datetime.datetime.strptime(ym_str, '%Y-%m').date()
        except:
            return None

    def _months_diff(self, start_date, end_date):
        return (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month) + 1

    def calculate_simulation(self, target_year, effective_month, eval_customer_start, eval_customer_end, eval_route_start, eval_route_end, product_class_ids, calc_method):
        if not self.origin_route_id or not self.customer_ids:
            self.errors.append("Falta seleccionar ruta origen o clientes.")
            return None
            
        if self.mode == 'transfer' and not self.destination_route_id:
            self.errors.append("Falta seleccionar la ruta destino.")
            return None

        eff_date = self._parse_month(effective_month)
        c_start = self._parse_month(eval_customer_start)
        c_end = self._parse_month(eval_customer_end)
        r_start = self._parse_month(eval_route_start)
        r_end = self._parse_month(eval_route_end)

        if not all([eff_date, c_start, c_end, r_start, r_end]):
            self.errors.append("Las fechas ingresadas no tienen un formato válido.")
            return None
            
        # Ajustar fin de mes para las evaluaciones
        c_end = c_end + relativedelta(day=31)
        r_end = r_end + relativedelta(day=31)
            
        product_classes = ProductClass.objects.filter(id__in=product_class_ids)
        origin_route = Route.objects.filter(id=self.origin_route_id).first()
        dest_route = Route.objects.filter(id=self.destination_route_id).first() if self.mode == 'transfer' else None
        
        # 1. Base Targets per route per class for the target year
        # {route_id: {class_id: {month(int): target_amount}}}
        targets = self._get_route_targets([self.origin_route_id, self.destination_route_id] if self.mode == 'transfer' else [self.origin_route_id], target_year, product_classes)
        
        # 2. Compute Modifiers (Deltas) per class
        deltas = {} # {class_id: delta_value (or percentage)}
        if calc_method == 'average':
            deltas = self._calculate_average_deltas(c_start, c_end, product_classes)
        elif calc_method == 'contribution':
            deltas = self._calculate_contribution_deltas(c_start, c_end, r_start, r_end, product_classes)

        # 3. Build computed deltas month by month per class (absolute values to transfer)
        computed_deltas = {}
        origin_targets = targets.get(self.origin_route_id, {})
        
        for pc in product_classes:
            computed_deltas[pc.id] = {}
            current_avg_base = Decimal('0.00')
            
            for m in range(1, 13):
                if m < eff_date.month:
                    computed_deltas[pc.id][m] = Decimal('0.00')
                else:
                    if calc_method == 'average':
                        if m == eff_date.month:
                            current_avg_base = deltas.get(pc.id, Decimal('0.00'))
                        else:
                            # Apply growth of origin route from m-1 to m
                            orig_prev = origin_targets.get(pc.id, {}).get(m - 1, Decimal('0.00'))
                            orig_curr = origin_targets.get(pc.id, {}).get(m, Decimal('0.00'))
                            
                            if orig_prev > 0:
                                growth_factor = orig_curr / orig_prev
                                current_avg_base = current_avg_base * growth_factor
                                
                        computed_deltas[pc.id][m] = current_avg_base
                        
                    elif calc_method == 'contribution':
                        pct = deltas.get(pc.id, Decimal('0.00'))
                        base_for_pct = origin_targets.get(pc.id, {}).get(m, Decimal('0.00'))
                        computed_deltas[pc.id][m] = base_for_pct * pct

        # 4. Build Result Structure
        months = [datetime.date(target_year, m, 1) for m in range(1, 13)]
        
        origin_result = self._build_route_result(origin_route, product_classes, origin_targets, computed_deltas, months, is_origin=True)
        dest_result = None
        if self.mode == 'transfer':
            dest_result = self._build_route_result(dest_route, product_classes, targets.get(self.destination_route_id, {}), computed_deltas, months, is_origin=False)
            
        return {
            'origin': origin_result,
            'destination': dest_result
        }

    def _get_route_targets(self, route_ids, target_year, product_classes):
        start_y = datetime.date(target_year, 1, 1)
        end_y = datetime.date(target_year, 12, 31)
        
        qs = SaleTarget.objects.filter(
            route_id__in=[r for r in route_ids if r],
            product_class__in=product_classes,
            period__gte=start_y,
            period__lte=end_y
        )
        
        targets = {}
        for r_id in route_ids:
            if not r_id: continue
            targets[r_id] = {pc.id: {m: Decimal('0.00') for m in range(1, 13)} for pc in product_classes}
            
        for t in qs:
            targets[t.route_id][t.product_class_id][t.period.month] = t.target_amount
            
        return targets

    def _calculate_average_deltas(self, start_date, end_date, product_classes):
        months_count = self._months_diff(start_date, end_date)
        if months_count <= 0: months_count = 1
        
        sales = SaleTransaction.objects.filter(
            customer_id__in=self.customer_ids,
            product_class__in=product_classes,
            sale_date__gte=start_date,
            sale_date__lte=end_date
        ).values('product_class').annotate(total=Sum('net_amount'))
        
        sales_map = {item['product_class']: item['total'] for item in sales}
        
        deltas = {}
        for pc in product_classes:
            total = sales_map.get(pc.id, Decimal('0.00'))
            deltas[pc.id] = total / Decimal(months_count)
        return deltas

    def _calculate_contribution_deltas(self, c_start, c_end, r_start, r_end, product_classes):
        c_sales = SaleTransaction.objects.filter(
            customer_id__in=self.customer_ids,
            product_class__in=product_classes,
            sale_date__gte=c_start,
            sale_date__lte=c_end
        ).values('product_class').annotate(total=Sum('net_amount'))
        c_map = {item['product_class']: item['total'] for item in c_sales}
        
        r_sales = SaleTransaction.objects.filter(
            route_id=self.origin_route_id,
            product_class__in=product_classes,
            sale_date__gte=r_start,
            sale_date__lte=r_end
        ).values('product_class').annotate(total=Sum('net_amount'))
        r_map = {item['product_class']: item['total'] for item in r_sales}
        
        deltas = {}
        for pc in product_classes:
            c_val = c_map.get(pc.id, Decimal('0.00'))
            r_val = r_map.get(pc.id, Decimal('0.00'))
            if r_val > 0:
                deltas[pc.id] = c_val / r_val
            else:
                deltas[pc.id] = Decimal('0.00')
        return deltas

    def _build_route_result(self, route, product_classes, targets, computed_deltas, months, is_origin):
        result = {
            'route_name': f"{route.id.upper()} {route.name.title()}",
            'classes': []
        }
        
        sign = -1 if is_origin else 1
        
        for pc in product_classes:
            pc_data = {
                'class_name': pc.name.title(),
                'months': []
            }
            
            for m in months:
                old_target = targets.get(pc.id, {}).get(m.month, Decimal('0.00'))
                
                # Growth vs previous month
                growth = Decimal('0.00')
                if m.month > 1:
                    prev = targets.get(pc.id, {}).get(m.month - 1, Decimal('0.00'))
                    if prev > 0:
                        growth = ((old_target - prev) / prev) * 100
                        
                delta_val = computed_deltas.get(pc.id, {}).get(m.month, Decimal('0.00')) * sign
                
                new_target = old_target + delta_val
                if new_target < 0: new_target = Decimal('0.00')
                
                pc_data['months'].append({
                    'date': m,
                    'old_target': old_target,
                    'growth': growth,
                    'delta': delta_val,
                    'new_target': new_target
                })
            result['classes'].append(pc_data)
            
        return result
