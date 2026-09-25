from datetime import date, timedelta
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.urls import reverse
from django.http import QueryDict
from django.utils import timezone
from .exports import *

import json
from decimal import Decimal
from django.db.models import Q
from dateutil.relativedelta import relativedelta
from apps.core.models import PeriodicityChoices
from apps.products.models import ProductClass
from .models import Customer, CommercialBenefit, CustomerAgreement, AgreementTypeChoices, EvaluationModeChoices
from .services.customer_agreements import parse_month_input

from .services import (
    CustomersService,
    CustomersStats,
    CustomerNotFound,
    PermissionsError,
    ServiceError,
    CustomerContactNotFound,
    AccountsReceivablesService,
    AccountsReceivablesStats,
    AccountsReceivableNotFound,
    CustomerAgreementsService,
    CustomerAgreementsStats,
    CustomerAgreementNotFound,
    CommercialBenefitNotFound,
    MarginValidationException,
)
from apps.mapser.models import CustomerGeoProfile
from .filters import CustomerFilter, AccountsReceivableFilter, CustomerProfileFilter, CustomerAgreementFilter
from .forms import (
    CustomerForm,
    CustomerAssignmentFormSet,
    CustomerClassMarginFormSet,
    CustomerGeoProfileForm,
    CustomerNoteForm,
    CustomerContactForm,
    CustomerAgreementCreateForm,
    CustomerAgreementDocumentForm,
)
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
    can_edit_partially = service.can_edit_partially(customer=customer)
    if service.has_full_access or can_edit_partially:
        available_actions = 'customers/partials/customer_detail__actions.html'

    customer_notes = service.get_customer_notes(customer=customer)
    note_form = CustomerNoteForm()

    customer_contacts = service.get_customer_contacts(customer=customer)
    contact_form = CustomerContactForm()

    tx_query_dict = QueryDict(mutable=True)
    tx_query_dict['customer'] = customer.pk

    date_start_str = get_data.get('date_start')
    if date_start_str:
        tx_query_dict['date_from'] = date_start_str
    date_end_str = get_data.get('date_end')
    if date_end_str:
        tx_query_dict['date_to'] = date_end_str

    for key in ['product_class', 'product_category', 'route', 'business_unit', 'region', 'warehouse', 'product']:
        vals = get_data.getlist(key)
        if vals:
            tx_query_dict.setlist(key, vals)

    transactions_url = f"{reverse('sales:sale_transaction_list_view')}?{tx_query_dict.urlencode()}"

    context = {
        'customer': customer,
        'filter': profile_filter,
        'available_actions': available_actions,
        'transactions_url': transactions_url,
        'can_edit_customer': service.has_full_access,
        'can_edit_partially': can_edit_partially,
        'can_edit_geo_profile': can_edit_partially,
        'customer_notes': customer_notes,
        'note_form': note_form,
        'customer_contacts': customer_contacts,
        'contact_form': contact_form,
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
        geo_form = CustomerGeoProfileForm(request.POST)

        if (
            form.is_valid()
            and assignments_formset.is_valid()
            and class_margins_formset.is_valid()
            and geo_form.is_valid()
        ):
            try:
                assignments_data = [f.cleaned_data for f in assignments_formset if f.cleaned_data]
                class_margins_data = [f.cleaned_data for f in class_margins_formset if f.cleaned_data]
                geo_data = geo_form.cleaned_data if any(geo_form.cleaned_data.values()) else None

                new_customer = service.create_customer(
                    customer_data=form.cleaned_data,
                    assignments_data=assignments_data,
                    class_margins_data=class_margins_data,
                    geo_profile_data=geo_data,
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
        geo_form = CustomerGeoProfileForm()

    context = {
        'form': form,
        'assignments_formset': assignments_formset,
        'class_margins_formset': class_margins_formset,
        'geo_form': geo_form,
        'can_update_access': service.has_full_access,
        'can_edit_customer': True,
        'can_edit_partially': True,
        'can_edit_geo_profile': True,
        'updating': None,
    }
    return render(request, template, context)

@login_required
def customer_update_view(request, pk: str):
    template = 'customers/customer_form.html'
    service = CustomersService(user=request.user)

    try:
        customer_instance = service.read_customer(pk=pk)
    except CustomerNotFound:
        messages.error(request, "El cliente solicitado no existe.")
        return redirect('customers:customer_list_view')
    except PermissionsError:
        messages.error(request, "No tienes permisos para acceder a este cliente.")
        return redirect('customers:customer_list_view')
    except Exception as e:
        messages.error(request, str(e))
        return redirect('customers:customer_list_view')

    can_edit_full = service.has_full_access
    can_edit_partially = service.can_edit_partially(customer=customer_instance)

    if not can_edit_full and not can_edit_partially:
        messages.error(request, "No tienes permisos para actualizar este cliente ni su información.")
        return redirect('customers:customer_detail_view', pk=pk)

    geo_profile_instance = getattr(customer_instance, 'geo_profile', None)
    if not geo_profile_instance:
        geo_profile_instance = CustomerGeoProfile.objects.filter(customer=customer_instance).first()

    if request.method == 'POST':
        if not can_edit_full and can_edit_partially:
            # user with partial access: can only edit customer geo profile
            geo_form = CustomerGeoProfileForm(request.POST, instance=geo_profile_instance)
            if geo_form.is_valid():
                try:
                    service.update_or_create_geo_profile(
                        customer=customer_instance,
                        geo_data=geo_form.cleaned_data,
                    )
                    messages.success(request, f"Perfil geográfico del cliente {customer_instance.id} actualizado correctamente.")
                    return redirect('customers:customer_detail_view', pk=customer_instance.pk)
                except ServiceError as e:
                    messages.error(request, str(e))
                except Exception as e:
                    messages.error(request, f"Ocurrió un error al actualizar el perfil geográfico: {str(e)}")
            else:
                messages.error(request, 'Por favor revisa los errores en el perfil geográfico.')

            form = CustomerForm(instance=customer_instance)
            assignments_formset = CustomerAssignmentFormSet(instance=customer_instance, prefix='assignments')
            class_margins_formset = CustomerClassMarginFormSet(instance=customer_instance, prefix='class_margins')

        else:
            # full access can edit customer, assignments, margins and geo profile
            form = CustomerForm(request.POST, instance=customer_instance)
            assignments_formset = CustomerAssignmentFormSet(
                request.POST, instance=customer_instance, prefix='assignments'
            )
            class_margins_formset = CustomerClassMarginFormSet(
                request.POST, instance=customer_instance, prefix='class_margins'
            )
            geo_form = CustomerGeoProfileForm(request.POST, instance=geo_profile_instance)

            if (
                form.is_valid()
                and assignments_formset.is_valid()
                and class_margins_formset.is_valid()
                and geo_form.is_valid()
            ):
                try:
                    assignments_data = [f.cleaned_data for f in assignments_formset if f.cleaned_data]
                    class_margins_data = [f.cleaned_data for f in class_margins_formset if f.cleaned_data]
                    geo_data = geo_form.cleaned_data

                    updated_customer = service.update_customer(
                        pk=pk,
                        customer_data=form.cleaned_data,
                        assignments_data=assignments_data,
                        class_margins_data=class_margins_data,
                        geo_profile_data=geo_data,
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
        geo_form = CustomerGeoProfileForm(instance=geo_profile_instance)

    context = {
        'form': form,
        'assignments_formset': assignments_formset,
        'class_margins_formset': class_margins_formset,
        'geo_form': geo_form,
        'updating': customer_instance,
        'can_update_access': can_edit_full,
        'can_edit_customer': can_edit_full,
        'can_edit_partially': can_edit_partially,
        'can_edit_geo_profile': can_edit_partially,
    }
    return render(request, template, context)

@login_required
@require_POST
def customer_add_note_view(request, pk: str):
    """
    view for creating a new note on the customer logbook
    """
    service = CustomersService(user=request.user)
    try:
        customer = service.read_customer(pk=pk)
    except (CustomerNotFound, PermissionsError) as e:
        messages.error(request, str(e))
        return redirect('customers:customer_list_view')
    except Exception as e:
        messages.error(request, f"Ocurrió un error al cargar el cliente: {str(e)}")
        return redirect('customers:customer_list_view')

    if not service.can_edit_partially(customer):
        messages.error(request, "No tienes permisos para agregar notas a este cliente.")
        return redirect('customers:customer_detail_view', pk=pk)

    form = CustomerNoteForm(request.POST)
    if form.is_valid():
        try:
            service.add_customer_note(
                customer=customer,
                category=form.cleaned_data['category'],
                content=form.cleaned_data['content'],
                is_pinned=form.cleaned_data.get('is_pinned', False),
            )
            messages.success(request, "Nota registrada exitosamente en la bitácora del cliente.")
        except PermissionsError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Error al guardar la nota: {str(e)}")
    else:
        messages.error(request, "Por favor completa el contenido de la nota.")

    return redirect('customers:customer_detail_view', pk=pk)

@login_required
@require_POST
def customer_add_contact_view(request, pk: str):
    """
    view for creating a new contact for the customer
    """
    service = CustomersService(user=request.user)
    try:
        customer = service.read_customer(pk=pk)
    except (CustomerNotFound, PermissionsError) as e:
        messages.error(request, str(e))
        return redirect('customers:customer_list_view')
    except Exception as e:
        messages.error(request, f"Ocurrió un error al cargar el cliente: {str(e)}")
        return redirect('customers:customer_list_view')

    if not service.can_edit_partially(customer):
        messages.error(request, "No tienes permisos para agregar contactos a este cliente.")
        return redirect('customers:customer_detail_view', pk=pk)

    form = CustomerContactForm(request.POST)
    if form.is_valid():
        try:
            service.add_customer_contact(
                customer=customer,
                name=form.cleaned_data['name'],
                role=form.cleaned_data['role'],
                phone=form.cleaned_data.get('phone'),
                mobile=form.cleaned_data.get('mobile'),
                email=form.cleaned_data.get('email'),
                is_primary=form.cleaned_data.get('is_primary', False),
                notes=form.cleaned_data.get('notes'),
            )
            messages.success(request, f'Contacto "{form.cleaned_data["name"].title()}" agregado exitosamente.')
        except (PermissionsError, ValidationError) as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Error al guardar el contacto: {str(e)}")
    else:
        error_msgs = [f"{errs[0]}" for field, errs in form.errors.items()]
        messages.error(request, f"Error en los datos del contacto: {', '.join(error_msgs)}")

    return redirect('customers:customer_detail_view', pk=pk)

@login_required
@require_POST
def customer_update_contact_view(request, pk: str, contact_id: int):
    """
    view for updating an existing contact of the customer
    """
    service = CustomersService(user=request.user)
    try:
        customer = service.read_customer(pk=pk)
    except (CustomerNotFound, PermissionsError) as e:
        messages.error(request, str(e))
        return redirect('customers:customer_list_view')
    except Exception as e:
        messages.error(request, f"Ocurrió un error al cargar el cliente: {str(e)}")
        return redirect('customers:customer_list_view')

    if not service.can_edit_partially(customer):
        messages.error(request, "No tienes permisos para editar contactos de este cliente.")
        return redirect('customers:customer_detail_view', pk=pk)

    form = CustomerContactForm(request.POST)
    if form.is_valid():
        try:
            service.update_customer_contact(
                contact=contact_id,
                name=form.cleaned_data['name'],
                role=form.cleaned_data['role'],
                phone=form.cleaned_data.get('phone'),
                mobile=form.cleaned_data.get('mobile'),
                email=form.cleaned_data.get('email'),
                is_primary=form.cleaned_data.get('is_primary', False),
                notes=form.cleaned_data.get('notes'),
            )
            messages.success(request, f'Contacto "{form.cleaned_data["name"]}" actualizado exitosamente.')
        except (CustomerContactNotFound, PermissionsError, ValidationError) as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Error al actualizar el contacto: {str(e)}")
    else:
        error_msgs = [f"{errs[0]}" for field, errs in form.errors.items()]
        messages.error(request, f"Error en los datos del contacto: {', '.join(error_msgs)}")

    return redirect('customers:customer_detail_view', pk=pk)

@login_required
@require_POST
def customer_delete_contact_view(request, pk: str, contact_id: int):
    """
    view for deleting an existing contact of the customer
    """
    service = CustomersService(user=request.user)
    try:
        customer = service.read_customer(pk=pk)
    except (CustomerNotFound, PermissionsError) as e:
        messages.error(request, str(e))
        return redirect('customers:customer_list_view')
    except Exception as e:
        messages.error(request, f"Ocurrió un error al cargar el cliente: {str(e)}")
        return redirect('customers:customer_list_view')

    if not service.can_edit_partially(customer):
        messages.error(request, "No tienes permisos para eliminar contactos de este cliente.")
        return redirect('customers:customer_detail_view', pk=pk)

    try:
        service.delete_customer_contact(contact=contact_id)
        messages.success(request, "Contacto eliminado correctamente.")
    except (CustomerContactNotFound, PermissionsError) as e:
        messages.error(request, str(e))
    except Exception as e:
        messages.error(request, f"Error al eliminar el contacto: {str(e)}")

    return redirect('customers:customer_detail_view', pk=pk)

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

@login_required
def customer_agreement_list_view(request):
    template = 'customers/customer_agreements/agreement_list.html'
    service = CustomerAgreementsService(user=request.user)
    stats_service = CustomerAgreementsStats(agreements_service=service)

    available_actions = None
    if service.has_full_access:
        available_actions = 'customers/customer_agreements/partials/agreement_list__actions.html'

    agreements_qs = service.read_agreements()
    agreement_filter = CustomerAgreementFilter(request.GET, queryset=agreements_qs, request=request)
    agreements_qs = agreement_filter.qs

    paginator = Paginator(agreements_qs, 50)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    query_dict = request.GET.copy()
    if 'page' in query_dict:
        del query_dict['page']

    agreements = page_obj.object_list
    kpis = stats_service.stats(qs=agreements_qs)

    context = {
        'agreements': agreements,
        'kpis': kpis,
        'query_string': query_dict.urlencode(),
        'page_obj': page_obj,
        'available_actions': available_actions,
        'filter': agreement_filter,
    }

    if request.htmx:
        target = request.headers.get('HX-Target')
        if target == 'agreement-list-content':
            return render(request, 'customers/customer_agreements/partials/agreement_list_content.html', context)
        return render(request, 'customers/customer_agreements/partials/agreement_list_rows.html', context)

    return render(request, template, context)


@login_required
def customer_agreement_detail_view(request, pk: int):
    template = 'customers/customer_agreements/agreement_detail.html'
    service = CustomerAgreementsService(user=request.user)

    try:
        agreement = service.read_agreement(pk=pk)
    except (CustomerAgreementNotFound, PermissionsError) as e:
        messages.error(request, str(e))
        return redirect('customers:customer_agreement_list_view')
    except Exception as e:
        messages.error(request, f"Ocurrió un error al cargar el convenio: {str(e)}")
        return redirect('customers:customer_agreement_list_view')

    is_seller = request.user.groups.filter(name='vendedor').exists()
    periods = agreement.evaluation_periods.all().prefetch_related('class_results__product_class')
    class_targets = agreement.class_targets.all().select_related('product_class')
    doc_form = CustomerAgreementDocumentForm(instance=agreement)

    available_actions = None
    if service.has_full_access:
        available_actions = 'customers/customer_agreements/partials/agreement_detail__actions.html'

    advisor_name = service.get_assigned_advisor_name(agreement.route, target_date=agreement.start_date)

    context = {
        'agreement': agreement,
        'advisor_name': advisor_name,
        'periods': periods,
        'class_targets': class_targets,
        'doc_form': doc_form,
        'is_seller': is_seller,
        'can_edit': service.can_edit_agreement,
        'available_actions': available_actions,
    }
    return render(request, template, context)


@login_required
def customer_agreement_create_view(request):
    template = 'customers/customer_agreements/agreement_create.html'
    service = CustomerAgreementsService(user=request.user)
    cust_service = CustomersService(user=request.user)

    if not service.has_full_access:
        messages.error(request, "No tienes permisos para crear convenios comerciales.")
        return redirect('customers:customer_agreement_list_view')

    allowed_customers = cust_service.read_customers().order_by('name', 'id')
    initial_customers = allowed_customers[:30]
    product_classes = ProductClass.objects.all().order_by('name', 'id')
    benefits = CommercialBenefit.objects.filter(is_active=True).order_by('name')

    if request.method == 'POST':
        form = CustomerAgreementCreateForm(request.POST, request.FILES, allowed_customers=allowed_customers)
        if form.is_valid():
            try:
                participating_class_ids = request.POST.getlist('participating_classes')
                if not participating_class_ids and request.POST.get('participating_classes_json'):
                    try:
                        participating_class_ids = json.loads(request.POST.get('participating_classes_json'))
                    except Exception:
                        participating_class_ids = []

                mandatory_targets = {}
                for key, val in request.POST.items():
                    if key.startswith('mandatory_target_') and val:
                        try:
                            cid = key.replace('mandatory_target_', '')
                            amt = Decimal(str(val))
                            if amt > 0:
                                mandatory_targets[cid] = amt
                        except Exception:
                            pass

                if not mandatory_targets and request.POST.get('mandatory_targets_json'):
                    try:
                        raw_mt = json.loads(request.POST.get('mandatory_targets_json'))
                        mandatory_targets = {k: Decimal(str(v)) for k, v in raw_mt.items() if Decimal(str(v)) > 0}
                    except Exception:
                        pass

                participating_classes_data = []
                for p_id in participating_class_ids:
                    p_id_str = str(p_id)
                    is_mand = p_id_str in mandatory_targets
                    req_target = mandatory_targets.get(p_id_str, Decimal('0.00'))
                    participating_classes_data.append({
                        'product_class_id': p_id_str,
                        'is_mandatory': is_mand,
                        'required_target': req_target,
                    })

                agreement = service.create_customer_agreement(
                    customer_id=form.cleaned_data['customer'].pk,
                    benefit_id=form.cleaned_data['benefit'].pk,
                    agreement_type=form.cleaned_data['agreement_type'],
                    evaluation_mode=form.cleaned_data.get('evaluation_mode', EvaluationModeChoices.PERIODIC),
                    start_date=form.cleaned_data['start_date'],
                    end_date=form.cleaned_data['end_date'],
                    global_target_amount=form.cleaned_data['global_target_amount'],
                    target_frequency=form.cleaned_data['target_frequency'],
                    growth_value=form.cleaned_data.get('growth_value') or Decimal('0.00'),
                    growth_frequency=form.cleaned_data.get('growth_frequency'),
                    penalty_amount=form.cleaned_data.get('penalty_amount') or Decimal('0.00'),
                    related_doc=request.FILES.get('related_doc'),
                    doc_id=form.cleaned_data.get('doc_id') or None,
                    participating_classes_data=participating_classes_data,
                    margin_warning_accepted=form.cleaned_data.get('margin_warning_accepted', False),
                )
                messages.success(request, f"Convenio {agreement.doc_id} creado exitosamente con {agreement.evaluation_periods.count()} periodos generados.")
                return redirect('customers:customer_agreement_detail_view', pk=agreement.pk)

            except MarginValidationException as e:
                form.add_error(None, f"Alerta de Margen: {e.message}")
                context = {
                    'form': form,
                    'benefits': benefits,
                    'product_classes': product_classes,
                    'initial_customers': initial_customers,
                    'margin_error': str(e),
                    'simulated_margin': e.simulated_margin,
                    'min_margin': e.min_margin,
                }
                return render(request, template, context)
            except ServiceError as e:
                form.add_error(None, str(e))
            except Exception as e:
                form.add_error(None, f"Ocurrió un error inesperado: {str(e)}")
    else:
        form = CustomerAgreementCreateForm(allowed_customers=allowed_customers)

    context = {
        'form': form,
        'benefits': benefits,
        'product_classes': product_classes,
        'initial_customers': initial_customers,
    }
    return render(request, template, context)

@login_required
def customer_agreement_validate_margin_view(request):
    """
    endpoint called dynamically from create form to evaluate customer margin.
    """
    service = CustomerAgreementsService(user=request.user)
    data = request.POST if request.method == 'POST' else request.GET

    customer_id = data.get('customer') or data.get('q')
    if customer_id:
        customer_id = str(customer_id).strip()
        cust_match = Customer.objects.filter(Q(id=customer_id) | Q(name__iexact=customer_id)).first()
        if not cust_match and len(customer_id) > 2:
            cust_match = Customer.objects.filter(Q(id__icontains=customer_id) | Q(name__icontains=customer_id)).first()
        if cust_match:
            customer_id = cust_match.id

    benefit_id = data.get('benefit')
    eval_start = data.get('eval_start')
    eval_end = data.get('eval_end')
    agreement_start_date = data.get('start_date')
    agreement_end_date = data.get('end_date')
    target_frequency = data.get('target_frequency')
    global_target = data.get('global_target_amount')
    growth_value = data.get('growth_value') or '0'
    growth_frequency = data.get('growth_frequency')

    # defst for evaluation dates if empty
    if not eval_end:
        today = timezone.localdate()
        prev_month = today.replace(day=1) - timedelta(days=1)
        eval_end = prev_month.strftime('%Y-%m')
    if not eval_start:
        end_d = parse_month_input(eval_end, is_end=True) or timezone.localdate()
        start_d = end_d - relativedelta(months=3)
        eval_start = start_d.strftime('%Y-%m')

    missing_fields = []
    if not customer_id:
        missing_fields.append("Cliente (búscalo y selecciónalo en el paso 1)")
    if not benefit_id:
        missing_fields.append("Beneficio comercial")
    if not agreement_start_date:
        missing_fields.append("Mes de inicio de vigencia")
    if not agreement_end_date:
        missing_fields.append("Mes de fin de vigencia")
    if not target_frequency:
        missing_fields.append("Frecuencia de evaluación")

    if missing_fields:
        return render(request, 'customers/customer_agreements/partials/margin_alert.html', {
            'error': f"Para simular el margen financiero, completa los siguientes campos: {', '.join(missing_fields)}.",
        })

    participating_class_ids = data.getlist('participating_classes')
    if not participating_class_ids and data.get('participating_classes_json'):
        try:
            participating_class_ids = json.loads(data.get('participating_classes_json'))
        except Exception:
            participating_class_ids = []

    mandatory_class_ids = set(data.getlist('mandatory_classes'))
    mandatory_targets = {}
    for key, val in data.items():
        if key.startswith('mandatory_target_') and val:
            try:
                cid = key.replace('mandatory_target_', '')
                amt = Decimal(str(val))
                if amt > 0:
                    mandatory_targets[cid] = amt
            except Exception:
                pass

    try:
        participating_classes_data = []
        for p_id in participating_class_ids:
            p_id_str = str(p_id)
            is_mand = (p_id_str in mandatory_class_ids) or (p_id_str in mandatory_targets)
            req_target = mandatory_targets.get(p_id_str, Decimal('0.00'))
            participating_classes_data.append({
                'product_class_id': p_id_str,
                'is_mandatory': is_mand,
                'required_target': req_target,
            })

        val_result = service.validate_agreement_margin(
            customer_id=customer_id,
            benefit_id=int(benefit_id),
            eval_start=eval_start,
            eval_end=eval_end,
            agreement_start_date=agreement_start_date,
            agreement_end_date=agreement_end_date,
            target_frequency=target_frequency,
            global_target_amount=Decimal(str(global_target)) if global_target else Decimal('0.00'),
            growth_value=Decimal(str(growth_value)) if growth_value else Decimal('0.00'),
            growth_frequency=growth_frequency,
            participating_classes_data=participating_classes_data,
        )

        if isinstance(val_result, tuple):
            is_valid, sim_margin, min_margin, vol_alert, res_dict = val_result
            res_dict['is_valid'] = is_valid
            res_dict['simulated_margin'] = sim_margin
            res_dict['min_margin'] = min_margin
            res_dict['volatility_alert'] = vol_alert
            result_context = res_dict
        else:
            result_context = val_result

        return render(request, 'customers/customer_agreements/partials/margin_alert.html', {
            'result': result_context,
        })
    except Exception as e:
        return render(request, 'customers/customer_agreements/partials/margin_alert.html', {
            'error': str(e),
        })


@login_required
def customer_agreement_preview_view(request):
    """
    modal endpoint returning printable contract preview and expected consumption matrix.
    """
    service = CustomerAgreementsService(user=request.user)
    data = request.POST if request.method == 'POST' else request.GET

    customer_id = data.get('customer') or data.get('q')
    if customer_id:
        customer_id = str(customer_id).strip()
        cust_match = Customer.objects.filter(Q(id=customer_id) | Q(name__iexact=customer_id)).first()
        if not cust_match and len(customer_id) > 2:
            cust_match = Customer.objects.filter(Q(id__icontains=customer_id) | Q(name__icontains=customer_id)).first()
        if cust_match:
            customer_id = cust_match.id

    benefit_id = data.get('benefit')
    agreement_type = data.get('agreement_type', AgreementTypeChoices.SHORT_TERM)
    evaluation_mode = data.get('evaluation_mode', EvaluationModeChoices.PERIODIC)
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    target_frequency = data.get('target_frequency', PeriodicityChoices.MONTHLY)
    global_target = data.get('global_target_amount')
    growth_value = data.get('growth_value') or '0'
    growth_frequency = data.get('growth_frequency')
    penalty_amount = data.get('penalty_amount') or '0'
    route_id = data.get('route') or data.get('route_id')
    doc_id = data.get('doc_id')
    if doc_id and str(doc_id).strip():
        doc_id = str(doc_id).strip().upper()
    else:
        doc_id = service.generate_random_doc_id()

    missing_fields = []
    if not customer_id:
        missing_fields.append("Cliente (búscalo y selecciónalo en el paso 1)")
    if not benefit_id:
        missing_fields.append("Beneficio comercial")
    if not start_date:
        missing_fields.append("Mes de inicio")
    if not end_date:
        missing_fields.append("Mes de fin")
    if not global_target:
        missing_fields.append("Cuota global")

    if missing_fields:
        return render(request, 'customers/customer_agreements/partials/agreement_preview.html', {
            'error': f"Para generar el previo, completa los siguientes campos: {', '.join(missing_fields)}.",
        })

    participating_class_ids = data.getlist('participating_classes')
    if not participating_class_ids and data.get('participating_classes_json'):
        try:
            participating_class_ids = json.loads(data.get('participating_classes_json'))
        except Exception:
            participating_class_ids = []

    mandatory_class_ids = set(data.getlist('mandatory_classes'))
    mandatory_targets = {}
    for key, val in data.items():
        if key.startswith('mandatory_target_') and val:
            try:
                cid = key.replace('mandatory_target_', '')
                amt = Decimal(str(val))
                if amt > 0:
                    mandatory_targets[cid] = amt
            except Exception:
                pass

    try:
        participating_classes_data = []
        for p_id in participating_class_ids:
            p_id_str = str(p_id)
            is_mand = (p_id_str in mandatory_class_ids) or (p_id_str in mandatory_targets)
            req_target = mandatory_targets.get(p_id_str, Decimal('0.00'))
            participating_classes_data.append({
                'product_class_id': p_id_str,
                'is_mandatory': is_mand,
                'required_target': req_target,
            })

        preview_data = service.generate_agreement_preview(
            customer_id=customer_id,
            benefit_id=int(benefit_id),
            agreement_type=agreement_type,
            evaluation_mode=evaluation_mode,
            start_date=start_date,
            end_date=end_date,
            global_target_amount=Decimal(str(global_target)),
            target_frequency=target_frequency,
            growth_value=Decimal(str(growth_value)) if growth_value else Decimal('0.00'),
            growth_frequency=growth_frequency,
            penalty_amount=Decimal(str(penalty_amount)) if penalty_amount else Decimal('0.00'),
            doc_id=doc_id,
            route_id=route_id,
            participating_classes_data=participating_classes_data,
        )

        return render(request, 'customers/customer_agreements/partials/agreement_preview.html', {
            'preview': preview_data,
        })
    except Exception as e:
        return render(request, 'customers/customer_agreements/partials/agreement_preview.html', {
            'error': str(e),
        })

@login_required
@require_POST
def customer_agreement_update_document_view(request, pk: int):
    service = CustomerAgreementsService(user=request.user)
    if not service.can_edit_agreement:
        messages.error(request, "No tienes permiso para modificar este convenio.")
        return redirect('customers:customer_agreement_detail_view', pk=pk)

    try:
        agreement = service.read_agreement(pk)
    except Exception as e:
        messages.error(request, str(e))
        return redirect('customers:customer_agreement_list_view')

    form = CustomerAgreementDocumentForm(request.POST, request.FILES, instance=agreement)
    if form.is_valid():
        try:
            service.update_agreement_execution(
                pk=pk,
                signed=form.cleaned_data.get('signed'),
                benefit_already_provided=form.cleaned_data.get('benefit_already_provided'),
                file_obj=request.FILES.get('related_doc'),
            )
            messages.success(request, "Convenio actualizado correctamente.")
        except PermissionsError as pe:
            messages.error(request, str(pe))
        except Exception as e:
            messages.error(request, f"Error al actualizar el convenio: {str(e)}")
    else:
        messages.error(request, "Datos de formulario inválidos.")
    return redirect('customers:customer_agreement_detail_view', pk=pk)


@login_required
@require_POST
def customer_agreement_evaluate_action_view(request, pk: int):
    service = CustomerAgreementsService(user=request.user)
    try:
        periods_count, _ = service.evaluate_pending_periods(pk=pk)
        messages.success(request, f"Evaluación completada: {periods_count} periodos analizados con ventas reales.")
    except Exception as e:
        messages.error(request, f"Error durante la evaluación: {str(e)}")
    return redirect('customers:customer_agreement_detail_view', pk=pk)


@login_required
def customer_agreement_search_customers_view(request):
    query = request.GET.get('q', '').strip()
    cust_service = CustomersService(user=request.user)
    customers_qs = cust_service.read_customers()
    if query:
        customers_qs = customers_qs.filter(Q(id__icontains=query) | Q(name__icontains=query))
    customers = customers_qs.order_by('name', 'id')[:25]
    return render(request, 'customers/customer_agreements/partials/customer_search_results.html', {
        'customers': customers,
    })


# used universally
@login_required
def customer_options_view(request):
    """
    Returns HTML option items for searchable customer dropdowns via HTMX.
    """
    q = request.GET.get('q_customer', request.GET.get('q', '')).strip()
    field_name = request.GET.get('field_name', 'customer')
    selected_id = request.GET.get('selected_id', '')

    cust_service = CustomersService(user=request.user)
    base_qs = cust_service.read_customers()

    if q:
        base_qs = base_qs.filter(
            Q(id__icontains=q) |
            Q(name__icontains=q)
        )

    customers = base_qs.order_by('name', 'id')[:30]

    return render(
        request,
        'customers/partials/customer_options.html',
        {
            'customers': customers,
            'field_name': field_name,
            'selected_id': str(selected_id),
        }
    )