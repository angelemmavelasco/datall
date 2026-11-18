import os
import uuid
from django.conf import settings
from django.core.paginator import Paginator
from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from decimal import Decimal
from django.utils import timezone
from django_q.tasks import async_task

from apps.core.models import GeneratedReport, ActivityLog

from .models import PurchaseOrder
from .services import (
    ProductsService,
    ProductsStats,
    StockTransfersService,
    StockTransferExports,
    PurchaseOrdersService,
    PurchaseOrdersStats,
    PurchaseOrderExports,
    PurchaseOrderNotFound,
    ProductNotFound,
    PermissionsError,
    ServiceError,
)
from .filters import ProductFilter, PurchaseOrderFilter
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

    timestamp_str = timezone.localdate().strftime('%Y%m%d_%H%M%S')
    filename = f"transferencias_{origin}_{destination}_{timestamp_str}.xlsx"

    serializable_cleaned_data = {}
    for k, v in req_data.lists():
        if len(v) == 1:
            serializable_cleaned_data[k] = v[0]
        else:
            serializable_cleaned_data[k] = v

    try:
        temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp_reports')
        os.makedirs(temp_dir, exist_ok=True)
        temp_filename = f"{uuid.uuid4().hex}.xlsx"
        temp_file_path = os.path.join(temp_dir, temp_filename)
        with open(temp_file_path, 'wb') as f:
            f.write(excel_data)

        report = GeneratedReport.objects.create(
            user=request.user,
            title=f"Reporte de Transferencias - {origin_name} a {dest_name}",
            module_name="stock_transfers",
            status=GeneratedReport.Status.PENDING,
            filters=serializable_cleaned_data,
            file_size=len(excel_data),
        )

        async_task(
            'apps.core.tasks.save_generated_report_file_task',
            report.id,
            temp_file_path,
            filename,
        )
    except Exception as bg_err:
        print(f"[STOCK TRANSFERS EXPORT] Error queuing background persistence: {bg_err}", flush=True)

    response = HttpResponse(
        excel_data,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response["Content-Length"] = len(excel_data)
    return response


@login_required
def purchase_order_list_view(request):
    template = 'products/purchase_orders/purchase_order_list.html'
    service = PurchaseOrdersService(user=request.user)
    stats_service = PurchaseOrdersStats(purchase_orders_service=service)

    available_actions = None
    if service.has_full_access:
        available_actions = 'products/purchase_orders/partials/purchase_order_list__actions.html'

    orders_qs = service.read_purchase_orders()
    order_filter = PurchaseOrderFilter(request.GET, queryset=orders_qs, request=request)
    orders_qs = order_filter.qs

    paginator = Paginator(orders_qs, 100)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    query_dict = request.GET.copy()
    if 'page' in query_dict:
        del query_dict['page']

    orders = page_obj.object_list
    kpis = stats_service.stats(qs=orders_qs)

    context = {
        'orders': orders,
        'kpis': kpis,
        'query_string': query_dict.urlencode(),
        'page_obj': page_obj,
        'available_actions': available_actions,
        'filter': order_filter,
        'can_manage_orders': service.has_full_access,
    }

    if request.htmx:
        target = request.headers.get('HX-Target')
        if target == 'purchase-order-list-content':
            return render(request, 'products/purchase_orders/partials/purchase_order_list_content.html', context)
        return render(request, 'products/purchase_orders/partials/purchase_order_list_rows.html', context)

    return render(request, template, context)


@login_required
def purchase_order_create_view(request):
    service = PurchaseOrdersService(user=request.user)

    if not service.has_full_access:
        messages.error(request, 'No tienes permisos para generar órdenes de compra.')
        return redirect('products:purchase_order_list_view')

    if request.method == 'POST' and (request.htmx or request.headers.get('HX-Request')) and request.POST.get('action') == 'calculate-order':
        warehouse_ids = request.POST.getlist('warehouses')
        grouping_mode = request.POST.get('grouping_mode', PurchaseOrder.GroupingModeChoices.SEPARATED)
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        coverage_months = request.POST.get('coverage_months', '1.0')
        product_classes = request.POST.getlist('product_classes')
        rotation_levels = request.POST.getlist('rotation_levels')

        preview = service.calculate_order_preview(
            warehouse_ids=warehouse_ids,
            start_date_str=start_date,
            end_date_str=end_date,
            grouping_mode=grouping_mode,
            coverage_months=coverage_months,
            product_class_ids=product_classes,
            rotation_level_ids=rotation_levels,
        )

        return render(
            request,
            'products/purchase_orders/partials/order_calculator_results.html',
            {
                'preview': preview,
                'errors': service.errors,
                'warnings': service.warnings,
            }
        )

    if request.method == 'POST' and request.POST.get('action') == 'save-order':
        origin_type = request.POST.get('origin_type', PurchaseOrder.OriginChoices.IMPORTACION)
        grouping_mode = request.POST.get('grouping_mode', PurchaseOrder.GroupingModeChoices.SEPARATED)
        warehouse_ids = request.POST.getlist('warehouses')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        coverage_months = request.POST.get('coverage_months', '1.0')
        product_classes = request.POST.getlist('product_classes')
        rotation_levels = request.POST.getlist('rotation_levels')
        custom_folio = request.POST.get('custom_folio', '')
        notes = request.POST.get('notes', '')

        requested_quantities = {}
        warehouse_quantities = {}
        product_coverages = {}

        for key, value in request.POST.items():
            if key.startswith('req_qty_'):
                prod_id = key.replace('req_qty_', '', 1)
                try:
                    requested_quantities[prod_id] = Decimal(str(value or '0'))
                except Exception:
                    requested_quantities[prod_id] = Decimal('0')
            elif key.startswith('wh_qty__'):
                parts = key.split('__', 2)
                if len(parts) == 3:
                    _, prod_id, wh_id = parts
                    try:
                        warehouse_quantities.setdefault(prod_id, {})[wh_id] = Decimal(str(value or '0'))
                    except Exception:
                        warehouse_quantities.setdefault(prod_id, {})[wh_id] = Decimal('0')
            elif key.startswith('coverage_'):
                prod_id = key.replace('coverage_', '', 1)
                try:
                    product_coverages[prod_id] = Decimal(str(value or '1.0'))
                except Exception:
                    product_coverages[prod_id] = Decimal('1.0')

        try:
            new_order = service.create_purchase_order(
                origin_type=origin_type,
                grouping_mode=grouping_mode,
                warehouse_ids=warehouse_ids,
                start_date_str=start_date,
                end_date_str=end_date,
                coverage_months=coverage_months,
                product_class_ids=product_classes,
                rotation_level_ids=rotation_levels,
                requested_quantities=requested_quantities,
                warehouse_quantities=warehouse_quantities,
                product_coverages=product_coverages,
                custom_folio=custom_folio,
                notes=notes,
            )
            request.activity_log_extra = {
                'content_object': new_order,
                'action': ActivityLog.Action.CREATE,
                'changes': {
                    'folio': new_order.folio,
                    'previous_status': '',
                    'previous_status_label': '-',
                    'new_status': new_order.status,
                    'new_status_label': new_order.get_status_display(),
                    'total_pallets': new_order.total_pallets,
                    'total_ordered_units': new_order.total_ordered_units,
                    'total_product_weight': str(new_order.total_product_weight),
                    'notes': new_order.notes,
                    'summary': f'Orden de compra {new_order.folio} creada en estatus "{new_order.get_status_display()}" con {new_order.total_pallets} tarimas ({new_order.total_ordered_units} uds).',
                },
            }
            messages.success(request, f'Orden de compra {new_order.folio} generada correctamente.')
            return redirect('products:purchase_order_detail_view', pk=new_order.pk)
        except (PermissionsError, ServiceError) as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f'Error al generar la orden de compra: {str(e)}')

    template = 'products/purchase_orders/purchase_order_create.html'
    context = {
        'warehouses': service.get_available_warehouses(),
        'product_classes': service.get_available_product_classes(),
        'origin_choices': PurchaseOrder.OriginChoices.choices,
        'grouping_choices': PurchaseOrder.GroupingModeChoices.choices,
        'logistics_params': service.get_logistics_parameters(),
    }
    return render(request, template, context)


