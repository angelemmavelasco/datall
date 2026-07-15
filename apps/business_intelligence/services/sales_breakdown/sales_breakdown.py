from django.db.models import Sum
from django.db.models.functions import ExtractYear
from asgiref.sync import sync_to_async
from django.core.paginator import Paginator
from apps.core.models import Product, ProductClass, Customer, Warehouse

import csv
import io

class SalesBreakdownService:
    def __init__(self, queryset, dimension='customer_productclass_product'):
        self.queryset = queryset
        self.dimension = dimension
        self.sorted_years = sorted(
            list(self.queryset.annotate(year=ExtractYear('sale_date'))
                 .values_list('year', flat=True)
                 .distinct())
        )
        if None in self.sorted_years:
            self.sorted_years.remove(None)
            
    def _init_annual_totals(self):
        return {y: {'net': 0.0, 'profit': 0.0} for y in self.sorted_years}

    def _add_annual_totals(self, target, source):
        for y in self.sorted_years:
            target[y]['net'] += source[y]['net']
            target[y]['profit'] += source[y]['profit']

    def _flatten_annual_totals(self, totals_dict):
        result = []
        prev_net = None
        
        for y in self.sorted_years:
            net = totals_dict[y]['net']
            profit = totals_dict[y]['profit']
            
            margin = (profit / net * 100) if net > 0 else 0.0
            if prev_net is not None and prev_net > 0:
                growth = ((net - prev_net) / prev_net * 100)
            else:
                growth = 0.0
                
            result.append({
                'year': y,
                'net': round(net, 2),
                'margin': round(margin, 2),
                'growth': round(growth, 2)
            })
            
            prev_net = net
            
        return result

    def get_data(self, page_number=1):
        if self.dimension == 'customer_productclass_product':
            return self._get_customer_productclass_product(page_number)
        elif self.dimension == 'productclass_customer_product':
            return self._get_productclass_customer_product(page_number)
        elif self.dimension == 'productclass_product':
            return self._get_productclass_product(page_number)
        elif self.dimension == 'management_productclass_product':
            return self._get_management_productclass_product(page_number)
        elif self.dimension == 'product_customer':
            return self._get_product_customer(page_number)
        else:
            return {}, self.sorted_years, None

    def _get_customer_productclass_product(self, page_number):
        qs_with_year = self.queryset.annotate(year=ExtractYear('sale_date'))
        
        l1_totals = qs_with_year.values('customer_id').annotate(
            total_overall=Sum('net_amount')
        ).order_by('-total_overall')
        
        paginator = Paginator(l1_totals, 50)
        page_obj = paginator.get_page(page_number)
        if not page_obj.object_list: 
            return {}, self.sorted_years, page_obj
            
        top_c_ids = [c['customer_id'] for c in page_obj.object_list if c['customer_id']]
        qs_page = qs_with_year.filter(customer_id__in=top_c_ids)
        
        data_list = list(qs_page.values(
            'customer_id', 'product_class_id', 'product_id', 'year'
        ).annotate(
            total=Sum('net_amount'),
            total_profit=Sum('profit')
        ).order_by())
        
        customer_names = dict(Customer.objects.filter(id__in=top_c_ids).values_list('id', 'name'))
        class_ids = list(set([row['product_class_id'] for row in data_list if row['product_class_id']]))
        class_names = dict(ProductClass.objects.filter(id__in=class_ids).values_list('id', 'name'))
        product_ids = list(set([row['product_id'] for row in data_list if row['product_id']]))
        product_names = dict(Product.objects.filter(id__in=product_ids).values_list('id', 'name'))
        
        pivot_data = {}
        for row in data_list:
            c = customer_names.get(row['customer_id']) or 'Sin cliente'
            l = class_names.get(row['product_class_id']) or 'Sin línea'
            p = product_names.get(row['product_id']) or 'Sin producto'
            y = row['year']
            t = float(row['total'] or 0)
            pr = float(row['total_profit'] or 0)
            
            if c not in pivot_data:
                pivot_data[c] = {'t_o': 0, 'totals': self._init_annual_totals(), 'lines': {}}
            pivot_data[c]['t_o'] += t
            pivot_data[c]['totals'][y]['net'] += t
            pivot_data[c]['totals'][y]['profit'] += pr
            
            if l not in pivot_data[c]['lines']:
                pivot_data[c]['lines'][l] = {'t_o': 0, 'totals': self._init_annual_totals(), 'products': {}}
            pivot_data[c]['lines'][l]['t_o'] += t
            pivot_data[c]['lines'][l]['totals'][y]['net'] += t
            pivot_data[c]['lines'][l]['totals'][y]['profit'] += pr
            
            if p not in pivot_data[c]['lines'][l]['products']:
                pivot_data[c]['lines'][l]['products'][p] = {'t_o': 0, 'totals': self._init_annual_totals()}
            pivot_data[c]['lines'][l]['products'][p]['t_o'] += t
            pivot_data[c]['lines'][l]['products'][p]['totals'][y]['net'] += t
            pivot_data[c]['lines'][l]['products'][p]['totals'][y]['profit'] += pr
            
        final_pivot = {}
        TOP_L = 100
        TOP_P = 50
        
        for c, c_data in sorted(pivot_data.items(), key=lambda x: x[1]['t_o'], reverse=True):
            final_pivot[c] = {'totals': self._flatten_annual_totals(c_data['totals']), 'lines': {}}
            sorted_l = sorted(c_data['lines'].items(), key=lambda x: x[1]['t_o'], reverse=True)
            
            for l, l_data in sorted_l[:TOP_L]:
                final_pivot[c]['lines'][l] = {'totals': self._flatten_annual_totals(l_data['totals']), 'products': {}}
                sorted_p = sorted(l_data['products'].items(), key=lambda x: x[1]['t_o'], reverse=True)
                
                for p, p_data in sorted_p[:TOP_P]:
                    final_pivot[c]['lines'][l]['products'][p] = self._flatten_annual_totals(p_data['totals'])
                    
                otros_p = sorted_p[TOP_P:]
                if otros_p:
                    o_t_p = self._init_annual_totals()
                    for _, op_data in otros_p:
                        self._add_annual_totals(o_t_p, op_data['totals'])
                    final_pivot[c]['lines'][l]['products']['OTROS PRODUCTOS'] = self._flatten_annual_totals(o_t_p)
                    
        return final_pivot, self.sorted_years, page_obj, 'cliente -> clase de producto -> producto'


    def _get_productclass_customer_product(self, page_number):
        qs_with_year = self.queryset.annotate(year=ExtractYear('sale_date'))
        
        l1_totals = qs_with_year.values('product_class_id').annotate(total_overall=Sum('net_amount')).order_by('-total_overall')
        paginator = Paginator(l1_totals, 50)
        page_obj = paginator.get_page(page_number)
        if not page_obj.object_list: return {}, self.sorted_years, page_obj
            
        top_l1_ids = [c['product_class_id'] for c in page_obj.object_list if c['product_class_id']]
        data_list = list(qs_with_year.filter(product_class_id__in=top_l1_ids).values(
            'product_class_id', 'customer_id', 'product_id', 'year'
        ).annotate(total=Sum('net_amount'), total_profit=Sum('profit')).order_by())
        
        class_names = dict(ProductClass.objects.filter(id__in=top_l1_ids).values_list('id', 'name'))
        customer_ids = list(set([row['customer_id'] for row in data_list if row['customer_id']]))
        customer_names = dict(Customer.objects.filter(id__in=customer_ids).values_list('id', 'name'))
        product_ids = list(set([row['product_id'] for row in data_list if row['product_id']]))
        product_names = dict(Product.objects.filter(id__in=product_ids).values_list('id', 'name'))
        
        pivot_data = {}
        for row in data_list:
            l = class_names.get(row['product_class_id']) or 'Sin línea'
            c = customer_names.get(row['customer_id']) or 'Sin cliente'
            p = product_names.get(row['product_id']) or 'Sin producto'
            y, t, pr = row['year'], float(row['total'] or 0), float(row['total_profit'] or 0)
            
            if l not in pivot_data: pivot_data[l] = {'t_o': 0, 'totals': self._init_annual_totals(), 'customers': {}}
            pivot_data[l]['t_o'] += t
            pivot_data[l]['totals'][y]['net'] += t; pivot_data[l]['totals'][y]['profit'] += pr
            
            if c not in pivot_data[l]['customers']: pivot_data[l]['customers'][c] = {'t_o': 0, 'totals': self._init_annual_totals(), 'products': {}}
            pivot_data[l]['customers'][c]['t_o'] += t
            pivot_data[l]['customers'][c]['totals'][y]['net'] += t; pivot_data[l]['customers'][c]['totals'][y]['profit'] += pr
            
            if p not in pivot_data[l]['customers'][c]['products']: pivot_data[l]['customers'][c]['products'][p] = {'t_o': 0, 'totals': self._init_annual_totals()}
            pivot_data[l]['customers'][c]['products'][p]['t_o'] += t
            pivot_data[l]['customers'][c]['products'][p]['totals'][y]['net'] += t; pivot_data[l]['customers'][c]['products'][p]['totals'][y]['profit'] += pr
            
        final_pivot = {}
        TOP_C, TOP_P = 100, 50
        
        for l, l_data in sorted(pivot_data.items(), key=lambda x: x[1]['t_o'], reverse=True):
            final_pivot[l] = {'totals': self._flatten_annual_totals(l_data['totals']), 'customers': {}}
            sorted_c = sorted(l_data['customers'].items(), key=lambda x: x[1]['t_o'], reverse=True)
            
            for c, c_data in sorted_c[:TOP_C]:
                final_pivot[l]['customers'][c] = {'totals': self._flatten_annual_totals(c_data['totals']), 'products': {}}
                sorted_p = sorted(c_data['products'].items(), key=lambda x: x[1]['t_o'], reverse=True)
                for p, p_totals in sorted_p[:TOP_P]: final_pivot[l]['customers'][c]['products'][p] = self._flatten_annual_totals(p_totals['totals'])
                
                otros_p = sorted_p[TOP_P:]
                if otros_p:
                    o_t_p = self._init_annual_totals()
                    for _, op_data in otros_p: self._add_annual_totals(o_t_p, op_data['totals'])
                    final_pivot[l]['customers'][c]['products']['OTROS PRODUCTOS'] = self._flatten_annual_totals(o_t_p)
                    
            otros_c = sorted_c[TOP_C:]
            if otros_c:
                o_t_c = self._init_annual_totals()
                for _, oc_data in otros_c: self._add_annual_totals(o_t_c, oc_data['totals'])
                final_pivot[l]['customers']['OTROS CLIENTES'] = {'totals': self._flatten_annual_totals(o_t_c), 'products': {}}
                
        return final_pivot, self.sorted_years, page_obj, 'clase de producto -> cliente -> producto'

    def _get_productclass_product(self, page_number):
        qs_with_year = self.queryset.annotate(year=ExtractYear('sale_date'))
        
        l1_totals = qs_with_year.values('product_class_id').annotate(total_overall=Sum('net_amount')).order_by('-total_overall')
        paginator = Paginator(l1_totals, 50)
        page_obj = paginator.get_page(page_number)
        if not page_obj.object_list: return {}, self.sorted_years, page_obj
            
        top_l1_ids = [c['product_class_id'] for c in page_obj.object_list if c['product_class_id']]
        data_list = list(qs_with_year.filter(product_class_id__in=top_l1_ids).values(
            'product_class_id', 'product_id', 'year'
        ).annotate(total=Sum('net_amount'), total_profit=Sum('profit')).order_by())
        
        class_names = dict(ProductClass.objects.filter(id__in=top_l1_ids).values_list('id', 'name'))
        product_ids = list(set([row['product_id'] for row in data_list if row['product_id']]))
        product_names = dict(Product.objects.filter(id__in=product_ids).values_list('id', 'name'))
        
        pivot_data = {}
        for row in data_list:
            l = class_names.get(row['product_class_id']) or 'Sin línea'
            p = product_names.get(row['product_id']) or 'Sin producto'
            y, t, pr = row['year'], float(row['total'] or 0), float(row['total_profit'] or 0)
            
            if l not in pivot_data: pivot_data[l] = {'t_o': 0, 'totals': self._init_annual_totals(), 'products': {}}
            pivot_data[l]['t_o'] += t
            pivot_data[l]['totals'][y]['net'] += t; pivot_data[l]['totals'][y]['profit'] += pr
            
            if p not in pivot_data[l]['products']: pivot_data[l]['products'][p] = {'t_o': 0, 'totals': self._init_annual_totals()}
            pivot_data[l]['products'][p]['t_o'] += t
            pivot_data[l]['products'][p]['totals'][y]['net'] += t; pivot_data[l]['products'][p]['totals'][y]['profit'] += pr
            
        final_pivot = {}
        TOP_P = 100
        
        for l, l_data in sorted(pivot_data.items(), key=lambda x: x[1]['t_o'], reverse=True):
            final_pivot[l] = {'totals': self._flatten_annual_totals(l_data['totals']), 'products': {}}
            sorted_p = sorted(l_data['products'].items(), key=lambda x: x[1]['t_o'], reverse=True)
            for p, p_totals in sorted_p[:TOP_P]: final_pivot[l]['products'][p] = self._flatten_annual_totals(p_totals['totals'])
            otros_p = sorted_p[TOP_P:]
            if otros_p:
                o_t_p = self._init_annual_totals()
                for _, op_data in otros_p: self._add_annual_totals(o_t_p, op_data['totals'])
                final_pivot[l]['products']['OTROS PRODUCTOS'] = self._flatten_annual_totals(o_t_p)
                
        return final_pivot, self.sorted_years, page_obj, 'clase de producto -> producto'

    def _get_management_productclass_product(self, page_number):
        qs_with_year = self.queryset.annotate(year=ExtractYear('sale_date'))
        
        l1_totals = qs_with_year.values('route__warehouse_id').annotate(total_overall=Sum('net_amount')).order_by('-total_overall')
        paginator = Paginator(l1_totals, 50)
        page_obj = paginator.get_page(page_number)
        if not page_obj.object_list: return {}, self.sorted_years, page_obj
            
        top_l1_ids = [c['route__warehouse_id'] for c in page_obj.object_list if c['route__warehouse_id']]
        data_list = list(qs_with_year.filter(route__warehouse_id__in=top_l1_ids).values(
            'route__warehouse_id', 'product_class_id', 'product_id', 'year'
        ).annotate(total=Sum('net_amount'), total_profit=Sum('profit')).order_by())
        
        mgt_names = dict(Warehouse.objects.filter(id__in=top_l1_ids).values_list('id', 'name'))
        class_ids = list(set([row['product_class_id'] for row in data_list if row['product_class_id']]))
        class_names = dict(ProductClass.objects.filter(id__in=class_ids).values_list('id', 'name'))
        product_ids = list(set([row['product_id'] for row in data_list if row['product_id']]))
        product_names = dict(Product.objects.filter(id__in=product_ids).values_list('id', 'name'))
        
        pivot_data = {}
        for row in data_list:
            mgt = mgt_names.get(row['route__warehouse_id']) or 'Sin Gerencia'
            l = class_names.get(row['product_class_id']) or 'Sin línea'
            p = product_names.get(row['product_id']) or 'Sin producto'
            y, t, pr = row['year'], float(row['total'] or 0), float(row['total_profit'] or 0)
            
            if mgt not in pivot_data: pivot_data[mgt] = {'t_o': 0, 'totals': self._init_annual_totals(), 'lines': {}}
            pivot_data[mgt]['t_o'] += t
            pivot_data[mgt]['totals'][y]['net'] += t; pivot_data[mgt]['totals'][y]['profit'] += pr
            
            if l not in pivot_data[mgt]['lines']: pivot_data[mgt]['lines'][l] = {'t_o': 0, 'totals': self._init_annual_totals(), 'products': {}}
            pivot_data[mgt]['lines'][l]['t_o'] += t
            pivot_data[mgt]['lines'][l]['totals'][y]['net'] += t; pivot_data[mgt]['lines'][l]['totals'][y]['profit'] += pr
            
            if p not in pivot_data[mgt]['lines'][l]['products']: pivot_data[mgt]['lines'][l]['products'][p] = {'t_o': 0, 'totals': self._init_annual_totals()}
            pivot_data[mgt]['lines'][l]['products'][p]['t_o'] += t
            pivot_data[mgt]['lines'][l]['products'][p]['totals'][y]['net'] += t; pivot_data[mgt]['lines'][l]['products'][p]['totals'][y]['profit'] += pr
            
        final_pivot = {}
        TOP_P = 100
        for mgt, m_data in sorted(pivot_data.items(), key=lambda x: x[1]['t_o'], reverse=True):
            final_pivot[mgt] = {'totals': self._flatten_annual_totals(m_data['totals']), 'lines': {}}
            for l, l_data in sorted(m_data['lines'].items(), key=lambda x: x[1]['t_o'], reverse=True):
                final_pivot[mgt]['lines'][l] = {'totals': self._flatten_annual_totals(l_data['totals']), 'products': {}}
                sorted_p = sorted(l_data['products'].items(), key=lambda x: x[1]['t_o'], reverse=True)
                for p, p_data in sorted_p[:TOP_P]: final_pivot[mgt]['lines'][l]['products'][p] = self._flatten_annual_totals(p_data['totals'])
                
                otros_p = sorted_p[TOP_P:]
                if otros_p:
                    o_t_p = self._init_annual_totals()
                    for _, op_data in otros_p: self._add_annual_totals(o_t_p, op_data['totals'])
                    final_pivot[mgt]['lines'][l]['products']['OTROS PRODUCTOS'] = self._flatten_annual_totals(o_t_p)
        return final_pivot, self.sorted_years, page_obj, 'gerencia -> clase de producto -> producto'


    def _get_product_customer(self, page_number):
        qs_with_year = self.queryset.annotate(year=ExtractYear('sale_date'))
        
        l1_totals = qs_with_year.values('product_id').annotate(total_overall=Sum('net_amount')).order_by('-total_overall')
        paginator = Paginator(l1_totals, 50)
        page_obj = paginator.get_page(page_number)
        if not page_obj.object_list: return {}, self.sorted_years, page_obj
            
        top_p_ids = [c['product_id'] for c in page_obj.object_list if c['product_id']]
        data_list = list(qs_with_year.filter(product_id__in=top_p_ids).values(
            'product_id', 'customer_id', 'year'
        ).annotate(total=Sum('net_amount'), total_profit=Sum('profit')).order_by())
        
        product_names = dict(Product.objects.filter(id__in=top_p_ids).values_list('id', 'name'))
        customer_ids = list(set([row['customer_id'] for row in data_list if row['customer_id']]))
        customer_names = dict(Customer.objects.filter(id__in=customer_ids).values_list('id', 'name'))
        
        pivot_data = {}
            
        for row in data_list:
            p = product_names.get(row['product_id']) or 'Sin producto'
            c = customer_names.get(row['customer_id']) or 'Sin cliente'
            y, t, pr = row['year'], float(row['total'] or 0), float(row['total_profit'] or 0)
            
            if p not in pivot_data: pivot_data[p] = {'t_o': 0, 'totals': self._init_annual_totals(), 'customers': {}}
            pivot_data[p]['t_o'] += t
            pivot_data[p]['totals'][y]['net'] += t; pivot_data[p]['totals'][y]['profit'] += pr
            if c not in pivot_data[p]['customers']: pivot_data[p]['customers'][c] = {'t_o': 0, 'totals': self._init_annual_totals()}
            pivot_data[p]['customers'][c]['t_o'] += t
            pivot_data[p]['customers'][c]['totals'][y]['net'] += t; pivot_data[p]['customers'][c]['totals'][y]['profit'] += pr
            
        final_pivot = {}
        TOP_C = 100
        for p, p_data in sorted(pivot_data.items(), key=lambda x: x[1]['t_o'], reverse=True):
            final_pivot[p] = {'totals': self._flatten_annual_totals(p_data['totals']), 'customers': {}}
            sorted_c = sorted(p_data['customers'].items(), key=lambda x: x[1]['t_o'], reverse=True)
            for c, c_totals in sorted_c[:TOP_C]: final_pivot[p]['customers'][c] = self._flatten_annual_totals(c_totals['totals'])
                
            otros_c = sorted_c[TOP_C:]
            if otros_c:
                o_t_c = self._init_annual_totals()
                for _, oc_data in otros_c: self._add_annual_totals(o_t_c, oc_data['totals'])
                final_pivot[p]['customers']['OTROS CLIENTES'] = self._flatten_annual_totals(o_t_c)
        return final_pivot, self.sorted_years, page_obj, 'producto -> cliente'

    
    def get_report_data(self):
        output = io.StringIO()
        writer = csv.writer(output)
        
        dimension_config = {
            'customer_productclass_product': {
                'fields': ['customer__id', 'customer__name', 'customer__route_id', 'product_class__name', 'product__id', 'product__name'],
                'headers': ['ID cliente', 'Nombre Cliente', 'Ruta', 'Línea', 'Producto']
            },
            'productclass_customer_product': {
                'fields': ['product_class__name', 'customer__id', 'customer__name', 'customer__route_id', 'product__id', 'product__name'],
                'headers': ['Línea', 'ID cliente', 'Nombre Cliente', 'Ruta', 'Producto']
            },
            'productclass_product': {
                'fields': ['product_class__name', 'product__id', 'product__name'],
                'headers': ['Línea', 'Producto']
            },
            'management_productclass_product': {
                'fields': ['route__warehouse__name', 'product_class__name', 'product__id', 'product__name'],
                'headers': ['Gerencia', 'Línea', 'Producto']
            },
            'product_customer': {
                'fields': ['product__id', 'product__name', 'customer__id', 'customer__name', 'customer__route_id'],
                'headers': ['Producto', 'ID cliente', 'Nombre Cliente', 'Ruta']
            }
        }
        
        config = dimension_config.get(self.dimension, dimension_config['customer_productclass_product'])
        
        writer.writerow(config['headers'] + ['Año', 'Venta Neta', 'Margen (%)', 'Crecimiento (%)'])

        export_qs = self.queryset.values(*config['fields']).annotate(
            year=ExtractYear('sale_date'), 
            total=Sum('net_amount'),
            total_profit=Sum('profit')
        ).order_by().iterator(chunk_size=2000)
        
        grouped_data = {}
        for row in export_qs:
            key = tuple(row.get(f) for f in config['fields'])
            
            if key not in grouped_data:
                grouped_data[key] = self._init_annual_totals()
                
            year = row.get('year')
            if year in self.sorted_years:
                grouped_data[key][year]['net'] += float(row.get('total') or 0)
                grouped_data[key][year]['profit'] += float(row.get('total_profit') or 0)
                
        for key, totals_dict in grouped_data.items():
            row_dict = dict(zip(config['fields'], key))
            
            c_id = row_dict.get('customer__id')
            c_name = row_dict.get('customer__name')
            c_route = row_dict.get('customer__route_id')
            
            c_id_str = str(c_id) if c_id else 'Sin ID'
            c_name_str = str(c_name) if c_name else 'Sin Cliente'
            c_route_str = str(c_route) if c_route else 'Sin Ruta'
            
            p_id = row_dict.get('product__id')
            p_name = row_dict.get('product__name')
            p = f"{p_id} - {p_name}".strip(" -") if p_id or p_name else 'Sin Producto'
            
            l = row_dict.get('product_class__name') or 'Sin Línea'
            w = row_dict.get('route__warehouse__name') or 'Sin Gerencia'
            
            out_base = []
            if self.dimension == 'customer_productclass_product':
                out_base.extend([c_id_str, c_name_str, c_route_str, l, p])
            elif self.dimension == 'productclass_customer_product':
                out_base.extend([l, c_id_str, c_name_str, c_route_str, p])
            elif self.dimension == 'productclass_product':
                out_base.extend([l, p])
            elif self.dimension == 'management_productclass_product':
                out_base.extend([w, l, p])
            elif self.dimension == 'product_customer':
                out_base.extend([p, c_id_str, c_name_str, c_route_str])
            else:
                out_base.extend([c_id_str, c_name_str, c_route_str, l, p])

            flattened_totals = self._flatten_annual_totals(totals_dict)
            
            for y_data in flattened_totals:
                if y_data['net'] != 0 or y_data['margin'] != 0 or y_data['growth'] != 0:
                    writer.writerow(out_base + [y_data['year'], y_data['net'], y_data['margin'], y_data['growth']])
                    
        return output.getvalue()