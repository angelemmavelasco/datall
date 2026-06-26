from datetime import datetime, date, timedelta
from collections import defaultdict
from decimal import Decimal
from django.db.models import Sum, Count, Q
from apps.core.models import Customer
from apps.sales.services.sale_transactions.sale_transactions_crud import SaleTransactionCRUD
from apps.sales.services.sale_targets.sale_targets_crud import SaleTargetCRUD

class TargetScopeService:
    def __init__(self, allowed_routes, filters):
        self.allowed_routes = allowed_routes
        self.filters = filters
        
        self.valid_classes = ['diamond', 'diamond naturals', 'care', 'taste of the wild', 'msd', 'vetoquinol', 'zoetis']
        self.display_classes = self.valid_classes + ['country value', 'nutriforce', 'otros']
        
    def _get_business_days(self, date_start_dt, date_end_dt):
        if not date_start_dt or not date_end_dt:
            return 1, 1
        total_days = 0
        curr = date_start_dt
        while curr <= date_end_dt:
            if curr.weekday() < 5:  # Lunes a Viernes
                total_days += 1
            curr += timedelta(days=1)
            
        today = date.today()
        yesterday = today - timedelta(days=1)
        
        elapsed_days = 0
        curr = date_start_dt
        end_elapsed = min(yesterday, date_end_dt)
        
        while curr <= end_elapsed:
            if curr.weekday() < 5:  # Lunes a Viernes
                elapsed_days += 1
            curr += timedelta(days=1)
            
        elapsed_safe = max(1, elapsed_days)
        if total_days == 0: total_days = 1
        
        return total_days, elapsed_safe

    def get_data(self):
        date_start_str = self.filters.get('sale_date_start')
        date_end_str = self.filters.get('sale_date_end')
        
        if date_start_str and date_end_str:
            date_start_dt = datetime.strptime(date_start_str, '%Y-%m-%d').date()
            date_end_dt = datetime.strptime(date_end_str, '%Y-%m-%d').date()
            total_b_days, elapsed_b_days_m1 = self._get_business_days(date_start_dt, date_end_dt)
        else:
            total_b_days = 1
            elapsed_b_days_m1 = 1
            date_start_dt = None
            date_end_dt = None

        tx_crud = SaleTransactionCRUD()
        tx_qs = tx_crud.read(self.allowed_routes, **self.filters)
        
        target_filters = self.filters.copy()
        if date_start_dt: target_filters['period_start'] = date_start_dt
        if date_end_dt: target_filters['period_end'] = date_end_dt
        if 'sale_date_start' in target_filters: del target_filters['sale_date_start']
        if 'sale_date_end' in target_filters: del target_filters['sale_date_end']
        
        target_crud = SaleTargetCRUD()
        target_qs = target_crud.read(self.allowed_routes, **target_filters)
        
        customer_qs = Customer.objects.filter(route__in=self.allowed_routes)
        if date_end_dt:
            customer_qs = customer_qs.filter(registration_date__lte=date_end_dt)
            
        customers_per_route = customer_qs.values('route_id').annotate(
            registered=Count('id')
        )
        
        new_customers_qs = customer_qs
        if date_start_dt and date_end_dt:
            new_customers_qs = new_customers_qs.filter(
                registration_date__gte=date_start_dt,
                registration_date__lte=date_end_dt
            )
        new_customers_per_route = new_customers_qs.values('route_id').annotate(
            nuevos=Count('id')
        )
        
        active_customers_qs = tx_qs.values('route_id').annotate(
            active=Count('customer_id', distinct=True)
        )
        
        route_customers_dict = defaultdict(lambda: {'registered': 0, 'new': 0, 'active': 0})
        for row in customers_per_route:
            route_customers_dict[row['route_id']]['registered'] = row['registered']
        for row in new_customers_per_route:
            route_customers_dict[row['route_id']]['new'] = row['nuevos']
        for row in active_customers_qs:
            route_customers_dict[row['route_id']]['active'] = row['active']
            
        route_targets = target_qs.values(
            'route_id', 
            'route__name',
            'warehouse_id',
            'warehouse__name',
            'product_class__name'
        ).annotate(
            total_target=Sum('target_amount')
        ).order_by('route_id')
        
        route_sales = tx_qs.values(
            'route_id', 
            'route__name',
            'route__warehouse_id',
            'route__warehouse__name',
            'product_class__name'
        ).annotate(
            total_sale=Sum('net_amount')
        )
        
        def empty_class_dict():
            return {
                'target': Decimal('0.00'),
                'net_amount': Decimal('0.00'),
                'difference': Decimal('0.00'),
                'scope': Decimal('0.00'),
                'scope_forecast': Decimal('0.00')
            }

        routes_data_dict = {}
        warehouse_map = {}
        
        for row in route_targets:
            rid = row['route_id']
            wid = row['warehouse_id']
            cname = (row['product_class__name'] or 'otros').lower()
            if cname not in self.display_classes: cname = 'otros'
            
            if wid not in warehouse_map: warehouse_map[wid] = row['warehouse__name']
            
            if rid not in routes_data_dict:
                routes_data_dict[rid] = {
                    'route_name': row['route__name'],
                    'warehouse_id': wid,
                    'classes': defaultdict(empty_class_dict)
                }
            routes_data_dict[rid]['classes'][cname]['target'] += (row['total_target'] or Decimal('0'))
            
        for row in route_sales:
            rid = row['route_id']
            wid = row['route__warehouse_id']
            cname = (row['product_class__name'] or 'otros').lower()
            if cname not in self.display_classes: cname = 'otros'
            
            if wid not in warehouse_map: warehouse_map[wid] = row['route__warehouse__name']
            
            if rid not in routes_data_dict:
                routes_data_dict[rid] = {
                    'route_name': row['route__name'],
                    'warehouse_id': wid,
                    'classes': defaultdict(empty_class_dict)
                }
            routes_data_dict[rid]['classes'][cname]['net_amount'] += (row['total_sale'] or Decimal('0'))

        warehouse_summaries = defaultdict(lambda: {
            'warehouse_id': '',
            'warehouse_name': '',
            'registered_customers': 0,
            'active_customers': 0,
            'portafolio_scope': 0,
            'new_customers': 0,
            'completed_product_classes': 0,
            'target': Decimal('0'),
            'net_amount': Decimal('0'),
            'difference': Decimal('0'),
            'scope': Decimal('0'),
            'scope_forecast': Decimal('0'),
            'classes': defaultdict(empty_class_dict),
            'routes_data': []
        })

        for rid, rdata in routes_data_dict.items():
            wid = rdata['warehouse_id']
            w_sum = warehouse_summaries[wid]
            w_sum['warehouse_name'] = warehouse_map[wid]
            
            c_info = route_customers_dict[rid]
            reg = c_info['registered']
            act = c_info['active']
            new = c_info['new']
            
            w_sum['registered_customers'] += reg
            w_sum['active_customers'] += act
            w_sum['new_customers'] += new
            
            r_target_total = Decimal('0')
            r_net_total = Decimal('0')
            completed_families = 0
            
            classes_breakdown = []
            
            for cname in self.display_classes:
                cdict = rdata['classes'][cname]
                wdict = w_sum['classes'][cname]
                
                target = cdict['target']
                net = cdict['net_amount']
                
                cdict['difference'] = target - net
                wdict['target'] += target
                wdict['net_amount'] += net
                wdict['difference'] += cdict['difference']
                
                if target > 0:
                    cdict['scope'] = (net / target) * 100
                else:
                    cdict['scope'] = Decimal('0.00')
                    
                proyeccion = (net / Decimal(elapsed_b_days_m1)) * Decimal(total_b_days)
                if target > 0:
                    cdict['scope_forecast'] = (proyeccion / target) * 100
                else:
                    cdict['scope_forecast'] = Decimal('0.00')
                    
                if cname in self.valid_classes:
                    if target > 0 and net >= target:
                        completed_families += 1
                        
                r_target_total += target
                r_net_total += net
                
                classes_breakdown.append({
                    'product_class_name': cname,
                    'target': target,
                    'net_amount': net,
                    'difference': cdict['difference'],
                    'scope': cdict['scope'],
                    'scope_forecast': cdict['scope_forecast']
                })
                
            diff = r_target_total - r_net_total
            if r_target_total > 0:
                scope = (r_net_total / r_target_total) * 100
            else:
                scope = Decimal('0.00')
                
            proyeccion_r = (r_net_total / Decimal(elapsed_b_days_m1)) * Decimal(total_b_days)
            if r_target_total > 0:
                scope_forecast = (proyeccion_r / r_target_total) * 100
            else:
                scope_forecast = Decimal('0.00')

            w_sum['target'] += r_target_total
            w_sum['net_amount'] += r_net_total
                
            port_scope = (act / reg * 100) if reg > 0 else 0
            
            w_sum['routes_data'].append({
                'route_id': rid,
                'route_name': rdata['route_name'],
                'registered_customers': reg,
                'active_customers': act,
                'portafolio_scope': port_scope,
                'new_customers': new,
                'completed_product_classes': completed_families,
                'target': r_target_total,
                'net_amount': r_net_total,
                'difference': diff,
                'scope': scope,
                'scope_forecast': scope_forecast,
                'route_product_classes_breakdown': classes_breakdown
            })

        final_data = []
        for wid, w_sum in warehouse_summaries.items():
            reg = w_sum['registered_customers']
            act = w_sum['active_customers']
            w_sum['portafolio_scope'] = (act / reg * 100) if reg > 0 else 0
            
            w_comp_fams = 0
            w_classes_breakdown = []
            
            for cname in self.display_classes:
                wdict = w_sum['classes'][cname]
                t = wdict['target']
                n = wdict['net_amount']
                if t > 0:
                    wdict['scope'] = (n / t) * 100
                else:
                    wdict['scope'] = Decimal('0.00')
                    
                p = (n / Decimal(elapsed_b_days_m1)) * Decimal(total_b_days)
                if t > 0:
                    wdict['scope_forecast'] = (p / t) * 100
                else:
                    wdict['scope_forecast'] = Decimal('0.00')
                    
                if cname in self.valid_classes:
                    if t > 0 and n >= t:
                        w_comp_fams += 1
                        
                w_classes_breakdown.append({
                    'product_class_name': cname,
                    'target': t,
                    'net_amount': n,
                    'difference': wdict['difference'],
                    'scope': wdict['scope'],
                    'scope_forecast': wdict['scope_forecast']
                })
                
            w_sum['completed_product_classes'] = w_comp_fams
            
            t_total = w_sum['target']
            n_total = w_sum['net_amount']
            w_sum['difference'] = t_total - n_total
            if t_total > 0:
                w_sum['scope'] = (n_total / t_total) * 100
            else:
                w_sum['scope'] = Decimal('0.00')
                
            p_total = (n_total / Decimal(elapsed_b_days_m1)) * Decimal(total_b_days)
            if t_total > 0:
                w_sum['scope_forecast'] = (p_total / t_total) * 100
            else:
                w_sum['scope_forecast'] = Decimal('0.00')
                
            routes = w_sum['routes_data']
            routes_by_scope = sorted(routes, key=lambda x: x['scope'], reverse=True)
            routes_by_sale = sorted(routes, key=lambda x: x['net_amount'], reverse=True)
            
            for rank, r in enumerate(routes_by_scope, start=1):
                r['rank_scope'] = rank
            for rank, r in enumerate(routes_by_sale, start=1):
                r['rank_sale'] = rank
                
            w_sum['routes_data'].sort(key=lambda x: int(x['route_id']) if str(x['route_id']).isdigit() else x['route_id'])
                
            final_data.append({
                'total_warehouse_data': {
                    'warehouse_id': wid,
                    'warehouse_name': w_sum['warehouse_name'],
                    'registered_customers': w_sum['registered_customers'],
                    'active_customers': w_sum['active_customers'],
                    'portafolio_scope': w_sum['portafolio_scope'],
                    'new_customers': w_sum['new_customers'],
                    'completed_product_classes': w_sum['completed_product_classes'],
                    'target': w_sum['target'],
                    'net_amount': w_sum['net_amount'],
                    'difference': w_sum['difference'],
                    'scope': w_sum['scope'],
                    'scope_forecast': w_sum['scope_forecast'],
                    'warehouse_product_classes_breakdown': w_classes_breakdown
                },
                'routes_data': w_sum['routes_data']
            })

        final_data.sort(key=lambda x: x['total_warehouse_data']['warehouse_name'])
        return final_data

    def export_report_data(self):
        import pandas as pd
        import io
        from django.db.models.functions import TruncMonth

        date_start_str = self.filters.get('sale_date_start')
        date_end_str = self.filters.get('sale_date_end')
        
        date_start_dt = None
        date_end_dt = None
        if date_start_str and date_end_str:
            date_start_dt = datetime.strptime(date_start_str, '%Y-%m-%d').date()
            date_end_dt = datetime.strptime(date_end_str, '%Y-%m-%d').date()

        tx_crud = SaleTransactionCRUD()
        tx_qs = tx_crud.read(self.allowed_routes, **self.filters)
        
        target_filters = self.filters.copy()
        if date_start_dt: target_filters['period_start'] = date_start_dt
        if date_end_dt: target_filters['period_end'] = date_end_dt
        if 'sale_date_start' in target_filters: del target_filters['sale_date_start']
        if 'sale_date_end' in target_filters: del target_filters['sale_date_end']
        
        target_crud = SaleTargetCRUD()
        target_qs = target_crud.read(self.allowed_routes, **target_filters)

        ventas_agrupadas = tx_qs.annotate(
            periodo=TruncMonth('sale_date')
        ).values(
            'route_id', 'product_class_id', 'periodo',
            'route__name', 'route__warehouse_id', 'product_class__name'
        ).annotate(
            venta_neta=Sum('net_amount')
        )

        cuotas_agrupadas = target_qs.annotate(
            periodo=TruncMonth('period')
        ).values(
            'route_id', 'product_class_id', 'periodo',
            'route__name', 'warehouse_id', 'product_class__name'
        ).annotate(
            cuota=Sum('target_amount')
        )

        consolidado = {}
        for v in ventas_agrupadas:
            key = (v['route_id'], v['product_class_id'], v['periodo'])
            consolidado[key] = {
                'ruta': v['route_id'],
                'agente': v['route__name'],
                'cedis ruta': v['route__warehouse_id'],
                'periodo': v['periodo'].strftime('%d/%m/%y') if v['periodo'] else '',
                'clase': v['product_class__name'],
                'cuota': Decimal('0'),
                'venta_neta': v['venta_neta'] or Decimal('0'),
            }

        for c in cuotas_agrupadas:
            key = (c['route_id'], c['product_class_id'], c['periodo'])
            if key not in consolidado:
                consolidado[key] = {
                    'ruta': c['route_id'],
                    'agente': c['route__name'],
                    'cedis ruta': c['warehouse_id'],
                    'periodo': c['periodo'].strftime('%d/%m/%y') if c['periodo'] else '',
                    'clase': c['product_class__name'],
                    'cuota': c['cuota'] or Decimal('0'),
                    'venta_neta': Decimal('0'),
                }
            else:
                consolidado[key]['cuota'] = c['cuota'] or Decimal('0')

        ventas_data = list(consolidado.values())
        ventas_data.sort(key=lambda x: (x['ruta'], x['clase']))
        df_ventas_final = pd.DataFrame(ventas_data)
        if df_ventas_final.empty:
            df_ventas_final = pd.DataFrame(columns=['ruta', 'agente', 'cedis ruta', 'periodo', 'clase', 'cuota', 'venta_neta'])

        customer_qs = Customer.objects.filter(route__in=self.allowed_routes)
        if date_end_dt:
            customer_qs = customer_qs.filter(registration_date__lte=date_end_dt)
            
        clientes_nuevos_q = Q(registration_date__gte=date_start_dt, registration_date__lte=date_end_dt) if (date_start_dt and date_end_dt) else Q()
        
        base_clientes = customer_qs.values('route_id').annotate(
            clientes_registrados=Count('id'),
            clientes_nuevos=Count('id', filter=clientes_nuevos_q)
        )
        
        consumo_clientes = tx_qs.values('route_id').annotate(
            clientes_con_consumo=Count('customer_id', distinct=True)
        )
        
        clientes_dict = {}
        for b in base_clientes:
            clientes_dict[b['route_id']] = {
                'ruta': b['route_id'],
                'clientes_registrados': b['clientes_registrados'],
                'clientes_con_consumo': 0,
                'efectividad_pct': 0.0,
                'clientes_nuevos': b['clientes_nuevos']
            }
            
        for c in consumo_clientes:
            if c['route_id'] in clientes_dict:
                clientes_dict[c['route_id']]['clientes_con_consumo'] = c['clientes_con_consumo']
                reg = clientes_dict[c['route_id']]['clientes_registrados']
                if reg > 0:
                    clientes_dict[c['route_id']]['efectividad_pct'] = round((c['clientes_con_consumo'] * 100.0) / reg, 1)

        clientes_data = list(clientes_dict.values())
        clientes_data.sort(key=lambda x: x['ruta'])
        df_clientes_final = pd.DataFrame(clientes_data)
        if df_clientes_final.empty:
            df_clientes_final = pd.DataFrame(columns=['ruta', 'clientes_registrados', 'clientes_con_consumo', 'efectividad_pct', 'clientes_nuevos'])

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_clientes_final.to_excel(writer, sheet_name='Cartera', index=False)
            df_ventas_final.to_excel(writer, sheet_name='Ventas y Cuotas', index=False)
            
        return output.getvalue()