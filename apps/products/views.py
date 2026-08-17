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
        'can_view_cost': service.has_full_access,
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
        'can_view_cost': service.has_full_access,
        'available_actions': available_actions,
    }
    return render(request, template, context)


@login_required
def product_create_view(request):
    pass


@login_required
def product_update_view(request, pk: str):
    pass