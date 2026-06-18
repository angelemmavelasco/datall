from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.contrib.auth.models import Group

from django.contrib.contenttypes.models import ContentType
from django.core.paginator import Paginator


from datetime import date


from apps.core.models import SystemModule,DataHistory
from apps.data_admin.services.users import users_crud
from apps.data_admin.services.groups import groups_crud
from apps.customers.services.customers_crud.customer_bulk import CustomersBulk
from apps.data_admin.services.data_history.data_history_crud import DataHistoryCrud


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
    DataHistoryCrud().log_action(
        request=request,
        action=DataHistory.Action.READ,
        description="Consulta del catálogo de usuarios.",
        changes={"filters": current_filters}
    )

    return render(request, TEMPLATE, context)

@login_required
def user(request, user_id: int = None):
    users_service = users_crud.UsersCRUD()
    user_groups = request.user.groups.all()

    context = {}

    if request.method == 'POST':
        user_obj_before = users_service.get_user(user_id=user_id)
        from django.forms.models import model_to_dict
        old_state = model_to_dict(user_obj_before) if user_obj_before else {}

        raw_data = request.POST.dict()
        selected_groups = request.POST.getlist('groups')
        update_success = users_service.process_user_update(user_id=user_id, raw_data=raw_data, selected_groups=selected_groups)

        if update_success:
            updated_user = users_service.get_user(user_id=user_id)
            new_state = model_to_dict(updated_user) if updated_user else {}
            from django.contrib.auth import get_user_model
            DataHistoryCrud().log_action(
                request=request,
                action=DataHistory.Action.UPDATE,
                content_type=ContentType.objects.get_for_model(get_user_model()),
                object_id=str(user_id),
                description=f"Actualización del usuario {user_id}.",
                changes={"old_state": old_state, "new_state": new_state}
            )
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
    DataHistoryCrud().log_action(
        request=request,
        action=DataHistory.Action.READ,
        description=f"Consulta de detalles del usuario {user_id}.",
        changes={"user_id": user_id}
    )

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
            from django.forms.models import model_to_dict
            new_state = model_to_dict(new_user)
            from django.contrib.auth import get_user_model
            DataHistoryCrud().log_action(
                request=request,
                action=DataHistory.Action.CREATE,
                content_type=ContentType.objects.get_for_model(get_user_model()),
                object_id=str(new_user.id),
                description=f"Creación del usuario {new_user.username}.",
                changes={"new_state": new_state}
            )
            messages.success(request, f'Usuario {new_user.username} creado con éxito.')
            #redirect to user page detailed
            return redirect('data_admin:user', user_id=new_user.id)
        else:
            messages.error(request,
                           'Error al crear: Verifica los datos obligatorios o intenta con otro nombre de usuario.')

            #return to user create page with errors
            context['user'] = raw_data
            return render(request, TEMPLATE, context)

    DataHistoryCrud().log_action(
        request=request,
        action=DataHistory.Action.READ,
        description="Consulta del formulario de creación de usuario."
    )
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
    
    DataHistoryCrud().log_action(
        request=request,
        action=DataHistory.Action.READ,
        description="Consulta del catálogo de grupos.",
        changes={"filters": current_filters}
    )
    return render(request, TEMPLATE, context)