@login_required
def purchase_order_detail_view(request, pk: int):
    template = 'products/purchase_orders/purchase_order_detail.html'
    service = PurchaseOrdersService(user=request.user)

    try:
        order = service.read_purchase_order(pk=pk)
    except PurchaseOrderNotFound as e:
        messages.error(request, str(e))
        return redirect('products:purchase_order_list_view')

    logistics_params = service.get_logistics_parameters()
    truck_cap = logistics_params['truck_capacity_lbs']
    estimated_trucks = (
        (order.total_pallet_weight / truck_cap).quantize(Decimal('0.01'))
        if truck_cap > 0
        else Decimal('0.00')
    )
    audit_logs = service.get_order_audit_logs(order=order)
    next_status = service.VALID_TRANSITIONS.get(order.status)
    status_labels = dict(PurchaseOrder.StatusChoices.choices)
    next_status_label = status_labels.get(next_status) if next_status else None

    warehouses = list(order.warehouses.all().order_by('name'))
    items = list(order.items.select_related('product', 'product__product_class').order_by('product__product_class__name', 'product__name'))
    for item in items:
        bd = item.warehouse_breakdown or {}
        item.per_warehouse_list = [
            {'warehouse': w, 'qty': bd.get(w.id, 0)}
            for w in warehouses
        ]

    context = {
        'order': order,
        'warehouses': warehouses,
        'items': items,
        'logistics_params': logistics_params,
        'estimated_trucks': estimated_trucks,
        'audit_logs': audit_logs,
        'can_manage_orders': service.has_full_access,
        'next_status': next_status,
        'next_status_label': next_status_label,
        'status_steps': [
            (PurchaseOrder.StatusChoices.REALIZADA, 'Realizada', order.created_at),
            (PurchaseOrder.StatusChoices.CONFIRMADA, 'Confirmada', order.confirmed_at),
            (PurchaseOrder.StatusChoices.EN_TRANSITO, 'En tránsito', order.in_transit_at),
            (PurchaseOrder.StatusChoices.COMPLETADA, 'Completada', order.completed_at),
        ],
    }
    return render(request, template, context)


