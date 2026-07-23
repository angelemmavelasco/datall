from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import TaxSystemForm
from .services.tax_systems import TaxSystemsService

@login_required
def tax_system_list(request):
    template = "accounting/tax_system_list.html"
    service = TaxSystemsService(request.user)
    
    # Todos pueden ver
    tax_systems = service.read_tax_systems()
    
    context = {
        'tax_systems': tax_systems
    }
    return render(request, template, context)


@login_required
def tax_system_create_form(request):
    template = "accounting/tax_system_form.html"
    service = TaxSystemsService(request.user)
    
    if request.method == 'POST':
        form = TaxSystemForm(request.POST)
        if form.is_valid():
            try:
                new_tax_system = service.create_tax_system(**form.cleaned_data)
                if new_tax_system:
                    messages.success(request, 'Régimen fiscal creado correctamente.')
                    return redirect('accounting:tax_system_list')
                else:
                    messages.error(request, 'No tienes permisos suficientes para crear regímenes fiscales.')
            except Exception as e:
                messages.error(request, f'Ocurrió un error al crear el régimen fiscal: {str(e)}')
    else:
        form = TaxSystemForm()
        
    context = {
        'form': form,
    }
    return render(request, template, context)


@login_required
def tax_system_update_form(request, tax_system_id: str):
    template = "accounting/tax_system_form.html"
    service = TaxSystemsService(request.user)
    
    tax_system_to_edit = service.read_tax_system(tax_system_id)
    if not tax_system_to_edit:
        messages.error(request, 'Régimen fiscal no encontrado.')
        return redirect('accounting:tax_system_list')
        
    if request.method == 'POST':
        form = TaxSystemForm(request.POST, instance=tax_system_to_edit)
        if form.is_valid():
            try:
                updated_tax_system = service.update_tax_system(tax_system_id, **form.cleaned_data)
                if updated_tax_system:
                    messages.success(request, 'Régimen fiscal actualizado correctamente.')
                    return redirect('accounting:tax_system_list')
                else:
                    messages.error(request, 'No tienes permisos suficientes para actualizar este régimen fiscal.')
            except Exception as e:
                messages.error(request, f'Ocurrió un error al actualizar el régimen fiscal: {str(e)}')
    else:
        form = TaxSystemForm(instance=tax_system_to_edit)
        
    context = {
        'form': form,
        'is_editing': True,
    }
    return render(request, template, context)
