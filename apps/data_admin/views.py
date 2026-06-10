from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse

from apps.data_admin.services.users import users_crud
from apps.data_admin.services.groups import groups_crud
from apps.core.models import SystemModule
from django.contrib.auth.models import Group


@login_required
def users(request):
    TEMPLATE = 'data_admin/users/users.html'
    users_service = users_crud.UsersCRUD()
    user_groups = request.user.groups.all()
    

    #get params from url by get method
    search_query = request.GET.get('q', '').strip()
    city = request.GET.get('city', '').strip()
    state = request.GET.get('state', '').strip()

    #status
    is_active_str = request.GET.get('is_active')
    is_active = True if is_active_str == 'True' else False if is_active_str == 'False' else None

    #groups
    groups_list = request.GET.getlist('groups')
    groups_list = [int(r) for r in groups_list if r.isdigit()] if groups_list else None

    #gender
    gender = request.GET.getlist('gender')
    gender = gender if gender else None

    #get users
    users_qs = users_service.get_users(
        search_query=search_query,
        groups=groups_list,
        is_active=is_active,
        gender=gender,
        city=city,
        state=state
    )

    current_filters = {
        'q': search_query,
        'city': city,
        'state': state,
        'is_active': is_active,
        'groups': groups_list,
        'gender': gender
    }
    
    all_groups = Group.objects.all()

    context = {
        'users': users_qs,
        'current_filters': current_filters,
        'user_groups': user_groups,
        'all_groups': all_groups,
    }

    return render(request, TEMPLATE, context)

@login_required
def user(request, user_id: int = None):
    users_service = users_crud.UsersCRUD()
    user_groups = request.user.groups.all()

    context = {}

    if request.method == 'POST':
        raw_data = request.POST.dict()
        selected_groups = request.POST.getlist('groups')
        update_success = users_service.process_user_update(user_id=user_id, raw_data=raw_data, selected_groups=selected_groups)

        if update_success:
            messages.success(request, 'Usuario actualizado con éxito.')
        else:
            messages.error(request, 'Error al actualizar: Verifica que los datos obligatorios estén completos.')

        return redirect('data_admin:user', user_id=user_id)

    user_obj = users_service.get_user(user_id=user_id)

    if not user_obj:
        messages.error(request, 'El usuario no existe.')
        return redirect('data_admin:users')

    all_groups = Group.objects.all()
    accessible_modules = SystemModule.objects.filter(allowed_groups__in=user_obj.groups.all()).distinct().select_related('section')

    context['user'] = user_obj
    context['user_groups'] = user_groups
    context['all_groups'] = all_groups
    context['user_obj_group_ids'] = list(user_obj.groups.values_list('id', flat=True))
    context['accessible_modules'] = accessible_modules

    return render(request, 'data_admin/users/user.html', context)


@login_required
def user_create(request):
    users_service = users_crud.UsersCRUD()
    user_groups = request.user.groups.all()
    TEMPLATE = 'data_admin/users/user_create.html'

    all_groups = Group.objects.all()
    
    context = {
        'user_groups': user_groups,
        'all_groups': all_groups
    }

    if request.method == 'POST':
        raw_data = request.POST.dict()
        selected_groups = request.POST.getlist('groups')

        new_user = users_service.process_user_create(raw_data=raw_data, selected_groups=selected_groups)

        if new_user:
            messages.success(request, f'Usuario {new_user.username} creado con éxito.')
            #redirect to user page detailed
            return redirect('data_admin:user', user_id=new_user.id)
        else:
            messages.error(request,
                           'Error al crear: Verifica los datos obligatorios o intenta con otro nombre de usuario.')

            #return to user create page with errors
            context['user'] = raw_data
            return render(request, TEMPLATE, context)

    return render(request, TEMPLATE, context)

@login_required
def groups(request):
    TEMPLATE = 'data_admin/groups/groups.html'
    groups_service = groups_crud.GroupsCRUD()
    
    search_query = request.GET.get('q', '').strip()
    
    groups_qs = groups_service.get_groups(search_query=search_query)
    
    current_filters = {
        'q': search_query,
    }
    
    context = {
        'groups': groups_qs,
        'current_filters': current_filters,
    }
    
    return render(request, TEMPLATE, context)

@login_required
def group(request, group_id: int = None):
    groups_service = groups_crud.GroupsCRUD()
    TEMPLATE = 'data_admin/groups/group.html'
    
    context = {}
    
    if request.method == 'POST':
        raw_data = request.POST.dict()
        selected_modules = request.POST.getlist('modules')
        
        update_success = groups_service.process_group_update(
            group_id=group_id, 
            raw_data=raw_data, 
            selected_modules=selected_modules
        )

        if update_success:
            messages.success(request, 'Grupo actualizado con éxito.')
        else:
            messages.error(request, 'Error al actualizar: Verifica que el nombre no esté vacío o en uso.')

        return redirect('data_admin:group', group_id=group_id)

    group_obj = groups_service.get_group(group_id=group_id)

    if not group_obj:
        messages.error(request, 'El grupo no existe.')
        return redirect('data_admin:groups')
        
    users_qs = groups_service.get_users_in_group(group_id=group_id)
    all_modules = SystemModule.objects.all().select_related('section')

    context['group'] = group_obj
    context['users'] = users_qs
    context['all_modules'] = all_modules
    context['group_modules_ids'] = list(group_obj.accessible_modules.values_list('id', flat=True))

    return render(request, TEMPLATE, context)

