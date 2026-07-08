# apps/sales/services/sale_targets/calculator.py
import datetime
from decimal import Decimal
from django.db.models import Sum, Q
from apps.core.models import SaleTarget, SaleTransaction, Route, ProductClass, Customer
from dateutil.relativedelta import relativedelta

class SaleTargetsCalculatorService:
    def __init__(self, mode, origin_route_id, destination_route_id=None, customer_ids=None, adjustment_direction='remove'):
        self.mode = mode
        self.origin_route_id = origin_route_id
        self.destination_route_id = destination_route_id
        self.customer_ids = customer_ids or []
        self.adjustment_direction = adjustment_direction
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
            
        c_end = c_end + relativedelta(day=31)
        r_end = r_end + relativedelta(day=31)
            
        product_classes = ProductClass.objects.filter(id__in=product_class_ids)
        origin_route = Route.objects.filter(id=self.origin_route_id).first()
        dest_route = Route.objects.filter(id=self.destination_route_id).first() if self.mode == 'transfer' else None
        
        targets = self._get_route_targets([self.origin_route_id, self.destination_route_id] if self.mode == 'transfer' else [self.origin_route_id], target_year, product_classes)
        
        deltas = {} 
        if calc_method == 'average':
            deltas = self._calculate_average_deltas(c_start, c_end, product_classes)
        elif calc_method == 'contribution':
            deltas = self._calculate_contribution_deltas(c_start, c_end, r_start, r_end, product_classes)

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
        
        if self.mode == 'transfer':
            sign = -1 if is_origin else 1
        else:
            sign = 1 if self.adjustment_direction == 'add' else -1
        
        for pc in product_classes:
            pc_data = {
                'class_name': pc.name.title(),
                'months': []
            }
            
            for m in months:
                old_target = targets.get(pc.id, {}).get(m.month, Decimal('0.00'))
                
                growth = Decimal('0.00')
                if m.month > 1:
                    prev = targets.get(pc.id, {}).get(m.month - 1, Decimal('0.00'))
                    if prev > 0:
                        growth = ((old_target - prev) / prev) * 100
                    elif prev == 0 and old_target > 0:
                        growth = Decimal('100.00')
                        
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

    def export_data_report(self, results):
        if not results:
            return None
            
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
        import io
        
        wb = openpyxl.Workbook()
        wb.remove(wb.active) # Remove default sheet
        
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="1F2937", end_color="1F2937", fill_type="solid")
        header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        thin_border = Border(
            left=Side(style='thin'), right=Side(style='thin'),
            top=Side(style='thin'), bottom=Side(style='thin')
        )
        title_font = Font(bold=True, size=14)
        
        for key, r in results.items():
            if not r:
                continue
                
            route_name = r['route_name'].replace('/', '-')
            sheet_title = f"{'Origen' if key == 'origin' else 'Destino'} - {route_name}"
            sheet_title = sheet_title.translate(str.maketrans('', '', '\\/*?:[]'))[:31]
            ws = wb.create_sheet(title=sheet_title)
            
            ws.append([f"Desglose de cálculo: {r['route_name']}"])
            ws.cell(row=ws.max_row, column=1).font = title_font
            ws.append([])
            
            if not r['classes']:
                ws.append(["No hay datos"])
                continue
                
            months = r['classes'][0]['months']
            
            header_row1 = ws.max_row + 1
            ws.cell(row=header_row1, column=1, value="Clase de producto").font = header_font
            ws.cell(row=header_row1, column=1).fill = header_fill
            ws.cell(row=header_row1, column=1).alignment = header_alignment
            ws.cell(row=header_row1, column=1).border = thin_border
            ws.merge_cells(start_row=header_row1, start_column=1, end_row=header_row1+1, end_column=1)
            
            col_idx = 2
            for m in months:
                month_name = m['date'].strftime('%b %Y').title()
                ws.cell(row=header_row1, column=col_idx, value=month_name).font = header_font
                ws.cell(row=header_row1, column=col_idx).fill = header_fill
                ws.cell(row=header_row1, column=col_idx).alignment = header_alignment
                
                for c in range(col_idx, col_idx + 3):
                    ws.cell(row=header_row1, column=c).border = thin_border
                    ws.cell(row=header_row1, column=c).fill = header_fill
                
                ws.merge_cells(start_row=header_row1, start_column=col_idx, end_row=header_row1, end_column=col_idx+2)
                col_idx += 3
                
            header_row2 = header_row1 + 1
            col_idx = 2
            sub_headers = ["Obj. original", "Crecimiento", "Ajuste"]
            for m in months:
                for sub in sub_headers:
                    cell = ws.cell(row=header_row2, column=col_idx, value=sub)
                    cell.font = header_font
                    cell.fill = header_fill
                    cell.alignment = header_alignment
                    cell.border = thin_border
                    col_idx += 1
                    
            for cls in r['classes']:
                current_row = ws.max_row + 1
                first_cell = ws.cell(row=current_row, column=1, value=cls['class_name'])
                first_cell.font = Font(bold=True)
                first_cell.border = thin_border
                
                col_idx = 2
                for m in cls['months']:
                    cell1 = ws.cell(row=current_row, column=col_idx, value=m['old_target'])
                    cell1.border = thin_border
                    cell1.number_format = '"$"#,##0.00'
                    col_idx += 1
                    
                    growth_val = float(m['growth']) / 100 if m['growth'] else 0.0
                    cell2 = ws.cell(row=current_row, column=col_idx, value=growth_val)
                    cell2.border = thin_border
                    cell2.number_format = '0.0%'
                    if growth_val > 0: cell2.font = Font(color="008000")
                    elif growth_val < 0: cell2.font = Font(color="FF0000")
                    col_idx += 1
                    
                    delta_val = m['delta']
                    cell3 = ws.cell(row=current_row, column=col_idx, value=delta_val)
                    cell3.border = thin_border
                    cell3.number_format = '"$"#,##0.00'
                    if delta_val > 0: cell3.font = Font(color="008000")
                    elif delta_val < 0: cell3.font = Font(color="FF0000")
                    col_idx += 1
                    
            ws.append([])
            ws.append([])
            ws.append([f"Objetivos Planificados (Objetivos finales): {r['route_name']}"])
            ws.cell(row=ws.max_row, column=1).font = title_font
            ws.append([])
            
            header_row3 = ws.max_row + 1
            ws.cell(row=header_row3, column=1, value="Clase de producto").font = header_font
            ws.cell(row=header_row3, column=1).fill = header_fill
            ws.cell(row=header_row3, column=1).alignment = header_alignment
            ws.cell(row=header_row3, column=1).border = thin_border
            
            col_idx = 2
            for m in months:
                month_name = m['date'].strftime('%b %Y').title()
                cell = ws.cell(row=header_row3, column=col_idx, value=month_name)
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = header_alignment
                cell.border = thin_border
                col_idx += 1
                
            for cls in r['classes']:
                current_row = ws.max_row + 1
                first_cell = ws.cell(row=current_row, column=1, value=cls['class_name'])
                first_cell.font = Font(bold=True)
                first_cell.border = thin_border
                
                col_idx = 2
                for m in cls['months']:
                    cell = ws.cell(row=current_row, column=col_idx, value=m['new_target'])
                    cell.border = thin_border
                    cell.number_format = '"$"#,##0.00'
                    if m['new_target'] > m['old_target']:
                        cell.font = Font(color="008000", bold=True)
                    elif m['new_target'] < m['old_target']:
                        cell.font = Font(color="FF0000", bold=True)
                    col_idx += 1
                    
            ws.column_dimensions['A'].width = 25
            for c in range(2, ws.max_column + 1):
                ws.column_dimensions[get_column_letter(c)].width = 15
                
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return output.getvalue()

