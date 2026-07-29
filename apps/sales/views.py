# pyrefly: ignore [missing-import]
from django.contrib import messages
# pyrefly: ignore [missing-import]
from django.shortcuts import render, redirect
from apps.sales.services.products.products_crud import ProductsCrud
from django.contrib.auth.decorators import login_required
from apps.data_admin.services.data_history.data_history_crud import ActivityLogger
from apps.core.models import Reference, ProductClass, Warehouse, Route, ProductCategory, SystemModule
from django.core.paginator import Paginator
import pandas as pd
import io
from apps.core.utils import get_allowed_routes_for_user
from apps.sales.services.sale_transactions.sale_transactions_crud import SaleTransactionCRUD
from django.http import HttpResponse
from asgiref.sync import sync_to_async
import datetime
import calendar
from django.db.models import Sum
from decimal import Decimal
from django.conf import settings

#services
from .services.routes_service import RoutesService


@login_required
def products(request):
    template = 'sales/products/products.html'

    product_classes = request.GET.getlist('product_classes')
    query_text = request.GET.get('query_text')

    filters = {}
    if product_classes: filters['product_classes'] = product_classes
    if query_text: filters['query_text'] = query_text

    products_service = ProductsCrud()
    qs = products_service.read(**filters)

    paginator = Paginator(qs, 100)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'products': page_obj.object_list,
        'page_obj': page_obj,
        'filter_product_classes': ProductClass.objects.all().order_by('name'),
        'selected_product_classes': product_classes,
        'query_text': query_text or '',
    }

    if request.htmx:
        template = 'sales/products/partials/product_rows.html'
    else:
        module = SystemModule.objects.filter(url_name='sales:products').first()
        ActivityLogger.log_read(
            user=request.user,
            module=module,
            description='visualización del listado de productos',
            metadata={'filters': filters}
        )
        
    return render(request, template, context)

