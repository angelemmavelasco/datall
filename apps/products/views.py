from django.core.paginator import Paginator
from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required

from .services import (
    ProductsService,
    ProductsStats,
    StockTransfersService,
    StockTransferExports,
    ProductNotFound,
    PermissionsError,
    ServiceError,
)
from .filters import ProductFilter
from .forms import (
    ProductForm,
    ProductPropertyValueFormSet,
    StockFormSet,
)


@login_required
def product_list_view(request):
    template = 'products/product_list.html'
    service = ProductsService(user=request.user)
    stats_service = ProductsStats(products_service=service)

    available_actions = None
    if service.has_full_access:
        available_actions = 'products/partials/product_list__actions.html'

    products_qs = service.read_products()
    product_filter = ProductFilter(request.GET, queryset=products_qs, request=request)
    products_qs = product_filter.qs

    paginator = Paginator(products_qs, 100)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    query_dict = request.GET.copy()
    if 'page' in query_dict:
        del query_dict['page']

    products = page_obj.object_list
    kpis = stats_service.stats(qs=products_qs)

    context = {
        'products': products,
        'kpis': kpis,
        'query_string': query_dict.urlencode(),
        'page_obj': page_obj,
        'available_actions': available_actions,
        'filter': product_filter,
        'can_view_cost': service.has_full_access and not request.user.groups.filter(name='vendedor').exists(),
    }

    if request.htmx:
        target = request.headers.get('HX-Target')
        if target == 'product-list-content':
            return render(request, 'products/partials/product_list_content.html', context)
        return render(request, 'products/partials/product_list_rows.html', context)

    return render(request, template, context)


@login_required
def product_detail_view(request, pk: str):
    template = 'products/product_detail.html'
    service = ProductsService(user=request.user)

    try:
        product = service.read_product(pk=pk)
    except (ProductNotFound, PermissionsError) as e:
        messages.error(request, str(e))
        return redirect('products:product_list_view')
    except Exception as e:
        messages.error(request, f"Ocurrió un error al cargar el producto: {str(e)}")
        return redirect('products:product_list_view')

    available_actions = None
    if service.has_full_access:
        available_actions = 'products/partials/product_detail__actions.html'

    context = {
        'product': product,
        'can_view_cost': service.has_full_access and not request.user.groups.filter(name='vendedor').exists(),
        'available_actions': available_actions,
    }
    return render(request, template, context)


@login_required
def product_create_view(request):
    template = 'products/product_form.html'
    service = ProductsService(user=request.user)

    if not service.has_full_access:
        messages.error(request, 'No tienes permisos para registrar productos.')
        return redirect('products:product_list_view')

    if request.method == 'POST':
        form = ProductForm(request.POST)
        properties_formset = ProductPropertyValueFormSet(request.POST, prefix='properties')
        stocks_formset = StockFormSet(request.POST, prefix='stocks')

        if form.is_valid() and properties_formset.is_valid() and stocks_formset.is_valid():
            try:
                properties_data = [f.cleaned_data for f in properties_formset if f.cleaned_data]
                stocks_data = [f.cleaned_data for f in stocks_formset if f.cleaned_data]

                new_product = service.create_product(
                    product_data=form.cleaned_data,
                    properties_data=properties_data,
                    stocks_data=stocks_data,
                )
                messages.success(request, f'Producto {new_product.id} registrado correctamente.')
                next_url = request.GET.get('next') or request.POST.get('next')
                if next_url:
                    return redirect(next_url)
                return redirect('products:product_detail_view', new_product.pk)

            except PermissionsError as e:
                messages.error(request, str(e))
                return redirect('products:product_list_view')

            except ServiceError as e:
                messages.error(request, str(e))

            except Exception as e:
                messages.error(request, f"Ocurrió un error inesperado al registrar: {str(e)}")
        else:
            messages.error(request, 'Por favor revisa los errores en el formulario.')
    else:
        form = ProductForm()
        properties_formset = ProductPropertyValueFormSet(prefix='properties')
        stocks_formset = StockFormSet(prefix='stocks')

    context = {
        'form': form,
        'properties_formset': properties_formset,
        'stocks_formset': stocks_formset,
        'can_update_access': service.has_full_access,
        'updating': None,
    }
    return render(request, template, context)


