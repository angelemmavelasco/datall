from django.core.paginator import Paginator
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required

from .services import (
    ProductsService,
    ProductsStats,
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