@login_required
def products_export(request):
    product_classes = request.GET.getlist('product_classes')
    query_text = request.GET.get('query_text')

    filters = {}
    if product_classes: filters['product_classes'] = product_classes
    if query_text: filters['query_text'] = query_text

    products_service = ProductsCrud()
    qs = products_service.read(**filters)

    data = []
    for product in qs:
        data.append({
            'ID': product.id.upper() if product.id else '',
            'Nombre': product.name.title() if product.name else '-',
            'Código de barras': product.barcode if product.barcode else 'No asignado',
            'Precio': product.price if product.price is not None else 0.0,
            'Costo': product.cost if product.cost is not None else 0.0,
            'Unidad de medida': product.unit_of_measure.title() if product.unit_of_measure else '-',
            'Clase': product.product_class.name.title() if product.product_class and product.product_class.name else '-',
            'Categoría': product.product_class.product_category.name.title() if product.product_class and product.product_class.product_category and product.product_class.product_category.name else '-',
        })

    df = pd.DataFrame(data)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Productos')

    output.seek(0)
    
    module = SystemModule.objects.filter(url_name='sales:products').first()
    ActivityLogger.log_download(
        user=request.user,
        module=module,
        description='descarga del listado de productos en Excel',
        metadata={'filters': filters}
    )

    response = HttpResponse(
        output,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename=productos.xlsx'
    return response

@login_required
def product(request, product_id: str):
    TEMPLATE = 'sales/products/product.html'
    products_service = ProductsCrud()
    product = products_service.get_by_id(product_id=product_id)

    context = {
        'product': product
    }

    module = SystemModule.objects.filter(url_name='sales:products').first()
    ActivityLogger.log_read(
        user=request.user,
        module=module,
        obj=product,
        description=f'visualización de detalle del producto {product.name}' if product else 'visualización de detalle de producto'
    )

    return render(request, TEMPLATE, context)


@login_required
def stock_transfers(request):
    if request.method == 'POST' and request.headers.get('HX-Request'):
        action = request.POST.get('action')
        if action == 'calculate-transfer':
            from apps.sales.services.stock_transfers.calculator import StockTransferCalculatorService
            
            origin = request.POST.get('warehouse_origin')
            destination = request.POST.get('warehouse_destination')
            start_date = request.POST.get('start_date')
            end_date = request.POST.get('end_date')
            
            # Using getlist for multiselect, although in template it's a single select currently,
            # but user said "el usuario puede decidir si solo de una clase o todas, por lo tanto, esto tiene que ser multiselect".
            # We will use getlist to support it if it becomes a multiple select.
            product_classes = request.POST.getlist('product_classes')
            rotation_levels = request.POST.getlist('rotation_levels')
            
            service = StockTransferCalculatorService(
                origin_warehouse_id=origin,
                destination_warehouse_id=destination,
                product_class_ids=product_classes,
                rotation_level_ids=rotation_levels
            )
            
            results = service.calculate_transfer(start_date, end_date)
            
            # optional logging
            module = SystemModule.objects.filter(url_name='sales:stock_transfers').first()
            if module:
                ActivityLogger.log_read(
                    user=request.user,
                    module=module,
                    description='cálculo de transferencias de stock',
                    metadata={'origin': origin, 'destination': destination}
                )
                
            return render(request, 'sales/stock_transfers/partials/transfer_results.html', {
                'results': results,
                'errors': service.errors
            })

    template = 'sales/stock_transfers/stock_transfers.html'
    warehouses = Warehouse.objects.all().exclude(id__in = ['cdmx1','cdmx2']).order_by('name')
    product_classes = ProductClass.objects.all().order_by('name')
    context = {
        'warehouses': warehouses,
        'product_classes': product_classes,
    }
    return render(request, template, context)

@login_required
async def export_stock_transfer_data(request):
    req_data = request.POST if request.method == 'POST' else request.GET
    
    origin = req_data.get('warehouse_origin')
    destination = req_data.get('warehouse_destination')
    start_date = req_data.get('start_date')
    end_date = req_data.get('end_date')
    
    product_classes = req_data.getlist('product_classes')
    rotation_levels = req_data.getlist('rotation_levels')
    
    coverages = {}
    for key, value in req_data.items():
        if key.startswith('coverage_'):
            prod_id = key.replace('coverage_', '')
            try:
                coverages[prod_id] = float(value)
            except (ValueError, TypeError):
                coverages[prod_id] = 1.0

    @sync_to_async
    def generate_file():
        from apps.sales.services.stock_transfers.calculator import StockTransferCalculatorService
        from apps.core.models import Warehouse
        
        service = StockTransferCalculatorService(
            origin_warehouse_id=origin,
            destination_warehouse_id=destination,
            product_class_ids=product_classes,
            rotation_level_ids=rotation_levels
        )
        
        results = service.calculate_transfer(start_date, end_date)
        
        origin_name = "Desconocido"
        dest_name = "Desconocido"
        if origin:
            w_origin = Warehouse.objects.filter(id=origin).first()
            if w_origin:
                origin_name = w_origin.name.title()
        if destination:
            w_dest = Warehouse.objects.filter(id=destination).first()
            if w_dest:
                dest_name = w_dest.name.title()
        
        module = SystemModule.objects.filter(url_name='sales:stock_transfers').first()
        ActivityLogger.log_download(
            user=request.user,
            module=module,
            description='descarga de resultados de transferencias de stock en Excel',
            metadata={'origin': origin, 'destination': destination}
        )
        
        return service.export_data_report(results, start_date, end_date, origin_name, dest_name, coverages)

    excel_file = await generate_file()
    
    if not excel_file:
        return HttpResponse("Error en los parámetros o la simulación", status=400)

    response = HttpResponse(
        excel_file, 
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="transferencias_stock.xlsx"'
    
    return response


@login_required
def sale_transactions(request):
    template = 'sales/sale_transactions/sale_transactions.html'
    allowed_routes = get_allowed_routes_for_user(request.user)

    # get filters
    doc_id = request.GET.get('doc_id')
    sale_date_start = request.GET.get('sale_date_start')
    sale_date_end = request.GET.get('sale_date_end')

    # default dates if not provided
    if not sale_date_start:
        today = datetime.date.today()
        sale_date_start = datetime.date(today.year, today.month, 1).strftime('%Y-%m-%d')
    if not sale_date_end:
        today = datetime.date.today()
        _, last_day = calendar.monthrange(today.year, today.month)
        sale_date_end = datetime.date(today.year, today.month, last_day).strftime('%Y-%m-%d')
    
    product_classes = request.GET.getlist('product_classes')
    product_categories = request.GET.getlist('product_categories')
    routes = request.GET.getlist('routes')
    warehouses = request.GET.getlist('warehouses')

    # customers and products as comma separated strings in simple input
    customers_str = request.GET.get('customers')
    products_str = request.GET.get('products')

    filters = {}
    if doc_id: filters['doc_id'] = doc_id
    if sale_date_start: filters['sale_date_start'] = sale_date_start
    if sale_date_end: filters['sale_date_end'] = sale_date_end
    if product_classes: filters['product_classes'] = product_classes
    if product_categories: filters['product_categories'] = product_categories
    if routes: filters['routes'] = routes
    if warehouses: filters['warehouses'] = warehouses
    if customers_str: filters['customers'] = [c.strip() for c in customers_str.split(',') if c.strip()]
    if products_str: filters['products'] = [p.strip() for p in products_str.split(',') if p.strip()]

    transactions_service = SaleTransactionCRUD()
    qs = transactions_service.read(allowed_routes, **filters)
    
    # We aggregate the values to compute the kpis!
    aggregates = qs.aggregate(
        total_net=Sum('net_amount'),
        total_gross=Sum('gross_amount'),
        total_profit=Sum('profit'),
        total_units=Sum('quantity')
    )
    
    net_amount = aggregates['total_net'] or Decimal('0.00')
    gross_amount = aggregates['total_gross'] or Decimal('0.00')
    profit = aggregates['total_profit'] or Decimal('0.00')
    units = aggregates['total_units'] or Decimal('0.00')
    
    margin = (profit / net_amount * 100) if net_amount != 0 else Decimal('0.00')
    
    kpis = {
        'net_amount': net_amount,
        'gross_amount': gross_amount,  # Match template typo 'groos_amount'
        'units': units,
        'margin': margin
    }
    
    # We order by sale_date DESC for recent ones first
    qs = qs.order_by('-sale_date')

    paginator = Paginator(qs, 100)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'transactions': page_obj.object_list,
        'page_obj': page_obj,
        'filter_product_classes': ProductClass.objects.all().order_by('name'),
        'filter_product_categories': ProductCategory.objects.all().order_by('name'),
        'filter_routes': Route.objects.filter(id__in=allowed_routes).order_by('id'),
        'filter_warehouses': Warehouse.objects.all().order_by('name'),
        
        'selected_product_classes': product_classes,
        'selected_product_categories': product_categories,
        'selected_routes': routes,
        'selected_warehouses': warehouses,
        'doc_id': doc_id or '',
        'sale_date_start': sale_date_start or '',
        'sale_date_end': sale_date_end or '',
        'selected_date_start': sale_date_start,
        'selected_date_end': sale_date_end,
        'customers': customers_str or '',
        'products': products_str or '',
        'allowed_routes': allowed_routes,
        'kpis': kpis
    }

    if request.htmx:
        template = 'sales/sale_transactions/partials/sale_transaction_rows.html'
    else:
        module = SystemModule.objects.filter(url_name='sales:sale_transactions').first()
        ActivityLogger.log_read(
            user=request.user,
            module=module,
            description='visualización del listado de transacciones de venta',
            metadata={'filters': filters}
        )

    return render(request, template, context)

@login_required
def sale_transactions_export(request):
    import datetime
    import calendar

    allowed_routes = get_allowed_routes_for_user(request.user)

    doc_id = request.GET.get('doc_id')
    sale_date_start = request.GET.get('sale_date_start')
    sale_date_end = request.GET.get('sale_date_end')

    # default dates if not provided
    if not sale_date_start:
        today = datetime.date.today()
        sale_date_start = datetime.date(today.year, today.month, 1).strftime('%Y-%m-%d')
    if not sale_date_end:
        today = datetime.date.today()
        _, last_day = calendar.monthrange(today.year, today.month)
        sale_date_end = datetime.date(today.year, today.month, last_day).strftime('%Y-%m-%d')
    
    product_classes = request.GET.getlist('product_classes')
    product_categories = request.GET.getlist('product_categories')
    routes = request.GET.getlist('routes')
    warehouses = request.GET.getlist('warehouses')

    customers_str = request.GET.get('customers')
    products_str = request.GET.get('products')

    filters = {}
    if doc_id: filters['doc_id'] = doc_id
    if sale_date_start: filters['sale_date_start'] = sale_date_start
    if sale_date_end: filters['sale_date_end'] = sale_date_end
    if product_classes: filters['product_classes'] = product_classes
    if product_categories: filters['product_categories'] = product_categories
    if routes: filters['routes'] = routes
    if warehouses: filters['warehouses'] = warehouses
    if customers_str: filters['customers'] = [c.strip() for c in customers_str.split(',') if c.strip()]
    if products_str: filters['products'] = [p.strip() for p in products_str.split(',') if p.strip()]

    transactions_service = SaleTransactionCRUD()
    qs = transactions_service.read(allowed_routes, **filters).order_by('-sale_date')

    data = []
    for txn in qs:
        data.append({
            'Documento': txn.doc_id.upper() if txn.doc_id else '',
            'Fecha': txn.sale_date.strftime('%d/%m/%Y') if txn.sale_date else '',
            'Lugar de venta': txn.warehouse_id.upper() if txn.warehouse_id else '',
            'Cliente': txn.customer_id.upper() if txn.customer_id else '',
            'Ruta': txn.route_id.upper() if txn.route_id else '',
            'Monto neto': txn.net_amount if txn.net_amount is not None else 0.0,
            'Monto bruto': txn.gross_amount if txn.gross_amount is not None else 0.0,
            'Cantidad': txn.quantity if txn.quantity is not None else 0.0,
            'Producto': txn.product_id.upper() if txn.product_id else '',
        })

    df = pd.DataFrame(data)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Transacciones')

    output.seek(0)
    
    module = SystemModule.objects.filter(url_name='sales:sale_transactions').first()
    ActivityLogger.log_download(
        user=request.user,
        module=module,
        description='descarga del listado de transacciones de venta en Excel',
        metadata={'filters': filters}
    )
    
    response = HttpResponse(
        output,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename=transacciones.xlsx'
    return response


@login_required
def sale_targets_calculator(request):
    product_classes = ProductClass.objects.all().order_by('name')
    routes = Route.objects.filter(is_active=True).order_by('id')
    
    context = {
        'product_classes': product_classes,
        'routes': routes,
    }
    
    if request.headers.get('HX-Request'):
        action = request.GET.get('action') or request.POST.get('action')
        
        if action == 'toggle_mode':
            mode = request.GET.get('adjustment_mode')
            return render(request, 'sale_targets_calculator/partials/route_selectors.html', {'mode': mode, 'routes': routes})
            
        if action == 'load_customers':
            from apps.core.models import Customer
            route_id = request.GET.get('origin_route')
            filter_type = request.GET.get('filter_type', 'assigned')
            
            customers = []
            if route_id:
                if filter_type == 'all':
                    customers = Customer.objects.select_related('route').all().order_by('name')
                else:
                    customers = Customer.objects.filter(route_id=route_id).order_by('name')
            return render(request, 'sale_targets_calculator/partials/customer_selector.html', {
                'customers': customers,
                'filter_type': filter_type,
                'origin_route_id': route_id
            })
            
        if action == 'calculate':
            from apps.sales.services.sale_targets.calculator import SaleTargetsCalculatorService
            
            mode = request.POST.get('adjustment_mode')
            method = request.POST.get('calculation_method')
            origin_route = request.POST.get('origin_route')
            destination_route = request.POST.get('destination_route')
            adjustment_direction = request.POST.get('adjustment_direction', 'remove')
            transfer_growth_rule = request.POST.get('transfer_growth_rule', 'exact')
            target_year = request.POST.get('target_year')
            effective_month = request.POST.get('effective_month')
            eval_customer_start = request.POST.get('eval_customer_start')
            eval_customer_end = request.POST.get('eval_customer_end')
            eval_route_start = request.POST.get('eval_route_start')
            eval_route_end = request.POST.get('eval_route_end')
            product_classes_selected = request.POST.getlist('product_classes')
            selected_customers = request.POST.getlist('selected_customers')
            
            service = SaleTargetsCalculatorService(
                mode=mode,
                origin_route_id=origin_route,
                destination_route_id=destination_route,
                customer_ids=selected_customers,
                adjustment_direction=adjustment_direction,
                transfer_growth_rule=transfer_growth_rule
            )
            
            results = service.calculate_simulation(
                target_year=int(target_year) if target_year else None,
                effective_month=effective_month,
                eval_customer_start=eval_customer_start,
                eval_customer_end=eval_customer_end,
                eval_route_start=eval_route_start,
                eval_route_end=eval_route_end,
                product_class_ids=product_classes_selected,
                calc_method=method
            )
            
            module = SystemModule.objects.filter(url_name='sales:sale_targets_calculator').first()
            ActivityLogger.log_read(
                user=request.user,
                module=module,
                description='cálculo de simulación de objetivos de venta',
                metadata={'method': method, 'mode': mode, 'target_year': target_year}
            )
            
            return render(request, 'sale_targets_calculator/partials/calculator_results.html', {
                'results': results,
                'errors': service.errors,
            })
            
    template = 'sale_targets_calculator/sale_targets_calculator.html'
    
    module = SystemModule.objects.filter(url_name='sales:sale_targets_calculator').first()
    ActivityLogger.log_read(
        user=request.user,
        module=module,
        description='visualización de calculadora de objetivos de venta'
    )
    
    return render(request, template, context)


@login_required
async def export_sale_targets_calculator_data(request):
    mode = request.GET.get('adjustment_mode')
    method = request.GET.get('calculation_method')
    origin_route = request.GET.get('origin_route')
    destination_route = request.GET.get('destination_route')
    adjustment_direction = request.GET.get('adjustment_direction', 'remove')
    transfer_growth_rule = request.GET.get('transfer_growth_rule', 'exact')
    target_year = request.GET.get('target_year')
    effective_month = request.GET.get('effective_month')
    eval_customer_start = request.GET.get('eval_customer_start')
    eval_customer_end = request.GET.get('eval_customer_end')
    eval_route_start = request.GET.get('eval_route_start')
    eval_route_end = request.GET.get('eval_route_end')
    product_classes_selected = request.GET.getlist('product_classes')
    selected_customers = request.GET.getlist('selected_customers')

    @sync_to_async
    def generate_file():
        from apps.sales.services.sale_targets.calculator import SaleTargetsCalculatorService
        
        service = SaleTargetsCalculatorService(
            mode=mode,
            origin_route_id=origin_route,
            destination_route_id=destination_route,
            customer_ids=selected_customers,
            adjustment_direction=adjustment_direction,
            transfer_growth_rule=transfer_growth_rule
        )
        
        results = service.calculate_simulation(
            target_year=int(target_year) if target_year else None,
            effective_month=effective_month,
            eval_customer_start=eval_customer_start,
            eval_customer_end=eval_customer_end,
            eval_route_start=eval_route_start,
            eval_route_end=eval_route_end,
            product_class_ids=product_classes_selected,
            calc_method=method
        )
        
        module = SystemModule.objects.filter(url_name='sales:sale_targets_calculator').first()
        ActivityLogger.log_download(
            user=request.user,
            module=module,
            description='descarga de resultados de simulación de objetivos de venta en Excel',
            metadata={'method': method, 'mode': mode, 'target_year': target_year}
        )
        
        return service.export_data_report(results)

    excel_file = await generate_file()
    
    if not excel_file:
        return HttpResponse("Error en los parámetros o la simulación", status=400)

    response = HttpResponse(
        excel_file, 
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="simulacion_objetivos.xlsx"'
    
    return response









@login_required
def sale_list_view(request):
    template = 'sales/sales/sale_list.html'
    routes_service = RoutesService(user=request.user)
    
    context = {
        'allowed_routes_for_selling': routes_service.read_routes(for_selling=True),
        'allowed_routes_for_viewing': routes_service.read_routes(),
        'allowed_bu_by_routes': routes_service.get_allowed_bu_by_routes(),
        'allowed_warehouses_by_routes': routes_service.get_allowed_warehouses_by_routes()
    }
    return render(request, template, context)
    