@login_required
def group_create(request):

    groups_service = groups_crud.GroupsCRUD()
    TEMPLATE = 'data_admin/groups/group_create.html'
    
    all_modules = SystemModule.objects.all().select_related('section')

    context = {
        'all_modules': all_modules
    }

    if request.method == 'POST':
        raw_data = request.POST.dict()
        selected_modules = request.POST.getlist('modules')

        new_group = groups_service.process_group_create(
            raw_data=raw_data, 
            selected_modules=selected_modules
        )

        if new_group:
            messages.success(request, f'Grupo "{new_group.name}" creado con éxito.')
            return redirect('data_admin:group', group_id=new_group.id)
        else:
            messages.error(request, 'Error al crear: Verifica que el nombre no esté vacío o en uso.')
            context['group'] = raw_data
            return render(request, TEMPLATE, context)

    return render(request, TEMPLATE, context)



@login_required
def uploads(request):
    TEMPLATE = 'data_admin/uploads/uploads.html'
    
    
    context = {}
    
    return render(request, TEMPLATE, context)


from django.contrib.contenttypes.models import ContentType
from apps.customers.services.customers_crud.customer_bulk import CustomersBulk

@login_required
def upload_create(request):
    TEMPLATE = 'data_admin/uploads/upload_create.html'

    if request.method == 'POST':
        content_type_id = request.POST.get('content_type_id')
        uploaded_file = request.FILES.get('file')

        if not content_type_id or not uploaded_file:
            messages.error(request, "Debe seleccionar un modelo y adjuntar un archivo válido.")
            return redirect('data_admin:upload_create')

        try:
            content_type = ContentType.objects.get(id=content_type_id)
        except ContentType.DoesNotExist:
            messages.error(request, "El modelo seleccionado no existe.")
            return redirect('data_admin:upload_create')

        if content_type.model == 'customer':
            bulk_service = CustomersBulk()
            success, result = bulk_service.clean(uploaded_file)
            
            if not success:
                messages.error(request, result)
                return redirect('data_admin:upload_create')
            
            df_cleaned = result
            success_create, msg = bulk_service.create(df_cleaned)
            
            if success_create:
                messages.success(request, msg)
                return redirect('data_admin:uploads')
            else:
                messages.error(request, msg)
                return redirect('data_admin:upload_create')
                
        elif content_type.model == 'product':
            from apps.sales.services.products.products_bulk import ProductsBulk
            bulk_service = ProductsBulk()
            success, result = bulk_service.clean(uploaded_file)
            
            if not success:
                messages.error(request, result)
                return redirect('data_admin:upload_create')
            
            df_cleaned = result
            success_create, msg = bulk_service.create(df_cleaned)
            
            if success_create:
                messages.success(request, msg)
                return redirect('data_admin:uploads')
            else:
                messages.error(request, msg)
                return redirect('data_admin:upload_create')
                
        elif content_type.model == 'saletransaction':
            from apps.sales.services.sale_transactions.sales_transactions_bulk import SalesTransactionsBulk
            bulk_service = SalesTransactionsBulk()
            success, result = bulk_service.clean(uploaded_file)
            
            if not success:
                messages.error(request, result)
                return redirect('data_admin:upload_create')
            
            df_cleaned = result
            success_create, msg = bulk_service.create(df_cleaned)
            
            if success_create:
                messages.success(request, msg)
                return redirect('data_admin:uploads')
            else:
                messages.error(request, msg)
                return redirect('data_admin:upload_create')

        elif content_type.model == 'saletarget':
            from apps.sales.services.sale_targets.sale_targets_bulk import SaleTargetsBulk
            bulk_service = SaleTargetsBulk()
            success, result = bulk_service.clean(uploaded_file)
            
            if not success:
                messages.error(request, result)
                return redirect('data_admin:upload_create')
            
            df_cleaned = result
            success_create, msg = bulk_service.create(df_cleaned)
            
            if success_create:
                messages.success(request, msg)
                return redirect('data_admin:uploads')
            else:
                messages.error(request, msg)
                return redirect('data_admin:upload_create')
        else:
            messages.warning(request, f"Todavía no hay un servicio de importación masiva configurado para el modelo: {content_type.model.title()}.")
            return redirect('data_admin:upload_create')

    content_types = ContentType.objects.all().order_by('model')

    context = {
        'content_types': content_types,
    }

    return render(request, TEMPLATE, context)




@login_required
def activity(request):
    TEMPLATE = 'data_admin/activity/activity.html'
    
    
    context = {}
    
    return render(request, TEMPLATE, context)