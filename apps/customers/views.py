from django.shortcuts import render, HttpResponse
from django.contrib.auth.decorators import login_required
from apps.core.utils import get_allowed_routes_for_user, get_allowed_warehouses_for_user
from apps.core.models import Region, Customer, CommercialBenefit, Periodicity, ProductClass, CustomerAgreement
from apps.customers.services.customer_agreements.customer_agreements import CustomerAgreementService

from datetime import datetime, date
import uuid

@login_required
def customer_agreements(request):
    allowed_routes = get_allowed_routes_for_user(request.user)
    allowed_warehouses = get_allowed_warehouses_for_user(request.user)
    allowed_regions = Region.objects.filter(warehouses__in=allowed_warehouses).distinct()
    template = 'customers/customer_agreements/customer_agreements.html'

    # get filters
    today = date.today()
    if request.GET:
        status = request.GET.getlist('status', [])
    else:
        status = ['active']
        
    created_start = request.GET.get('created_start', '')
    created_end = request.GET.get('created_end', '')
    finished_start = request.GET.get('finished_start', '')
    finished_end = request.GET.get('finished_end', '')
    routes = request.GET.getlist('routes', [])
    warehouses = request.GET.getlist('warehouses', [])
    regions = request.GET.getlist('regions', [])
    
    filters = {}

    context = {
        'filter_routes': allowed_routes,
        'filter_warehouses': allowed_warehouses,
        'filter_regions': allowed_regions,

        # selected filters
        'selected_status': status,
        'selected_created_start': created_start,
        'selected_created_end': created_end,
        'selected_finished_start': finished_start,
        'selected_finished_end': finished_end,
        'selected_routes': routes,
        'selected_warehouses': warehouses,
        'selected_regions': regions,

    }
    return render(request, template, context)

@login_required
def create_customer_agreement(request):
    allowed_routes = get_allowed_routes_for_user(request.user)
    allowed_customers = Customer.objects.filter(route__in=allowed_routes).order_by('name')
    benefits = CommercialBenefit.objects.filter(is_active=True).order_by('name')
    periodicities = Periodicity.objects.all()
    product_classes = ProductClass.objects.all().order_by('name')
    agreement_types = CustomerAgreement.TypesChoices.choices
    
    template = 'customers/customer_agreements/create_customer_agreement.html'
    context = {
        'allowed_routes': allowed_routes,
        'allowed_customers': allowed_customers,
        'benefits': benefits,
        'periodicities': periodicities,
        'product_classes': product_classes,
        'agreement_types': agreement_types
    }
    
    if request.method == 'POST':
        pass

    return render(request, template, context)

@login_required
def validate_customer_agreement(request):
    print('margin validation')
    if request.method == 'POST':
        customer_id = request.POST.get('customer_id')
        benefit_id = request.POST.get('benefit_id')
        eval_start = request.POST.get('eval_customer_start')
        eval_end = request.POST.get('eval_customer_end')
        agreement_start = request.POST.get('start_date')
        agreement_end = request.POST.get('end_date')
        target_freq_id = request.POST.get('target_freq_id')
        
        # classes
        product_class_ids = request.POST.getlist('participating_classes[]')
        
        if not (customer_id and benefit_id and eval_start and eval_end and agreement_start and agreement_end and target_freq_id):
            print('faltan datos')
            return HttpResponse("Faltan datos para la validación (asegúrese de ingresar fechas y periodicidad).", status=400)
            
        service = CustomerAgreementService()
        is_valid, simulated_margin, max_req_margin, is_volatility_alert, data = service.validate_agreement_margin(
            customer_id, benefit_id, product_class_ids, eval_start, eval_end, agreement_start, agreement_end, target_freq_id
        )
        print(is_valid)
        
        context = {
            'is_valid': is_valid,
            'simulated_margin': simulated_margin,
            'min_margin': max_req_margin,
            'is_volatility_alert': is_volatility_alert,
            'avg_monthly_margin': data.get('avg_monthly_margin'),
            'total_profit': data.get('total_profit'),
            'total_net': data.get('total_net'),
            'past_cost': data.get('past_cost'),
            'cme': data.get('cme')
        }
        return render(request, 'customers/customer_agreements/partials/margin_alert.html', context)
        
@login_required
def save_customer_agreement(request):
    if request.method == 'POST':
        # Retrieve form data
        data = {
            'customer_id': request.POST.get('customer_id'),
            'benefit_id': request.POST.get('benefit_id'),
            'doc_id': request.POST.get('doc_id'),
            'agreement_name': request.POST.get('agreement_name'),
            'agreement_type': request.POST.get('agreement_type'),
            'start_date': request.POST.get('start_date'),
            'end_date': request.POST.get('end_date') or None,
            'global_target_amount': request.POST.get('global_target_amount') or 0,
            'target_freq_id': request.POST.get('target_freq_id'),
            'penalty_freq_id': request.POST.get('penalty_freq_id') or None,
            'growth_freq_id': request.POST.get('growth_freq_id') or None,
            'penalty_amount': request.POST.get('penalty_amount') or 0,
            'growth_value': request.POST.get('growth_value') or 0,
            'related_doc': request.FILES.get('related_doc')
        }
        
        margin_warning_accepted = request.POST.get('accept_margin_warning') == 'on'
        
        participating_class_ids = request.POST.getlist('participating_classes[]')
        
        targets_data = []
        for pc_id in participating_class_ids:
            is_mandatory = request.POST.get(f'is_mandatory_{pc_id}') == 'on'
            raw_target = request.POST.get(f'required_target_{pc_id}')
            required_target = raw_target if raw_target else 0
            
            targets_data.append({
                'product_class_id': pc_id,
                'required_target': required_target,
                'is_mandatory': is_mandatory
            })
            
        service = CustomerAgreementService()
        
        try:
            agreement = service.create_customer_agreement(request.user, data, targets_data, margin_warning_accepted)
            return HttpResponse('<script>window.location.href="/customers/customer_agreements/";</script>')
        except Exception as e:
            return HttpResponse(f"Error al guardar: {str(e)}", status=400)


@login_required
def evaluate_agreements_action(request):
    if request.method == 'POST':
        service = CustomerAgreementService()
        try:
            service.evaluate_all_pending_periods()
            return HttpResponse('<script>window.location.reload();</script>')
        except Exception as e:
            return HttpResponse(f"Error en evaluación: {str(e)}", status=400)