@login_required
def product_update_view(request, pk: str):
    template = 'products/product_form.html'
    service = ProductsService(user=request.user)

    if not service.has_full_access:
        messages.error(request, 'No tienes permisos para actualizar productos.')
        return redirect('products:product_detail_view', pk=pk)

    try:
        product_instance = service.read_product(pk=pk)
    except ProductNotFound:
        messages.error(request, "El producto solicitado no existe.")
        return redirect('products:product_list_view')
    except PermissionsError:
        messages.error(request, "No tienes permisos para acceder a este producto.")
        return redirect('products:product_list_view')
    except Exception as e:
        messages.error(request, str(e))
        return redirect('products:product_list_view')

    if request.method == 'POST':
        form = ProductForm(request.POST, instance=product_instance)
        properties_formset = ProductPropertyValueFormSet(
            request.POST, instance=product_instance, prefix='properties'
        )
        stocks_formset = StockFormSet(
            request.POST, instance=product_instance, prefix='stocks'
        )

        if form.is_valid() and properties_formset.is_valid() and stocks_formset.is_valid():
            try:
                properties_data = [f.cleaned_data for f in properties_formset if f.cleaned_data]
                stocks_data = [f.cleaned_data for f in stocks_formset if f.cleaned_data]

                updated_product = service.update_product(
                    pk=pk,
                    product_data=form.cleaned_data,
                    properties_data=properties_data,
                    stocks_data=stocks_data,
                )
                messages.success(request, f"Producto {updated_product.id} actualizado correctamente.")
                return redirect('products:product_detail_view', updated_product.pk)

            except PermissionsError as e:
                messages.error(request, str(e))
                return redirect('products:product_list_view')

            except ServiceError as e:
                messages.error(request, str(e))

            except Exception as e:
                messages.error(request, f"Ocurrió un error inesperado al actualizar: {str(e)}")
        else:
            messages.error(request, 'Por favor revisa los errores en el formulario.')
    else:
        form = ProductForm(instance=product_instance)
        properties_formset = ProductPropertyValueFormSet(
            instance=product_instance, prefix='properties'
        )
        stocks_formset = StockFormSet(
            instance=product_instance, prefix='stocks'
        )

    context = {
        'form': form,
        'properties_formset': properties_formset,
        'stocks_formset': stocks_formset,
        'updating': product_instance,
        'can_update_access': service.has_full_access,
    }
    return render(request, template, context)

@login_required
def product_filter_options_view(request):
    q = request.GET.get('q_product', '').strip()
    selected_ids = request.GET.getlist('product')

    service = ProductsService(user=request.user)
    base_qs = service.read_products()

    selected_qs = base_qs.filter(pk__in=selected_ids) if selected_ids else base_qs.none()

    search_qs = base_qs
    if q:
        from django.db.models import Q
        search_qs = search_qs.filter(
            Q(id__icontains=q) |
            Q(name__icontains=q) |
            Q(barcode__icontains=q)
        )
    if selected_ids:
        search_qs = search_qs.exclude(pk__in=selected_ids)

    products = list(selected_qs) + list(search_qs.order_by('name', 'id')[:30])

    return render(
        request,
        'products/partials/product_filter_options.html',
        {
            'products': products,
            'selected_ids': selected_ids,
        }
    )

@login_required
def stock_transfers_view(request):
    service = StockTransfersService(user=request.user)

    if request.method == 'POST' and (request.htmx or request.headers.get('HX-Request')):
        action = request.POST.get('action')
        if action == 'calculate-transfer':
            origin = request.POST.get('warehouse_origin')
            destination = request.POST.get('warehouse_destination')
            start_date = request.POST.get('start_date')
            end_date = request.POST.get('end_date')

            product_classes = request.POST.getlist('product_classes')
            rotation_levels = request.POST.getlist('rotation_levels')

            results = service.calculate_transfer(
                origin_warehouse_id=origin,
                destination_warehouse_id=destination,
                start_date_str=start_date,
                end_date_str=end_date,
                product_class_ids=product_classes,
                rotation_level_ids=rotation_levels
            )

            return render(
                request,
                'products/stock_transfers/partials/transfer_results.html',
                {
                    'results': results,
                    'errors': service.errors,
                    'warnings': service.warnings,
                }
            )

    template = 'products/stock_transfers/stock_transfers.html'
    warehouses = service.get_available_warehouses()
    product_classes = service.get_available_product_classes()

    context = {
        'warehouses': warehouses,
        'product_classes': product_classes,
    }
    return render(request, template, context)


@login_required
def export_stock_transfers_view(request):
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

    service = StockTransfersService(user=request.user)
    results = service.calculate_transfer(
        origin_warehouse_id=origin,
        destination_warehouse_id=destination,
        start_date_str=start_date,
        end_date_str=end_date,
        product_class_ids=product_classes,
        rotation_level_ids=rotation_levels
    )

    if results is None:
        return HttpResponse("Parámetros de cálculo inválidos o faltantes.", status=400)

    origin_obj = service.warehouse_model.objects.filter(id=origin).first() if origin else None
    dest_obj = service.warehouse_model.objects.filter(id=destination).first() if destination else None

    origin_name = origin_obj.name.title() if origin_obj else (origin or "Origen")
    dest_name = dest_obj.name.title() if dest_obj else (destination or "Destino")

    excel_data = StockTransferExports.export_excel(
        results=results,
        start_date_str=start_date,
        end_date_str=end_date,
        origin_name=origin_name,
        destination_name=dest_name,
        coverages=coverages
    )

    if not excel_data:
        return HttpResponse("No se pudieron generar los datos para exportar.", status=400)

    response = HttpResponse(
        excel_data,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"transferencias_{origin}_{destination}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response