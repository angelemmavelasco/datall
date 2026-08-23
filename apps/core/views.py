from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required

from .filters import UserFilter
from .forms import UserForm
from .models import User, GeneratedReport
from .services.users import UsersService, UsersKPIsService, ServiceError, UserNotFoundError, UserPermissionError

def error_400_view(request, exception=None):
    context = {
        'LOGIN_REDIRECT_URL': getattr(settings, 'LOGIN_REDIRECT_URL', '/hello-world/'),
        'exception': str(exception) if exception else None,
    }
    template_name = getattr(settings, 'BAD_REQUEST', getattr(settings, 'PAGE_NOT_FOUND', 'errors/404.html'))
    return render(request, template_name, context, status=400)


def error_403_view(request, exception=None):
    context = {
        'email': getattr(settings, 'SUPPORT_EMAIL', getattr(settings, 'DEFAULT_FROM_EMAIL', 'soporte@datall.com.mx')),
        'LOGIN_REDIRECT_URL': getattr(settings, 'LOGIN_REDIRECT_URL', '/hello-world/'),
        'exception': str(exception) if exception else None,
    }
    template_name = getattr(settings, 'ACCESS_DENIED', 'errors/access_denied.html')
    return render(request, template_name, context, status=403)


def error_404_view(request, exception=None):
    context = {
        'LOGIN_REDIRECT_URL': getattr(settings, 'LOGIN_REDIRECT_URL', '/hello-world/'),
        'exception': str(exception) if exception else None,
    }
    template_name = getattr(settings, 'PAGE_NOT_FOUND', 'errors/404.html')
    return render(request, template_name, context, status=404)


def error_500_view(request):
    context = {
        'LOGIN_REDIRECT_URL': getattr(settings, 'LOGIN_REDIRECT_URL', '/hello-world/'),
        'email': getattr(settings, 'SUPPORT_EMAIL', getattr(settings, 'DEFAULT_FROM_EMAIL', 'soporte@datall.com.mx')),
    }
    template_name = getattr(settings, 'INTERNAL_SERVER_ERROR', 'errors/500.html')
    return render(request, template_name, context, status=500)

@login_required
def hello_world(request):
    template = 'hello_world.html'
    context = {
        'message': 'Hola mundo desde datall'
    }
    
    return render(request, template, context)

@login_required
def user_list_view(request):
    template = 'core/users/user_list.html'
    users_service = UsersService(user=request.user)
    users_kpis_service = UsersKPIsService(users_service=users_service)
    can_create = users_service.has_full_access

    users_qs = users_service.read_users().order_by('first_name')
    user_filter = UserFilter(request.GET, queryset=users_qs)
    users_qs = user_filter.qs

    paginator = Paginator(users_qs, 100)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    query_dict = request.GET.copy()
    if 'page' in query_dict: del query_dict['page']

    users = page_obj.object_list

    kpis = users_kpis_service.stats(qs=users_qs)

    context = {
        'users': users,
        'kpis': kpis,
        'query_string': query_dict.urlencode(),
        'page_obj': page_obj,
        'can_create': can_create,
        'filter': user_filter
    }

    if request.htmx:
        target = request.headers.get('HX-Target')
        if target == 'user-list-content':
            return render(request, 'core/users/partials/user_list_content.html', context)
        return render(request, 'core/users/partials/user_list_rows.html', context)

    return render(request, template, context)

@login_required
def user_detail_view(request, pk):
    template = 'core/users/user_detail.html'
    users_service = UsersService(user=request.user)
    # employees_service = EmployeesService(user=request.user)
    can_update_access = users_service.has_full_access

    user_instance = users_service.read_user(pk=pk)
    if not user_instance:
        messages.error(request, 'Usuario no encontrado o no tienes permisos para verlo.')
        return redirect('core:user_list')

    # user_positions = employees_service.read_employees_by_user(user_id=user_instance.pk)

    context = {
        'user_instance': user_instance,
        # 'user_positions': user_positions,
        'can_update_access': can_update_access
    }
    return render(request, template, context)

@login_required
def user_create_form_view(request):
    users_service = UsersService(user=request.user)
    template = 'core/users/user_form.html'
    creating = True

    if not users_service.has_full_access and not getattr(request.user, 'is_superuser', False):
        messages.error(request, 'No tienes permisos para crear usuarios.')
        return redirect('core:user_list_view')

    if request.method == 'POST':
        form = UserForm(
            request.POST,
            request.FILES,
            requesting_user=request.user,
            is_full_access=users_service.has_full_access
        )
        if form.is_valid():
            try:
                new_user = users_service.create_user(**form.cleaned_data)
                messages.success(request, f'Usuario {new_user.username} creado correctamente.')
                return redirect('core:user_detail_view', new_user.pk)

            except UserPermissionError as e:
                messages.error(request, str(e))
                return redirect('core:user_list_view')

            except ServiceError as e:
                messages.error(request, str(e))

            except Exception as e:
                messages.error(request, f"Ocurrió un error inesperado al crear: {str(e)}")
        else:
            messages.error(request, 'Por favor revisa los errores en el formulario.')
    else:
        form = UserForm(
            requesting_user=request.user,
            is_full_access=users_service._is_full_access
        )

    context = {
        'form': form,
        'creating': creating,
        'can_update_access': users_service._is_full_access
    }

    return render(request, template, context)