@login_required
def group(request, group_id: int = None):
    groups_service = groups_crud.GroupsCRUD()
    TEMPLATE = 'data_admin/groups/group.html'
    
    context = {}
    
    if request.method == 'POST':
        group_obj_before = groups_service.get_group(group_id=group_id)
        from django.forms.models import model_to_dict
        old_state = model_to_dict(group_obj_before) if group_obj_before else {}
        if group_obj_before:
            old_state['modules'] = list(group_obj_before.accessible_modules.values_list('id', flat=True))

        raw_data = request.POST.dict()
        selected_modules = request.POST.getlist('modules')
        
        update_success = groups_service.process_group_update(
            group_id=group_id, 
            raw_data=raw_data, 
            selected_modules=selected_modules
        )

        if update_success:
            updated_group = groups_service.get_group(group_id=group_id)
            new_state = model_to_dict(updated_group) if updated_group else {}
            if updated_group:
                new_state['modules'] = list(updated_group.accessible_modules.values_list('id', flat=True))
            from django.contrib.auth.models import Group
            DataHistoryCrud().log_action(
                request=request,
                action=DataHistory.Action.UPDATE,
                content_type=ContentType.objects.get_for_model(Group),
                object_id=str(group_id),
                description=f"Actualización del grupo {group_id}.",
                changes={"old_state": old_state, "new_state": new_state}
            )
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

    DataHistoryCrud().log_action(
        request=request,
        action=DataHistory.Action.READ,
        description=f"Consulta de detalles del grupo {group_id}.",
        changes={"group_id": group_id}
    )
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
            from django.forms.models import model_to_dict
            new_state = model_to_dict(new_group)
            new_state['modules'] = list(new_group.accessible_modules.values_list('id', flat=True))
            from django.contrib.auth.models import Group
            DataHistoryCrud().log_action(
                request=request,
                action=DataHistory.Action.CREATE,
                content_type=ContentType.objects.get_for_model(Group),
                object_id=str(new_group.id),
                description=f"Creación del grupo {new_group.name}.",
                changes={"new_state": new_state}
            )
            messages.success(request, f'Grupo "{new_group.name}" creado con éxito.')
            return redirect('data_admin:group', group_id=new_group.id)
        else:
            messages.error(request, 'Error al crear: Verifica que el nombre no esté vacío o en uso.')
            context['group'] = raw_data
            return render(request, TEMPLATE, context)

    DataHistoryCrud().log_action(
        request=request,
        action=DataHistory.Action.READ,
        description="Consulta del formulario de creación de grupo."
    )
    return render(request, TEMPLATE, context)



@login_required
def uploads(request):
    TEMPLATE = 'data_admin/uploads/uploads.html'
    


    # Filters
    query_text = request.GET.get('query_text')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    selected_results = request.GET.getlist('results')
    selected_actions = request.GET.getlist('actions')

    filters = {}
    if query_text: filters['search_query'] = query_text
    if start_date: filters['start_date'] = start_date
    if end_date: filters['end_date'] = end_date
    if selected_results: filters['results'] = selected_results

    # If no specific action is selected, default to import and export
    if selected_actions:
        filters['actions'] = selected_actions
    else:
        filters['actions'] = [DataHistory.Action.IMPORT, DataHistory.Action.EXPORT]

    crud = DataHistoryCrud()
    qs = crud.get_histories(**filters)

    paginator = Paginator(qs, 50)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'uploads': page_obj.object_list,
        'page_obj': page_obj,

        'query_text': query_text,
        'start_date': start_date,
        'end_date': end_date,
        'selected_results': selected_results,
        'selected_actions': selected_actions,

        'filter_results': [{'id': r[0], 'name': r[1]} for r in DataHistory.Result.choices],
        'filter_actions': [{'id': a[0], 'name': a[1]} for a in DataHistory.Action.choices if a[0] in [DataHistory.Action.IMPORT, DataHistory.Action.EXPORT]],
    }
    
    DataHistoryCrud().log_action(
        request=request,
        action=DataHistory.Action.READ,
        description="Consulta de historial de cargas masivas.",
        changes={"filters": filters}
    )
    
    if request.htmx:
        return render(request, 'data_admin/uploads/partials/uploads_rows.html', context)
    
    return render(request, TEMPLATE, context)