@login_required
def purchase_order_status_update_view(request, pk: int):
    if request.method != 'POST':
        return redirect('products:purchase_order_detail_view', pk=pk)

    service = PurchaseOrdersService(user=request.user)
    new_status = request.POST.get('new_status', '').strip()
    notes = request.POST.get('notes', '').strip()

    try:
        order, change_payload = service.update_order_status(
            pk=pk,
            new_status=new_status,
            notes=notes,
        )
        request.activity_log_extra = {
            'content_object': order,
            'action': ActivityLog.Action.UPDATE,
            'changes': change_payload,
        }
        messages.success(
            request,
            f'Orden {order.folio} actualizada a estatus "{order.get_status_display()}".'
        )
    except (PermissionsError, PurchaseOrderNotFound, ServiceError) as e:
        messages.error(request, str(e))
    except Exception as e:
        messages.error(request, f'Ocurrió un error al actualizar el estatus: {str(e)}')

    return redirect('products:purchase_order_detail_view', pk=pk)


@login_required
def export_purchase_order_view(request, pk: int):
    service = PurchaseOrdersService(user=request.user)
    try:
        order = service.read_purchase_order(pk=pk)
    except PurchaseOrderNotFound as e:
        messages.error(request, str(e))
        return redirect('products:purchase_order_list_view')

    logistics_params = service.get_logistics_parameters()
    excel_data = PurchaseOrderExports.export_order_excel(
        order=order,
        logistics_params=logistics_params,
    )
    if not excel_data:
        return HttpResponse('No se pudieron generar los datos para exportar.', status=400)

    timestamp_str = timezone.localdate().strftime('%Y%m%d_%H%M%S')
    filename = f'orden_compra_{order.folio.lower()}_{timestamp_str}.xlsx'

    request.activity_log_extra = {
        'content_object': order,
        'action': ActivityLog.Action.EXPORT,
        'changes': {
            'folio': order.folio,
            'summary': f'Exportación a Excel de la orden {order.folio}',
        },
    }

    response = HttpResponse(
        excel_data,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response['Content-Length'] = len(excel_data)
    return response