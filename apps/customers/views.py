from django.core.paginator import Paginator
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
from .forms import CustomerForm, CustomerAssignmentFormSet


@login_required
def customer_list_view(request):
    template = 'customers/customer_list.html'
    service = CustomersService(user=request.user)
    stats_service = CustomersStats(customers_service=service)

    available_actions = None
    if service.has_full_access:
        available_actions = 'customers/partials/customer_list__actions.html'

    customers_qs = service.read_customers()
    customer_filter = CustomerFilter(request.GET, queryset=customers_qs, request=request)
    customers_qs = customer_filter.qs

    paginator = Paginator(customers_qs, 100)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    query_dict = request.GET.copy()
    if 'page' in query_dict:
        del query_dict['page']

    customers = page_obj.object_list
    kpis = stats_service.stats(qs=customers_qs)

    context = {
        'customers': customers,
        'kpis': kpis,
        'query_string': query_dict.urlencode(),
        'page_obj': page_obj,
        'available_actions': available_actions,
        'filter': customer_filter,
    }

    if request.htmx:
        target = request.headers.get('HX-Target')
        if target == 'customer-list-content':
            return render(request, 'customers/partials/customer_list_content.html', context)
        return render(request, 'customers/partials/customer_list_rows.html', context)

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


@login_required
def customer_create_view(request):
    template = 'customers/customer_form.html'
    service = CustomersService(user=request.user)

    if not service.has_full_access:
        messages.error(request, 'No tienes permisos para registrar clientes.')
        return redirect('customers:customer_list_view')

    if request.method == 'POST':
        form = CustomerForm(request.POST)
        assignments_formset = CustomerAssignmentFormSet(request.POST, prefix='assignments')

        if form.is_valid() and assignments_formset.is_valid():
            try:
                assignments_data = [f.cleaned_data for f in assignments_formset if f.cleaned_data]
                new_customer = service.create_customer(
                    customer_data=form.cleaned_data,
                    assignments_data=assignments_data,
                )
                messages.success(request, f'Cliente {new_customer.id} registrado correctamente.')
                next_url = request.GET.get('next') or request.POST.get('next')
                if next_url:
                    return redirect(next_url)
                return redirect('customers:customer_detail_view', new_customer.pk)

            except PermissionsError as e:
                messages.error(request, str(e))
                return redirect('customers:customer_list_view')

            except ServiceError as e:
                messages.error(request, str(e))

            except Exception as e:
                messages.error(request, f"Ocurrió un error inesperado al registrar: {str(e)}")
        else:
            messages.error(request, 'Por favor revisa los errores en el formulario.')
    else:
        form = CustomerForm()
        assignments_formset = CustomerAssignmentFormSet(prefix='assignments')

    context = {
        'form': form,
        'assignments_formset': assignments_formset,
        'can_update_access': service.has_full_access,
        'updating': None,
    }
    return render(request, template, context)


@login_required
def customer_update_view(request, pk: str):
    template = 'customers/customer_form.html'
    service = CustomersService(user=request.user)

    if not service.has_full_access:
        messages.error(request, 'No tienes permisos para actualizar clientes.')
        return redirect('customers:customer_detail_view', pk=pk)

    try:
        customer_instance = service.read_customer(pk=pk)
    except CustomerNotFound:
        messages.error(request, "El cliente solicitado no existe.")
        return redirect('customers:customer_list_view')
    except PermissionsError:
        messages.error(request, "No tienes permisos para actualizar este cliente.")
        return redirect('customers:customer_list_view')
    except Exception as e:
        messages.error(request, str(e))
        return redirect('customers:customer_list_view')

    if request.method == 'POST':
        form = CustomerForm(request.POST, instance=customer_instance)
        assignments_formset = CustomerAssignmentFormSet(
            request.POST, instance=customer_instance, prefix='assignments'
        )

        if form.is_valid() and assignments_formset.is_valid():
            try:
                assignments_data = [f.cleaned_data for f in assignments_formset if f.cleaned_data]
                updated_customer = service.update_customer(
                    pk=pk,
                    customer_data=form.cleaned_data,
                    assignments_data=assignments_data,
                )
                messages.success(request, f"Cliente {updated_customer.id} actualizado correctamente.")
                return redirect('customers:customer_detail_view', updated_customer.pk)

            except PermissionsError as e:
                messages.error(request, str(e))
                return redirect('customers:customer_list_view')

            except ServiceError as e:
                messages.error(request, str(e))

            except Exception as e:
                messages.error(request, f"Ocurrió un error inesperado al actualizar: {str(e)}")
        else:
            messages.error(request, 'Por favor revisa los errores en el formulario.')
    else:
        form = CustomerForm(instance=customer_instance)
        assignments_formset = CustomerAssignmentFormSet(
            instance=customer_instance, prefix='assignments'
        )

    context = {
        'form': form,
        'assignments_formset': assignments_formset,
        'updating': customer_instance,
        'can_update_access': service.has_full_access,
    }
    return render(request, template, context)

@login_required
def customer_filter_options_view(request):
    q = request.GET.get('q_customer', '').strip()
    selected_ids = request.GET.getlist('customer')

    service = CustomersService(user=request.user)
    base_qs = service.read_customers()

    selected_qs = base_qs.filter(pk__in=selected_ids) if selected_ids else base_qs.none()

    search_qs = base_qs
    if q:
        from django.db.models import Q
        search_qs = search_qs.filter(
            Q(id__icontains=q) |
            Q(name__icontains=q)
        )
    if selected_ids:
        search_qs = search_qs.exclude(pk__in=selected_ids)

    customers = list(selected_qs) + list(search_qs.order_by('name', 'id')[:30])

    return render(
        request,
        'customers/partials/customer_filter_options.html',
        {
            'customers': customers,
            'selected_ids': selected_ids,
        }
    )