from decimal import Decimal
from collections import defaultdict
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter


from django.db.models import Sum, Count, F
from django.db.models.functions import ExtractMonth
from django.http import HttpResponse



from apps.core.models import SaleTransaction, SaleTarget, Customer, AccountsReceivable, ProductClass




class MonthlyBreakdownByWarehouse:
    def __init__(self, year, allowed_routes_qs, warehouse_id):
        self.year = int(year)
        self.allowed_routes_qs = allowed_routes_qs
        self.warehouse_id = warehouse_id
        
        self.routes_qs = self.allowed_routes_qs.filter(warehouse_id=self.warehouse_id)
        self.route_ids = list(self.routes_qs.values_list('id', flat=True))

    def _get_monthly_targets(self):
        targets_qs = SaleTarget.objects.filter(
            period__year=self.year,
            route_id__in=self.route_ids
        ).annotate(
            month=ExtractMonth('period')
        ).values('route_id', 'product_class__name', 'month').annotate(
            total=Sum('target_amount')
        )
        
        data = defaultdict(Decimal)
        for row in targets_qs:
            key = (row['route_id'], row['product_class__name'].lower(), row['month'])
            data[key] = row['total'] or Decimal('0.00')
        return data

    def _get_monthly_sales(self):
        sales_qs = SaleTransaction.objects.filter(
            sale_date__year=self.year,
            route_id__in=self.route_ids
        ).annotate(
            month=ExtractMonth('sale_date')
        ).values('route_id', 'product_class__name', 'month').annotate(
            total=Sum('net_amount')
        )
        
        data = defaultdict(Decimal)
        for row in sales_qs:
            key = (row['route_id'], row['product_class__name'].lower(), row['month'])
            data[key] = row['total'] or Decimal('0.00')
        return data

    def _get_monthly_margin(self):
        margin_qs = SaleTransaction.objects.filter(
            sale_date__year=self.year,
            route_id__in=self.route_ids
        ).annotate(
            month=ExtractMonth('sale_date')
        ).values('route_id', 'month').annotate(
            total_profit=Sum('profit'),
            total_net=Sum('net_amount')
        )
        data = defaultdict(Decimal)
        for row in margin_qs:
            t_profit = row['total_profit'] or Decimal('0.00')
            t_net = row['total_net'] or Decimal('0.00')
            if t_net > 0:
                margin = (t_profit / t_net) * Decimal('100.00')
            else:
                margin = Decimal('0.00')
                
            data[(row['route_id'], row['month'])] = margin
        return data

    def _get_monthly_new_customers(self):
        customers_qs = Customer.objects.filter(
            registration_date__year=self.year,
            route_id__in=self.route_ids
        ).annotate(
            month=ExtractMonth('registration_date')
        ).values('route_id', 'month').annotate(
            total=Count('id')
        )
        data = defaultdict(int)
        for row in customers_qs:
            data[(row['route_id'], row['month'])] = row['total'] or 0
        return data

    def _get_monthly_accounts_receivable(self):
        ar_qs = AccountsReceivable.objects.filter(
            period__year=self.year,
            route_id__in=self.route_ids
        ).annotate(
            month=ExtractMonth('period')
        ).values('route_id', 'month').annotate(
            total_amount=Sum('total_balance'),
            total_count=Count('id')
        )
        amount_data = defaultdict(Decimal)
        count_data = defaultdict(int)
        for row in ar_qs:
            amount_data[(row['route_id'], row['month'])] = row['total_amount'] or Decimal('0.00')
            count_data[(row['route_id'], row['month'])] = row['total_count'] or 0
        return count_data, amount_data

    def _get_monthly_promotions(self):
        return defaultdict(Decimal)

    def _get_monthly_agreements(self):
        return defaultdict(int)

    def get_data(self):
        """
        Retrieve and structure the monthly breakdown data.

        This method orchestrates the data retrieval by calling helper methods for:
        - Monthly targets
        - Monthly sales
        - Monthly margins
        - Monthly new customers
        - Monthly accounts receivable (both count and amount)
        - Monthly promotions
        - Monthly agreements

        Returns:
            list: A list containing a single dictionary with the structured breakdown data.
        """
        product_classes = ProductClass.objects.values_list('name', flat=True)
        pc_names = sorted(list(set(pc.lower() for pc in product_classes)))
        
        targets = self._get_monthly_targets()
        sales = self._get_monthly_sales()
        margins = self._get_monthly_margin()
        new_customers = self._get_monthly_new_customers()
        ar_counts, ar_amounts = self._get_monthly_accounts_receivable()
        promotions = self._get_monthly_promotions()
        agreements = self._get_monthly_agreements()

        from apps.core.models import Warehouse
        try:
            warehouse = Warehouse.objects.get(id=self.warehouse_id)
            warehouse_name = warehouse.name
        except Warehouse.DoesNotExist:
            warehouse_name = "Desconocida"

        temp_warehouse = {
            'warehouse_id': self.warehouse_id,
            'warehouse_name': warehouse_name,
            'routes': []
        }

        results_names = ['margen', 'clientes nuevos', 'cuentas por cobrar', 'cuentas por cobrar $', 'promociones', 'convenios']

        for route in self.routes_qs:
            route_id = route.id
            temp_route = {
                'route_id': route_id,
                'route_name': route.name,
                'product_classes': [],
                'total': {'name': 'total', 'monthly_data': []},
                'results': []
            }
            
            route_monthly_totals = {m: {'target': Decimal('0.00'), 'net_sale': Decimal('0.00')} for m in range(1, 13)}

            for pc_name in pc_names:
                temp_pc = {'name': pc_name, 'monthly_data': []}
                for month in range(1, 13):
                    t = targets[(route_id, pc_name, month)]
                    s = sales[(route_id, pc_name, month)]
                    diff = s - t
                    scope = (s / t * Decimal('100')) if t > 0 else (Decimal('100') if s > 0 else Decimal('0'))
                    
                    temp_pc['monthly_data'].append({
                        'target': t,
                        'net_sale': s,
                        'diff': diff,
                        'scope': scope
                    })

                    route_monthly_totals[month]['target'] += t
                    route_monthly_totals[month]['net_sale'] += s

                temp_route['product_classes'].append(temp_pc)

            for month in range(1, 13):
                t = route_monthly_totals[month]['target']
                s = route_monthly_totals[month]['net_sale']
                diff = s - t
                scope = (s / t * Decimal('100')) if t > 0 else (Decimal('100') if s > 0 else Decimal('0'))

                temp_route['total']['monthly_data'].append({
                    'target': t,
                    'net_sale': s,
                    'diff': diff,
                    'scope': scope
                })

            for res_name in results_names:
                temp_res = {'name': res_name, 'monthly_data': []}
                for month in range(1, 13):
                    val = 0
                    if res_name == 'margen':
                        val = f"{margins[(route_id, month)]:,.2f} %"
                    elif res_name == 'clientes nuevos':
                        val = new_customers[(route_id, month)]
                    elif res_name == 'cuentas por cobrar':
                        val = ar_counts[(route_id, month)]
                    elif res_name == 'cuentas por cobrar $':
                        val = f"$ {ar_amounts[(route_id, month)]:,.2f}"
                    elif res_name == 'promociones':
                        val = f"{promotions[(route_id, month)]:,.2f}"
                    elif res_name == 'convenios':
                        val = agreements[(route_id, month)]
                    
                    temp_res['monthly_data'].append({'value': val})
                temp_route['results'].append(temp_res)
            
            temp_warehouse['routes'].append(temp_route)
        
        return [temp_warehouse]


    def get_data_report(self):
        """
        Generate an Excel workbook with detailed monthly breakdown data.

        Key Features:
        - Creates one sheet per warehouse.
        - Summarizes target sales vs actual sales for each product class.
        - Includes route-level performance metrics.
        - Provides KPIs like new customers, accounts receivable, promotions, and agreements.

        Returns:
            openpyxl.Workbook: The generated workbook containing all the data.
        """
        wb = openpyxl.Workbook()
        wb.remove(wb.active)

        #style config
        HEADER_FILL = PatternFill(start_color="2D9999", fill_type="solid")
        ALT_CLASS_1 = PatternFill(start_color="FFFFFF", fill_type="solid")
        ALT_CLASS_2 = PatternFill(start_color="A4E0E6", fill_type="solid")
        TOTAL_FILL = PatternFill(start_color="FAC003", fill_type="solid")
        ALT_SUM_1 = PatternFill(start_color="D9D9D9", fill_type="solid")
        ALT_SUM_2 = PatternFill(start_color="FFFFFF", fill_type="solid")

        
        WHITE_BOLD = Font(color="FFFFFF", bold=True)
        BLACK_BOLD = Font(color="000000", bold=True)
        BLACK = Font(color="000000")
        CENTER = Alignment(horizontal="center", vertical="center")
        LEFT = Alignment(horizontal="left", vertical="center")

        THIN_BORDER = Border(
            left=Side(style='thin', color='000000'),
            right=Side(style='thin', color='000000'),
            top=Side(style='thin', color='000000'),
            bottom=Side(style='thin', color='000000')
        )




        def style_cell(cell, fill, font=None, alignment=None, number_format=None):
            cell.fill = fill
            cell.border = THIN_BORDER
            if font: cell.font = font
            if alignment: cell.alignment = alignment
            if number_format: cell.number_format = number_format
            return cell

        month_names = ['ENERO', 'FEBRERO', 'MARZO', 'ABRIL', 'MAYO', 'JUNIO', 'JULIO', 'AGOSTO', 'SEPTIEMBRE', 'OCTUBRE', 'NOVIEMBRE', 'DICIEMBRE']

        #reuse internal function
        report_data = self.get_data()

        #iteration over the gotten list
        for w_data in report_data:
            #maximum sheet title length is 31 characters
            sheet_title = (w_data['warehouse_name'] or 'Gerencia')[:31].upper()
            ws = wb.create_sheet(title=sheet_title)
            current_row = 1

            for route in w_data['routes']:
                #headers
                headers = ["AGENTE", "CLASE"]
                for m_name in month_names:
                    # Tus 4 columnas base
                    headers.extend([f"OBJETIVO {m_name}", f"VENTA {m_name}", f"ALCANCE {m_name}", f"DIF. {m_name}"])

                for col_num, val in enumerate(headers, 1):
                    c = ws.cell(row=current_row, column=col_num, value=val)
                    style_cell(c, HEADER_FILL, WHITE_BOLD, CENTER)
                current_row += 1

                #product classe rows
                row_idx = 0
                for pc in route['product_classes']:
                    fill_color = ALT_CLASS_1 if row_idx % 2 == 0 else ALT_CLASS_2

                    style_cell(ws.cell(row=current_row, column=1, value=route['route_id']), fill_color, BLACK, CENTER)
                    style_cell(ws.cell(row=current_row, column=2, value=pc['name'].upper()), fill_color, BLACK, LEFT)

                    col = 3
                    for m_data in pc['monthly_data']:
                        style_cell(ws.cell(row=current_row, column=col, value=float(m_data['target'])), fill_color, BLACK, CENTER, '"$"#,##0.00')
                        style_cell(ws.cell(row=current_row, column=col + 1, value=float(m_data['net_sale'])), fill_color, BLACK, CENTER, '"$"#,##0.00')
                        style_cell(ws.cell(row=current_row, column=col + 2, value=float(m_data['scope']) / 100), fill_color, BLACK, CENTER, '0.00%')
                        style_cell(ws.cell(row=current_row, column=col + 3, value=float(m_data['diff'])), fill_color, BLACK, CENTER, '"$"#,##0.00')
                        col += 4

                    current_row += 1
                    row_idx += 1

                #total
                style_cell(ws.cell(row=current_row, column=1, value=route['route_id']), TOTAL_FILL, BLACK_BOLD, CENTER)
                style_cell(ws.cell(row=current_row, column=2, value="TOTAL"), TOTAL_FILL, BLACK_BOLD, LEFT)

                col = 3
                for m_data in route['total']['monthly_data']:
                    style_cell(ws.cell(row=current_row, column=col, value=float(m_data['target'])), TOTAL_FILL, BLACK_BOLD, CENTER, '"$"#,##0.00')
                    style_cell(ws.cell(row=current_row, column=col + 1, value=float(m_data['net_sale'])), TOTAL_FILL, BLACK_BOLD, CENTER, '"$"#,##0.00')
                    style_cell(ws.cell(row=current_row, column=col + 2, value=float(m_data['scope']) / 100), TOTAL_FILL, BLACK_BOLD, CENTER, '0.00%')
                    style_cell(ws.cell(row=current_row, column=col + 3, value=float(m_data['diff'])), TOTAL_FILL, BLACK_BOLD, CENTER, '"$"#,##0.00')
                    col += 4
                current_row += 1

                #total rows
                res_idx = 0
                for res in route['results']:
                    fill_color = ALT_SUM_1 if res_idx % 2 == 0 else ALT_SUM_2

                    style_cell(ws.cell(row=current_row, column=1, value=route['route_id']), fill_color, BLACK_BOLD, CENTER)
                    style_cell(ws.cell(row=current_row, column=2, value=res['name'].upper()), fill_color, BLACK_BOLD, LEFT)

                    col = 3
                    for m_data in res['monthly_data']:
                        #trasnform the gotten results which have format as currency or percentage to excel recognizes them as numbers
                        val_str = str(m_data['value']).replace('$', '').replace('%', '').replace(',', '').strip()
                        try:
                            val = float(val_str)
                        except ValueError:
                            val = 0.0

                        #currency and percentage format
                        res_name = res['name'].lower()
                        num_format = '0'
                        if 'margen' in res_name:
                            num_format = '0.00%'
                            val = val / 100
                        elif '$' in res_name or 'promociones' in res_name:
                            num_format = '"$"#,##0.00'

                        #colspan 4 inthe total rows
                        ws.merge_cells(start_row=current_row, start_column=col, end_row=current_row, end_column=col + 3)
                        
                        c_val = ws.cell(row=current_row, column=col, value=val)
                        style_cell(c_val, fill_color, BLACK_BOLD, CENTER, num_format)

                        #outline
                        style_cell(ws.cell(row=current_row, column=col + 1), fill_color)
                        style_cell(ws.cell(row=current_row, column=col + 2), fill_color)
                        style_cell(ws.cell(row=current_row, column=col + 3), fill_color)

                        col += 4

                    current_row += 1
                    res_idx += 1

                #alternate colors
                current_row += 1

            #col width
            ws.column_dimensions['A'].width = 12
            ws.column_dimensions['B'].width = 25
            for col_idx in range(3, 51):
                ws.column_dimensions[get_column_letter(col_idx)].width = 16

        #http response
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename="desglose_mensual_gerencia_{self.year}_{self.warehouse_id}.xlsx"'
        wb.save(response)

        return response


    def summary_for_assistant(self) -> dict:
        """
        Generates a structured, token-optimized summary for the LLM assistant.
        Filters out product classes with zero activity to save context window 
        and formats Decimals to native floats for JSON serialization.
        """
        raw_data = self.get_data()
        
        # Si no hay datos, retornamos un dict vacío
        if not raw_data:
            return {}

        warehouse_info = raw_data[0]
        
        summary = {
            "contexto_general": {
                "año_evaluado": self.year,
                "gerencia": f"{warehouse_info['warehouse_id']} - {warehouse_info['warehouse_name']}",
                "descripción": "Reporte de ejecución de cuotas, rentabilidad (margen) y salud financiera mensual por ruta."
            },
            "rutas": []
        }

        for route in warehouse_info['routes']:
            route_summary = {
                "ruta": f"{route['route_id']} - {route['route_name']}",
                "totales_mensuales_ruta": [],
                "clases_con_actividad_comercial": [],
                "salud_financiera_e_indicadores": {}
            }

            # 1. Totales Generales de la Ruta
            for month_idx, m_data in enumerate(route['total']['monthly_data'], start=1):
                route_summary["totales_mensuales_ruta"].append({
                    "mes": month_idx,
                    "objetivo": float(m_data['target']),
                    "venta": float(m_data['net_sale']),
                    "alcance_pct": float(m_data['scope']),
                    "diferencia": float(m_data['diff'])
                })

            # 2. Clases de Producto (Filtro Inteligente)
            for pc in route['product_classes']:
                total_target = sum(m['target'] for m in pc['monthly_data'])
                total_sale = sum(m['net_sale'] for m in pc['monthly_data'])
                
                # TRUCO DE TOKENS: Solo enviamos al LLM las clases que tenían cuota 
                # o que registraron al menos una venta en el año.
                if total_target > 0 or total_sale > 0:
                    clase_limpia = {
                        "clase": pc['name'],
                        "mensual": [
                            {
                                "mes": idx + 1,
                                "objetivo": float(m['target']),
                                "venta": float(m['net_sale']),
                                "alcance_pct": float(m['scope'])
                            }
                            for idx, m in enumerate(pc['monthly_data'])
                        ]
                    }
                    route_summary["clases_con_actividad_comercial"].append(clase_limpia)

            # 3. Aplanado de Indicadores Financieros (Cobranza, Margen, Clientes)
            for res in route['results']:
                # Convertimos la lista de diccionarios en un arreglo simple de 12 posiciones
                route_summary["salud_financiera_e_indicadores"][res['name']] = [
                    m['value'] for m in res['monthly_data']
                ]

            summary["rutas"].append(route_summary)

            print(summary)

        return summary
