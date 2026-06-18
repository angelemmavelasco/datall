from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from datetime import datetime

from apps.core.models import DataHistory, Customer, Route, Benefit, Periodicity, ProductClass
from apps.data_admin.services.data_history.data_history_crud import DataHistoryCrud
from apps.customers.services.customer_agreements.customer_agreements import CustomerAgreementCRUD


@login_required
def customer_agreements(request):
    template = 'customers/customer_agreements/customer_agreements.html'
    
    agreements = CustomerAgreementCRUD.read_agreements()

    context = {
        'agreements': agreements
    }

    DataHistoryCrud().log_action(
        request=request,
        action=DataHistory.Action.READ,
        description="Consulta de convenios de clientes."
    )
    return render(request, template, context)



@login_required
def customer_agreement_create(request):
    template = 'customers/customer_agreements/customer_agreement_create.html'

    customers = Customer.objects.all().order_by('name')
    routes = Route.objects.all().order_by('id')
    benefits = Benefit.objects.filter(is_active=True).order_by('name')
    periodicities = Periodicity.objects.filter(months_duration__isnull=False).order_by('months_duration')
    product_classes = ProductClass.objects.all().order_by('name')

    agreements = CustomerAgreementCRUD.read_agreements()

    context = {
        'agreements': agreements,
        'customers': customers,
        'routes': routes,
        'benefits': benefits,
        'periodicities': periodicities,
        'product_classes': product_classes
    }

    if request.method == 'POST':

        try:
            data = request.POST.dict()
            product_lines = []
            for pc in product_classes:
                target_val = request.POST.get(f'line_target_{pc.id}')
                is_selected = request.POST.get(f'line_selected_{pc.id}')
                if is_selected == 'on':
                    product_lines.append({
                        'product_class_id': pc.id,
                        'target': target_val if target_val else '0'
                    })
            data['product_lines'] = product_lines
        
            if not data.get('target_freq_id'): data['target_freq_id'] = None
            if not data.get('penalty_freq_id'): data['penalty_freq_id'] = None
            if not data.get('growth_freq_id'): data['growth_freq_id'] = None
            if 'related_doc' in request.FILES:
                data['related_doc'] = request.FILES['related_doc']

            if request.POST.get('target_freq_end') == 'on':
                data['target_freq_id'] = None
            if request.POST.get('penalty_freq_end') == 'on':
                data['penalty_freq_id'] = None

            CustomerAgreementCRUD.create_agreement(data)
            messages.success(request, 'Convenio creado con éxito.')
            
            DataHistoryCrud().log_action(
                request=request,
                action=DataHistory.Action.CREATE,
                description=f"Creación de convenio comercial para cliente {data['customer_id']}.",
                changes={'doc_id': data.get('doc_id'), 'target_amount': data.get('target_amount')}
            )
            return redirect('customers:customer_agreements')

        except Exception as e:
            messages.error(request, f'Error al crear convenio: {str(e)}')
            return redirect('customers:customer_agreement_create')

    DataHistoryCrud().log_action(
        request=request,
        action=DataHistory.Action.READ,
        description="Vista de creación de convenio."
    )

    return render(request, template, context)