@login_required
def user_update_form_view(request, pk):
    template = 'core/users/user_form.html'
    users_service = UsersService(user=request.user)
    can_update = users_service.has_full_access
    creating = False

    try:
        user_instance = users_service.read_user(pk=pk)
    except UserNotFoundError:
        messages.error(request, 'El usuario solicitado no existe.')
        return redirect('core:user_list_view')
    except UserPermissionError:
        messages.warning(request, 'No tienes permisos suficientes para acceder a este usuario.')
        return redirect('core:user_list_view')
    except Exception as e:
        messages.error(request, f'Ocurrió un error inesperado al consultar el usuario: {str(e)}')
        return redirect('core:user_list_view')

    if request.method == 'POST':
        form = UserForm(
            request.POST,
            request.FILES,
            instance=user_instance,
            requesting_user=request.user,
            is_full_access=users_service.has_full_access
        )
        if form.is_valid():
            try:
                updated_user = users_service.update_user(pk=pk, **form.cleaned_data)
                messages.success(request, 'Usuario actualizado correctamente.')
                return redirect('core:user_detail_view', updated_user.pk)

            except (UserNotFoundError, UserPermissionError) as e:
                messages.error(request, str(e))
                return redirect('core:user_list_view')

            except ServiceError as e:
                messages.error(request, str(e))

            except Exception as e:
                messages.error(request, f"Ocurrió un error inesperado: {str(e)}")
        else:
            messages.error(request, 'Por favor revisa los errores en el formulario.')
    else:
        form = UserForm(
            instance=user_instance,
            requesting_user=request.user,
            is_full_access=users_service.has_full_access
        )

    context = {
        'form': form,
        'creating': creating,
        'can_update_access': can_update,
    }

    return render(request, template, context)

@login_required
def user_delete_view(request, pk: int):
    pass

@login_required
def module_list_view(request):
    pass

@login_required
def module_detail_view(request, pk: int):
    pass

@login_required
def module_create_view(request):
    pass

@login_required
def module_update_view(request, pk: int):
    pass


@login_required
def upload_options_list_view(request):
    template = 'core/uploads/upload_options_list.html'

    if request.method == 'POST':
        model_key = request.POST.get('model_key', '').strip()
        file_obj = request.FILES.get('file')

        if not model_key:
            messages.error(request, 'No se especificó la entidad o catálogo a importar.')
            return redirect('core:upload_options_list_view')

        if not file_obj:
            messages.error(request, 'Debes seleccionar un archivo para importar (.xlsx, .xls, .csv).')
            return redirect('core:upload_options_list_view')

        from apps.core.services.uploads import UploadsService
        service = UploadsService(user=request.user)
        result = service.process_upload(model_key=model_key, file_obj=file_obj)

        if result.success:
            messages.success(request, result.message)
        else:
            messages.error(request, result.message)

        return redirect('core:upload_options_list_view')

    upload_options = [
        {
            'key': 'product',
            'title': 'Catálogo de Productos',
            'model_name': 'Product',
            'app_label': 'Inventario / Productos',
            'description': 'Actualización e importación del catálogo maestro de productos, precios, costos y clases de producto.',
            'icon': 'box',
            'tags': ['CSV / Excel', 'Mapeo de Clases', 'Upsert'],
        },
        {
            'key': 'customer',
            'title': 'Catálogo de Clientes',
            'model_name': 'Customer',
            'app_label': 'Clientes',
            'description': 'Importación masiva de clientes, tipos de cliente, condiciones comerciales y fechas de registro.',
            'icon': 'users',
            'tags': ['CSV / Excel', 'Mapeo de Tipos', 'Preserva Líderes'],
        },
        {
            'key': 'saletransaction',
            'title': 'Transacciones de Venta',
            'model_name': 'SaleTransaction',
            'app_label': 'Ventas',
            'description': 'Carga transaccional de ventas por producto, cliente, ruta y centro de distribución con cálculo de utilidades.',
            'icon': 'receipt',
            'tags': ['CSV / Excel', 'Doble Perspectiva', 'Alto Volumen'],
        },
        {
            'key': 'accountsreceivable',
            'title': 'Cuentas por Cobrar',
            'model_name': 'AccountsReceivable',
            'app_label': 'Clientes / Cartera',
            'description': 'Importación de documentos de cartera, saldos corrientes y desglose de antigüedad de saldos vencidos.',
            'icon': 'landmark',
            'tags': ['CSV / Excel', 'Antigüedad 15/30/60d', 'Saldos'],
        },
        {
            'key': 'stock',
            'title': 'Existencias (Stock)',
            'model_name': 'Stock',
            'app_label': 'Inventario / Stock',
            'description': 'Carga masiva de existencias físicas por centro de distribución, números de lote y fechas de caducidad.',
            'icon': 'warehouse',
            'tags': ['CSV / Excel', 'Por Almacén', 'Control de Lotes'],
        },
    ]

    context = {
        'upload_options': upload_options,
    }
    return render(request, template, context)


@login_required
def user_reports_partial_view(request):
    """Returns the list of generated reports for the current user and marks them as seen"""
    reports = GeneratedReport.objects.filter(user=request.user).order_by('-created_at')[:20]
    GeneratedReport.objects.filter(
        user=request.user,
        status__in=[GeneratedReport.Status.COMPLETED, GeneratedReport.Status.FAILED],
        is_seen=False
    ).update(is_seen=True)
    return render(request, 'core/partials/_user_reports_list.html', {'user_reports': reports})


@login_required
def reports_indicator_view(request):
    """Returns the nav indicator partial with smart polling status and animated alert icon"""
    has_pending = GeneratedReport.objects.filter(
        user=request.user,
        status=GeneratedReport.Status.PENDING
    ).exists()

    has_unseen = GeneratedReport.objects.filter(
        user=request.user,
        status__in=[GeneratedReport.Status.COMPLETED, GeneratedReport.Status.FAILED],
        is_seen=False
    ).exists()

    context = {
        'has_pending_reports': has_pending,
        'has_unseen_reports': has_unseen,
    }
    return render(request, 'core/partials/_reports_nav_indicator.html', context)


