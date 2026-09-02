from datetime import date, timedelta
from django.core.paginator import Paginator
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from .exports import *

from .services import (
    CustomersService,
    CustomersStats,
    CustomerNotFound,
    PermissionsError,
    ServiceError,
    AccountsReceivablesService,
    AccountsReceivablesStats,
    AccountsReceivableNotFound,
)
from .filters import CustomerFilter, AccountsReceivableFilter, CustomerProfileFilter
from .forms import CustomerForm, CustomerAssignmentFormSet, CustomerClassMarginFormSet
from apps.sales.services.sale_transactions import SaleTransactionsService
from apps.analytics.services.customer_kpis import CustomerProfileService


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

    tx_service = SaleTransactionsService(user=request.user)
    base_txs = tx_service.read_transactions_by_allowed_customers().filter(customer=customer)

    today = timezone.localdate()
    get_data = request.GET.copy()
    if 'date_start' not in get_data:
        get_data['date_start'] = date(today.year, 1, 1).strftime('%Y-%m-%d')
    if 'date_end' not in get_data:
        last_day_prev_month = date(today.year, today.month, 1) - timedelta(days=1)
        default_end = last_day_prev_month if today.month > 1 else today
        get_data['date_end'] = default_end.strftime('%Y-%m-%d')

    profile_filter = CustomerProfileFilter(get_data, queryset=base_txs, request=request)
    filtered_txs = profile_filter.qs

    ar_service = AccountsReceivablesService(user=request.user)
    base_ars = ar_service.read_ars_by_allowed_customers().filter(customer=customer)

    cleaned_data = profile_filter.form.cleaned_data if profile_filter.is_valid() else {}

    date_start_val = cleaned_data.get('date_start')
    date_end_val = cleaned_data.get('date_end')

    profile_service = CustomerProfileService(
        user=request.user,
        customer=customer,
        transactions_qs=filtered_txs,
        ars_qs=base_ars,
        cleaned_data=cleaned_data,
        date_start=date_start_val,
        date_end=date_end_val,
    )
    customer = profile_service.build_profile()

    available_actions = None
    if service.has_full_access:
        available_actions = 'customers/partials/customer_detail__actions.html'

    context = {
        'customer': customer,
        'filter': profile_filter,
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
        class_margins_formset = CustomerClassMarginFormSet(request.POST, prefix='class_margins')

        if form.is_valid() and assignments_formset.is_valid() and class_margins_formset.is_valid():
            try:
                assignments_data = [f.cleaned_data for f in assignments_formset if f.cleaned_data]
                class_margins_data = [f.cleaned_data for f in class_margins_formset if f.cleaned_data]
                new_customer = service.create_customer(
                    customer_data=form.cleaned_data,
                    assignments_data=assignments_data,
                    class_margins_data=class_margins_data,
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
        class_margins_formset = CustomerClassMarginFormSet(prefix='class_margins')

    context = {
        'form': form,
        'assignments_formset': assignments_formset,
        'class_margins_formset': class_margins_formset,
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
        class_margins_formset = CustomerClassMarginFormSet(
            request.POST, instance=customer_instance, prefix='class_margins'
        )

        if form.is_valid() and assignments_formset.is_valid() and class_margins_formset.is_valid():
            try:
                assignments_data = [f.cleaned_data for f in assignments_formset if f.cleaned_data]
                class_margins_data = [f.cleaned_data for f in class_margins_formset if f.cleaned_data]
                updated_customer = service.update_customer(
                    pk=pk,
                    customer_data=form.cleaned_data,
                    assignments_data=assignments_data,
                    class_margins_data=class_margins_data,
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
        class_margins_formset = CustomerClassMarginFormSet(
            instance=customer_instance, prefix='class_margins'
        )

    context = {
        'form': form,
        'assignments_formset': assignments_formset,
        'class_margins_formset': class_margins_formset,
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

@login_required
def ar_list_view(request):
    template = 'customers/accounts_receivable/ar_list.html'
    service = AccountsReceivablesService(user=request.user)
    stats_service = AccountsReceivablesStats(accounts_receivables_service=service)

    available_actions = None

    perspective = request.GET.get('perspective', 'current_customers')
    if perspective == 'emitting_routes':
        ars_qs = service.read_ars_by_allowed_routes()
    else:
        ars_qs = service.read_ars_by_allowed_customers()

    ar_filter = AccountsReceivableFilter(request.GET, queryset=ars_qs, request=request)
    ars_qs = ar_filter.qs

    paginator = Paginator(ars_qs, 100)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    query_dict = request.GET.copy()
    if 'page' in query_dict:
        del query_dict['page']

    accounts_receivable = page_obj.object_list
    kpis = stats_service.stats(qs=ars_qs)

    selected_customer_ids = request.GET.getlist('customer')
    customers_service = CustomersService(user=request.user)
    cust_base = customers_service.read_customers()
    cust_selected = cust_base.filter(pk__in=selected_customer_ids) if selected_customer_ids else cust_base.none()
    cust_remaining = cust_base.exclude(pk__in=selected_customer_ids).order_by('name', 'id')[:20]
    initial_customers = list(cust_selected) + list(cust_remaining)

    context = {
        'accounts_receivable': accounts_receivable,
        'kpis': kpis,
        'query_string': query_dict.urlencode(),
        'page_obj': page_obj,
        'available_actions': available_actions,
        'filter': ar_filter,
        'initial_customers': initial_customers,
        'selected_customer_ids': selected_customer_ids,
        'current_perspective': perspective,
    }

    if request.htmx:
        target = request.headers.get('HX-Target')
        if target == 'ar-list-content':
            return render(request, 'customers/accounts_receivable/partials/ar_list_content.html', context)
        return render(request, 'customers/accounts_receivable/partials/ar_list_rows.html', context)

    return render(request, template, context)


@login_required
def ar_detail_view(request, pk: str | int):
    template = 'customers/accounts_receivable/ar_detail.html'
    service = AccountsReceivablesService(user=request.user)

    try:
        ar_obj = service.read_ar(pk=pk)
    except (AccountsReceivableNotFound, PermissionsError) as e:
        messages.error(request, str(e))
        return redirect('customers:ar_list_view')
    except Exception as e:
        messages.error(request, f"Ocurrió un error al cargar la cuenta por cobrar: {str(e)}")
        return redirect('customers:ar_list_view')

    available_actions = None

    context = {
        'ar': ar_obj,
        'available_actions': available_actions,
    }
    return render(request, template, context)