from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required

from .services import (
    CustomersService,
    CustomersStats,
    CustomerNotFound,
    PermissionsError,
    ServiceError,
)
from .filters import CustomerFilter


@login_required
def customer_list_view(request):
    template = 'customers/customer_list.html'
    service = CustomersService(user=request.user)
    stats_service = CustomersStats(customers_service=service)

    available_actions = None
    if service.has_full_access:
        available_actions = 'customers/partials/customer_list__actions.html'

    customers = service.read_customers()
    customer_filter = CustomerFilter(request.GET, queryset=customers, request=request)
    customers = customer_filter.qs

    kpis = stats_service.stats(qs=customers)

    context = {
        'customers': customers,
        'kpis': kpis,
        'available_actions': available_actions,
        'filter': customer_filter,
    }
    return render(request, template, context)


@login_required
def customer_detail_view(request, pk: str):
    template = 'customers/customer_detail.html'
    service = CustomersService(user=request.user)

    try:
        customer = service.read_customer(pk=pk)
    except (CustomerNotFound, PermissionsError) as e:
        messages.error(request, str(e))
        return redirect('customers:customer_list_view')
    except Exception as e:
        messages.error(request, f"Ocurrió un error al cargar el cliente: {str(e)}")
        return redirect('customers:customer_list_view')

    available_actions = None
    if service.has_full_access:
        available_actions = 'customers/partials/customer_detail__actions.html'

    context = {
        'customer': customer,
        'available_actions': available_actions,
    }
    return render(request, template, context)