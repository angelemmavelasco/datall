from django.db.models import Sum
from django.db.models.functions import ExtractYear
from django.core.paginator import Paginator
from apps.core.models import Product, ProductClass, Customer, Warehouse

class SalesBreakdownService:
    def __init__(self, queryset, dimension='customer_productclass_product'):
        self.queryset = queryset
        self.dimension = dimension
        # Obtener años únicos dinámicamente
        self.sorted_years = sorted(
            list(self.queryset.annotate(year=ExtractYear('sale_date'))
                 .values_list('year', flat=True)
                 .distinct())
        )
        if None in self.sorted_years:
            self.sorted_years.remove(None)
            
    def _init_annual_totals(self):
        return {y: 0.0 for y in self.sorted_years}

    def _flatten_annual_totals(self, totals_dict):
        return [totals_dict[y] for y in self.sorted_years]

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

    # ==============================================================================
    # 1. CLIENTE > LÍNEA > PRODUCTO
    # ==============================================================================
    def _get_customer_productclass_product(self, page_number):
        qs_with_year = self.queryset.annotate(year=ExtractYear('sale_date'))
        
        # Paginar Nivel 1
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
        ).annotate(total=Sum('net_amount')).order_by())
        
        # Diccionarios Nombres
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
            
            if c not in pivot_data:
                pivot_data[c] = {'t_o': 0, 'totals': self._init_annual_totals(), 'lines': {}}
            pivot_data[c]['t_o'] += t
            pivot_data[c]['totals'][y] += t
            
            if l not in pivot_data[c]['lines']:
                pivot_data[c]['lines'][l] = {'t_o': 0, 'totals': self._init_annual_totals(), 'products': {}}
            pivot_data[c]['lines'][l]['t_o'] += t
            pivot_data[c]['lines'][l]['totals'][y] += t
            
            if p not in pivot_data[c]['lines'][l]['products']:
                pivot_data[c]['lines'][l]['products'][p] = {'t_o': 0, 'totals': self._init_annual_totals()}
            pivot_data[c]['lines'][l]['products'][p]['t_o'] += t
            pivot_data[c]['lines'][l]['products'][p]['totals'][y] += t
            
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
                        for y in self.sorted_years:
                            o_t_p[y] += op_data['totals'][y]
                    final_pivot[c]['lines'][l]['products']['OTROS PRODUCTOS'] = self._flatten_annual_totals(o_t_p)
                    
        return final_pivot, self.sorted_years, page_obj

    # ==============================================================================
    # 2. LÍNEA > CLIENTE > PRODUCTO
    # ==============================================================================
    def _get_productclass_customer_product(self, page_number):
        qs_with_year = self.queryset.annotate(year=ExtractYear('sale_date'))
        
        l1_totals = qs_with_year.values('product_class_id').annotate(
            total_overall=Sum('net_amount')
        ).order_by('-total_overall')
        
        paginator = Paginator(l1_totals, 50)
        page_obj = paginator.get_page(page_number)
        if not page_obj.object_list: 
            return {}, self.sorted_years, page_obj
            
        top_l1_ids = [c['product_class_id'] for c in page_obj.object_list if c['product_class_id']]
        qs_page = qs_with_year.filter(product_class_id__in=top_l1_ids)
        
        data_list = list(qs_page.values(
            'product_class_id', 'customer_id', 'product_id', 'year'
        ).annotate(total=Sum('net_amount')).order_by())
        
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
            y = row['year']
            t = float(row['total'] or 0)
            
            if l not in pivot_data:
                pivot_data[l] = {'t_o': 0, 'totals': self._init_annual_totals(), 'customers': {}}
            pivot_data[l]['t_o'] += t
            pivot_data[l]['totals'][y] += t
            
            if c not in pivot_data[l]['customers']:
                pivot_data[l]['customers'][c] = {'t_o': 0, 'totals': self._init_annual_totals(), 'products': {}}
            pivot_data[l]['customers'][c]['t_o'] += t
            pivot_data[l]['customers'][c]['totals'][y] += t
            
            if p not in pivot_data[l]['customers'][c]['products']:
                pivot_data[l]['customers'][c]['products'][p] = {'t_o': 0, 'totals': self._init_annual_totals()}
            pivot_data[l]['customers'][c]['products'][p]['t_o'] += t
            pivot_data[l]['customers'][c]['products'][p]['totals'][y] += t
            
        final_pivot = {}
        TOP_C = 100
        TOP_P = 50
        
        for l, l_data in sorted(pivot_data.items(), key=lambda x: x[1]['t_o'], reverse=True):
            final_pivot[l] = {'totals': self._flatten_annual_totals(l_data['totals']), 'customers': {}}
            sorted_c = sorted(l_data['customers'].items(), key=lambda x: x[1]['t_o'], reverse=True)
            
            for c, c_data in sorted_c[:TOP_C]:
                final_pivot[l]['customers'][c] = {'totals': self._flatten_annual_totals(c_data['totals']), 'products': {}}
                sorted_p = sorted(c_data['products'].items(), key=lambda x: x[1]['t_o'], reverse=True)
                
                for p, p_totals in sorted_p[:TOP_P]:
                    final_pivot[l]['customers'][c]['products'][p] = self._flatten_annual_totals(p_totals['totals'])
                    
                otros_p = sorted_p[TOP_P:]
                if otros_p:
                    o_t_p = self._init_annual_totals()
                    for _, op_data in otros_p:
                        for y in self.sorted_years:
                            o_t_p[y] += op_data['totals'][y]
                    final_pivot[l]['customers'][c]['products']['OTROS PRODUCTOS'] = self._flatten_annual_totals(o_t_p)
                    
            otros_c = sorted_c[TOP_C:]
            if otros_c:
                o_t_c = self._init_annual_totals()
                for _, oc_data in otros_c:
                    for y in self.sorted_years:
                        o_t_c[y] += oc_data['totals'][y]
                final_pivot[l]['customers']['OTROS CLIENTES'] = {'totals': self._flatten_annual_totals(o_t_c), 'products': {}}
                
        return final_pivot, self.sorted_years, page_obj

    # ==============================================================================
    # 3. LÍNEA > PRODUCTO
    # ==============================================================================
    def _get_productclass_product(self, page_number):
        qs_with_year = self.queryset.annotate(year=ExtractYear('sale_date'))
        
        l1_totals = qs_with_year.values('product_class_id').annotate(
            total_overall=Sum('net_amount')
        ).order_by('-total_overall')
        
        paginator = Paginator(l1_totals, 50)
        page_obj = paginator.get_page(page_number)
        if not page_obj.object_list: 
            return {}, self.sorted_years, page_obj
            
        top_l1_ids = [c['product_class_id'] for c in page_obj.object_list if c['product_class_id']]
        qs_page = qs_with_year.filter(product_class_id__in=top_l1_ids)
        
        data_list = list(qs_page.values(
            'product_class_id', 'product_id', 'year'
        ).annotate(total=Sum('net_amount')).order_by())
        
        class_names = dict(ProductClass.objects.filter(id__in=top_l1_ids).values_list('id', 'name'))
        product_ids = list(set([row['product_id'] for row in data_list if row['product_id']]))
        product_names = dict(Product.objects.filter(id__in=product_ids).values_list('id', 'name'))
        
        pivot_data = {}
        for row in data_list:
            l = class_names.get(row['product_class_id']) or 'Sin línea'
            p = product_names.get(row['product_id']) or 'Sin producto'
            y = row['year']
            t = float(row['total'] or 0)
            
            if l not in pivot_data:
                pivot_data[l] = {'t_o': 0, 'totals': self._init_annual_totals(), 'products': {}}
            pivot_data[l]['t_o'] += t
            pivot_data[l]['totals'][y] += t
            
            if p not in pivot_data[l]['products']:
                pivot_data[l]['products'][p] = {'t_o': 0, 'totals': self._init_annual_totals()}
            pivot_data[l]['products'][p]['t_o'] += t
            pivot_data[l]['products'][p]['totals'][y] += t
            
        final_pivot = {}
        TOP_P = 100
        
        for l, l_data in sorted(pivot_data.items(), key=lambda x: x[1]['t_o'], reverse=True):
            final_pivot[l] = {'totals': self._flatten_annual_totals(l_data['totals']), 'products': {}}
            sorted_p = sorted(l_data['products'].items(), key=lambda x: x[1]['t_o'], reverse=True)
            
            for p, p_totals in sorted_p[:TOP_P]:
                final_pivot[l]['products'][p] = self._flatten_annual_totals(p_totals['totals'])
                
            otros_p = sorted_p[TOP_P:]
            if otros_p:
                o_t_p = self._init_annual_totals()
                for _, op_data in otros_p:
                    for y in self.sorted_years:
                        o_t_p[y] += op_data['totals'][y]
                final_pivot[l]['products']['OTROS PRODUCTOS'] = self._flatten_annual_totals(o_t_p)
                
        return final_pivot, self.sorted_years, page_obj

    # ==============================================================================
    # 4. GERENCIA (WAREHOUSE) > LÍNEA > PRODUCTO
    # ==============================================================================
    def _get_management_productclass_product(self, page_number):
        qs_with_year = self.queryset.annotate(year=ExtractYear('sale_date'))
        
        l1_totals = qs_with_year.values('warehouse_id').annotate(
            total_overall=Sum('net_amount')
        ).order_by('-total_overall')
        
        paginator = Paginator(l1_totals, 50)
        page_obj = paginator.get_page(page_number)
        if not page_obj.object_list: 
            return {}, self.sorted_years, page_obj
            
        top_l1_ids = [c['warehouse_id'] for c in page_obj.object_list if c['warehouse_id']]
        qs_page = qs_with_year.filter(warehouse_id__in=top_l1_ids)
        
        data_list = list(qs_page.values(
            'warehouse_id', 'product_class_id', 'product_id', 'year'
        ).annotate(total=Sum('net_amount')).order_by())
        
        mgt_names = dict(Warehouse.objects.filter(id__in=top_l1_ids).values_list('id', 'name'))
        class_ids = list(set([row['product_class_id'] for row in data_list if row['product_class_id']]))
        class_names = dict(ProductClass.objects.filter(id__in=class_ids).values_list('id', 'name'))
        product_ids = list(set([row['product_id'] for row in data_list if row['product_id']]))
        product_names = dict(Product.objects.filter(id__in=product_ids).values_list('id', 'name'))
        
        pivot_data = {}
        for row in data_list:
            mgt = mgt_names.get(row['warehouse_id']) or 'Sin Gerencia'
            l = class_names.get(row['product_class_id']) or 'Sin línea'
            p = product_names.get(row['product_id']) or 'Sin producto'
            y = row['year']
            t = float(row['total'] or 0)
            
            if mgt not in pivot_data:
                pivot_data[mgt] = {'t_o': 0, 'totals': self._init_annual_totals(), 'lines': {}}
            pivot_data[mgt]['t_o'] += t
            pivot_data[mgt]['totals'][y] += t
            
            if l not in pivot_data[mgt]['lines']:
                pivot_data[mgt]['lines'][l] = {'t_o': 0, 'totals': self._init_annual_totals(), 'products': {}}
            pivot_data[mgt]['lines'][l]['t_o'] += t
            pivot_data[mgt]['lines'][l]['totals'][y] += t
            
            if p not in pivot_data[mgt]['lines'][l]['products']:
                pivot_data[mgt]['lines'][l]['products'][p] = {'t_o': 0, 'totals': self._init_annual_totals()}
            pivot_data[mgt]['lines'][l]['products'][p]['t_o'] += t
            pivot_data[mgt]['lines'][l]['products'][p]['totals'][y] += t
            
        final_pivot = {}
        TOP_P = 100
        
        for mgt, m_data in sorted(pivot_data.items(), key=lambda x: x[1]['t_o'], reverse=True):
            final_pivot[mgt] = {'totals': self._flatten_annual_totals(m_data['totals']), 'lines': {}}
            for l, l_data in sorted(m_data['lines'].items(), key=lambda x: x[1]['t_o'], reverse=True):
                final_pivot[mgt]['lines'][l] = {'totals': self._flatten_annual_totals(l_data['totals']), 'products': {}}
                sorted_p = sorted(l_data['products'].items(), key=lambda x: x[1]['t_o'], reverse=True)
                
                for p, p_data in sorted_p[:TOP_P]:
                    final_pivot[mgt]['lines'][l]['products'][p] = self._flatten_annual_totals(p_data['totals'])
                    
                otros_p = sorted_p[TOP_P:]
                if otros_p:
                    o_t_p = self._init_annual_totals()
                    for _, op_data in otros_p:
                        for y in self.sorted_years:
                            o_t_p[y] += op_data['totals'][y]
                    final_pivot[mgt]['lines'][l]['products']['OTROS PRODUCTOS'] = self._flatten_annual_totals(o_t_p)
                    
        return final_pivot, self.sorted_years, page_obj

    # ==============================================================================
    # 5. PRODUCTO > CLIENTE
    # ==============================================================================
    def _get_product_customer(self, page_number):
        qs_with_year = self.queryset.annotate(year=ExtractYear('sale_date'))
        
        l1_totals = qs_with_year.values('product_id').annotate(
            total_overall=Sum('net_amount')
        ).order_by('-total_overall')
        
        paginator = Paginator(l1_totals, 50)
        page_obj = paginator.get_page(page_number)
        if not page_obj.object_list: 
            return {}, self.sorted_years, page_obj
            
        top_p_ids = [c['product_id'] for c in page_obj.object_list if c['product_id']]
        qs_page = qs_with_year.filter(product_id__in=top_p_ids)
        
        data_list = list(qs_page.values(
            'product_id', 'customer_id', 'year'
        ).annotate(total=Sum('net_amount')).order_by())
        
        product_names = dict(Product.objects.filter(id__in=top_p_ids).values_list('id', 'name'))
        customer_ids = list(set([row['customer_id'] for row in data_list if row['customer_id']]))
        customer_names = dict(Customer.objects.filter(id__in=customer_ids).values_list('id', 'name'))
        
        pivot_data = {}
        for row in data_list:
            p = product_names.get(row['product_id']) or 'Sin producto'
            c = customer_names.get(row['customer_id']) or 'Sin cliente'
            y = row['year']
            t = float(row['total'] or 0)
            
            if p not in pivot_data:
                pivot_data[p] = {'t_o': 0, 'totals': self._init_annual_totals(), 'customers': {}}
            pivot_data[p]['t_o'] += t
            pivot_data[p]['totals'][y] += t
            
            if c not in pivot_data[p]['customers']:
                pivot_data[p]['customers'][c] = {'t_o': 0, 'totals': self._init_annual_totals()}
            pivot_data[p]['customers'][c]['t_o'] += t
            pivot_data[p]['customers'][c]['totals'][y] += t
            
        final_pivot = {}
        TOP_C = 100
        
        for p, p_data in sorted(pivot_data.items(), key=lambda x: x[1]['t_o'], reverse=True):
            final_pivot[p] = {'totals': self._flatten_annual_totals(p_data['totals']), 'customers': {}}
            sorted_c = sorted(p_data['customers'].items(), key=lambda x: x[1]['t_o'], reverse=True)
            
            for c, c_totals in sorted_c[:TOP_C]:
                final_pivot[p]['customers'][c] = self._flatten_annual_totals(c_totals['totals'])
                
            otros_c = sorted_c[TOP_C:]
            if otros_c:
                o_t_c = self._init_annual_totals()
                for _, oc_data in otros_c:
                    for y in self.sorted_years:
                        o_t_c[y] += oc_data['totals'][y]
                final_pivot[p]['customers']['OTROS CLIENTES'] = self._flatten_annual_totals(o_t_c)
                
        return final_pivot, self.sorted_years, page_obj