@login_required
def upload_create(request):
    TEMPLATE = 'data_admin/uploads/upload_create.html'
    
    from apps.core.models import DataHistory
    from apps.data_admin.services.data_history.data_history_crud import DataHistoryCrud

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
            
        def audit_upload(status, message):
            crud = DataHistoryCrud()
            crud.log_action(
                request=request,
                action=DataHistory.Action.IMPORT,
                result=status,
                content_type=content_type,
                description=message,
                changes={"filename": uploaded_file.name}
            )

        if content_type.model == 'customer':
            bulk_service = CustomersBulk()
            success, result = bulk_service.clean(uploaded_file)
            
            if not success:
                audit_upload(DataHistory.Result.ERROR, result)
                messages.error(request, result)
                return redirect('data_admin:upload_create')
            
            df_cleaned = result
            success_create, msg = bulk_service.create(df_cleaned)
            
            if success_create:
                audit_upload(DataHistory.Result.SUCCESS, msg)
                messages.success(request, msg)
                return redirect('data_admin:uploads')
            else:
                audit_upload(DataHistory.Result.ERROR, msg)
                messages.error(request, msg)
                return redirect('data_admin:upload_create')
                
        elif content_type.model == 'product':
            from apps.sales.services.products.products_bulk import ProductsBulk
            bulk_service = ProductsBulk()
            success, result = bulk_service.clean(uploaded_file)
            
            if not success:
                audit_upload(DataHistory.Result.ERROR, result)
                messages.error(request, result)
                return redirect('data_admin:upload_create')
            
            df_cleaned = result
            success_create, msg = bulk_service.create(df_cleaned)
            
            if success_create:
                audit_upload(DataHistory.Result.SUCCESS, msg)
                messages.success(request, msg)
                return redirect('data_admin:uploads')
            else:
                audit_upload(DataHistory.Result.ERROR, msg)
                messages.error(request, msg)
                return redirect('data_admin:upload_create')
                
        elif content_type.model == 'saletransaction':
            from apps.sales.services.sale_transactions.sales_transactions_bulk import SalesTransactionsBulk
            bulk_service = SalesTransactionsBulk()
            success, result = bulk_service.clean(uploaded_file)
            
            if not success:
                audit_upload(DataHistory.Result.ERROR, result)
                messages.error(request, result)
                return redirect('data_admin:upload_create')
            
            df_cleaned = result
            success_create, msg = bulk_service.create(df_cleaned)
            
            if success_create:
                audit_upload(DataHistory.Result.SUCCESS, msg)
                messages.success(request, msg)
                return redirect('data_admin:uploads')
            else:
                audit_upload(DataHistory.Result.ERROR, msg)
                messages.error(request, msg)
                return redirect('data_admin:upload_create')

        elif content_type.model == 'saletarget':
            from apps.sales.services.sale_targets.sale_targets_bulk import SaleTargetsBulk
            bulk_service = SaleTargetsBulk()
            success, result = bulk_service.clean(uploaded_file)
            
            if not success:
                audit_upload(DataHistory.Result.ERROR, result)
                messages.error(request, result)
                return redirect('data_admin:upload_create')
            
            df_cleaned = result
            success_create, msg = bulk_service.create(df_cleaned)
            
            if success_create:
                audit_upload(DataHistory.Result.SUCCESS, msg)
                messages.success(request, msg)
                return redirect('data_admin:uploads')
            else:
                audit_upload(DataHistory.Result.ERROR, msg)
                messages.error(request, msg)
                return redirect('data_admin:upload_create')
        else:
            msg = f"Todavía no hay un servicio de importación masiva configurado para el modelo: {content_type.model.title()}."
            audit_upload(DataHistory.Result.ERROR, msg)
            messages.warning(request, msg)
            return redirect('data_admin:upload_create')

    content_types = ContentType.objects.all().order_by('model')

    context = {
        'content_types': content_types,
    }

    DataHistoryCrud().log_action(
        request=request,
        action=DataHistory.Action.READ,
        description="Consulta del formulario de carga masiva."
    )
    return render(request, TEMPLATE, context)




@login_required
def activity(request):
    TEMPLATE = 'data_admin/activity/activity.html'

    date_start = request.POST.get('date_start')
    date_end = request.POST.get('date_end')
    users = request.POST.getlist('users')
    actions = request.POST.getlist('actions')
    results = request.POST.getlist('results')
    modules = request.POST.getlist('modules')


    today = date.today()
    if not date_start: date_start = today.replace(day=1)
    if not date_end: date_end = today

    filters = {}
    filters['start_date'] = date_start
    filters['end_date'] = date_end
    if users:
        filters['users'] = users
    if actions:
        filters['actions'] = actions
    if results:
        filters['results'] = results
    if modules:
        filters['modules'] = modules
    

    service = DataHistoryCrud()
    logs = service.get_histories(**filters)
    
    context = {
        'logs': logs,
    }
    DataHistoryCrud().log_action(
        request=request,
        action=DataHistory.Action.READ,
        description="Consulta de historial de actividad del sistema.",
        changes={"filters": filters}
    )
    return render(request, TEMPLATE, context)



@login_required
def activity_detail(request, activity_id):
    template = 'data_admin/activity/activity_detail.html'
    context = {}

    service = DataHistoryCrud()
    log = service.get_history(history_id =  activity_id)

    if log is None:
        messages.error(request, "No se encontró la actividad.")
        return redirect('data_admin:activity')
    
    context['log'] = log
    DataHistoryCrud().log_action(
        request=request,
        action=DataHistory.Action.READ,
        description=f"Consulta del detalle de actividad {activity_id}.",
        changes={"activity_id": activity_id}
    )
    return render(request, template, context)
    