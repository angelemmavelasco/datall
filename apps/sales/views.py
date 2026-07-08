from django.contrib import messages
from django.shortcuts import render, redirect
from apps.sales.services.products.products_crud import ProductsCrud
from django.contrib.auth.decorators import login_required
from apps.core.models import Reference, ProductClass, Warehouse, Route, ProductCategory
from django.core.paginator import Paginator
from django.http import HttpResponse
import pandas as pd
import io
from apps.core.utils import get_allowed_routes_for_user
from apps.sales.services.sale_transactions.sale_transactions_crud import SaleTransactionCRUD

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

    return render(request, TEMPLATE, context)




@login_required
def sale_transactions(request):
    template = 'sales/sale_transactions/sale_transactions.html'
    allowed_routes = get_allowed_routes_for_user(request.user)

    # get filters
    doc_id = request.GET.get('doc_id')
    sale_date_start = request.GET.get('sale_date_start')
    sale_date_end = request.GET.get('sale_date_end')
    
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
        'customers': customers_str or '',
        'products': products_str or '',
        'allowed_routes': allowed_routes
    }

    if request.htmx:
        template = 'sales/sale_transactions/partials/sale_transaction_rows.html'

    return render(request, template, context)

@login_required
def sale_transactions_export(request):
    allowed_routes = get_allowed_routes_for_user(request.user)

    doc_id = request.GET.get('doc_id')
    sale_date_start = request.GET.get('sale_date_start')
    sale_date_end = request.GET.get('sale_date_end')
    
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
    response = HttpResponse(
        output,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename=transacciones.xlsx'
    return response


@login_required
def sale_targets_calculator(request):
    from apps.core.models import ProductClass, Route
    
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
                    # Traemos todos los clientes sin límite
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
                adjustment_direction=adjustment_direction
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
            
            return render(request, 'sale_targets_calculator/partials/calculator_results.html', {
                'results': results,
                'errors': service.errors,
            })
            
    template = 'sale_targets_calculator/sale_targets_calculator.html'
    return render(request, template, context)