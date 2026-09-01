from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.urls import reverse

from apps.core.services.uploads import UploadsService, BaseETLHelper
from apps.human_resources.services.employees import EmployeesService

from django.utils import timezone
from django_q.tasks import async_task
from .filters import UserFilter
from .forms import UserForm
from .models import User, GeneratedReport, Reference

from .services.users import UsersService, UsersKPIsService, ServiceError, UserNotFoundError, UserPermissionError

def custom_csrf_failure_view(request, reason=""):
    """
    personalized handler for csrf failure
    """
    if request.headers.get('HX-Request') or getattr(request, 'htmx', False):
        response = HttpResponse(status=200)
        response['HX-Redirect'] = reverse('core:login')
        return response

    messages.warning(
        request,
        'Tu sesión o el formulario ha expirado por inactividad. Por favor inicia sesión nuevamente para continuar.'
    )
    return redirect('core:login')

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
    employees_service = EmployeesService(user=request.user)
    can_update_access = users_service.has_full_access

    if not users_service.has_full_access and str(pk) != str(request.user.pk):
        messages.error(request, 'No tienes permisos suficientes para acceder a otros usuarios. Has sido redirigido a tu perfil.')
        return redirect('core:user_detail_view', pk=request.user.pk)

    try:
        user_instance = users_service.read_user(pk=pk)
    except UserNotFoundError:
        messages.error(request, 'El usuario solicitado no existe.')
        if users_service.has_full_access:
            return redirect('core:user_list_view')
        return redirect('core:user_detail_view', pk=request.user.pk)
    except UserPermissionError as e:
        messages.error(request, str(e))
        if users_service.has_full_access:
            return redirect('core:user_list_view')
        return redirect('core:user_detail_view', pk=request.user.pk)
    except Exception as e:
        messages.error(request, f'Ocurrió un error inesperado al consultar el usuario: {str(e)}')
        if users_service.has_full_access:
            return redirect('core:user_list_view')
        return redirect('core:user_detail_view', pk=request.user.pk)

    if not user_instance:
        messages.error(request, 'Usuario no encontrado o no tienes permisos para verlo.')
        if users_service.has_full_access:
            return redirect('core:user_list_view')
        return redirect('core:user_detail_view', pk=request.user.pk)

    user_employees = employees_service.read_employees_by_user(user_id=user_instance.pk)

    context = {
        'user_instance': user_instance,
        'user_employees': user_employees,
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

    if not users_service.has_full_access and str(pk) != str(request.user.pk):
        messages.error(request, 'No tienes permisos suficientes para editar otros usuarios. Has sido redirigido a tu perfil.')
        return redirect('core:user_update_form_view', pk=request.user.pk)

    try:
        user_instance = users_service.read_user(pk=pk)
    except UserNotFoundError:
        messages.error(request, 'El usuario solicitado no existe.')
        if users_service.has_full_access:
            return redirect('core:user_list_view')
        return redirect('core:user_detail_view', pk=request.user.pk)
    except UserPermissionError:
        messages.error(request, 'No tienes permisos suficientes para acceder a este usuario.')
        if users_service.has_full_access:
            return redirect('core:user_list_view')
        return redirect('core:user_detail_view', pk=request.user.pk)
    except Exception as e:
        messages.error(request, f'Ocurrió un error inesperado al consultar el usuario: {str(e)}')
        if users_service.has_full_access:
            return redirect('core:user_list_view')
        return redirect('core:user_detail_view', pk=request.user.pk)

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
        action = request.POST.get('action', '').strip()
        if action == 'update_last_reports_date':
            service = UploadsService(user=request.user)
            try:
                service.validate_permission()
            except Exception as e:
                messages.error(request, str(e))
                return redirect('core:upload_options_list_view')

            raw_datetime = request.POST.get('last_update_datetime', '').strip()
            if not raw_datetime:
                messages.error(request, 'Debes seleccionar una fecha y hora.')
                return redirect('core:upload_options_list_view')

            months_es = {
                1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril',
                5: 'Mayo', 6: 'Junio', 7: 'Julio', 8: 'Agosto',
                9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre'
            }

            try:
                dt = timezone.datetime.fromisoformat(raw_datetime)
                formatted_value = f"{dt.day} de {months_es.get(dt.month, '')} de {dt.year}, {dt.strftime('%H:%M')} hrs"
            except Exception:
                formatted_value = raw_datetime

            ref, _ = Reference.objects.get_or_create(
                context='ultima_actualizacion_reportes',
                key='datetime'
            )
            ref.value = formatted_value
            ref.save()

            messages.success(request, f"Se actualizó la fecha de corte a: {formatted_value}")
            return redirect('core:upload_options_list_view')

        model_key = request.POST.get('model_key', '').strip().lower()
        file_obj = request.FILES.get('file')

        if not model_key:
            messages.error(request, 'No se especificó la entidad o catálogo a importar.')
            return redirect('core:upload_options_list_view')

        if not file_obj:
            messages.error(request, 'Debes seleccionar un archivo para importar (.xlsx, .xls, .csv).')
            return redirect('core:upload_options_list_view')

        service = UploadsService(user=request.user)

        try:
            service.validate_permission()
        except Exception as e:
            messages.error(request, str(e))
            return redirect('core:upload_options_list_view')

        is_valid_file, file_err = BaseETLHelper.validate_file(file_obj)
        if not is_valid_file:
            messages.error(request, file_err)
            return redirect('core:upload_options_list_view')

        catalog_titles = {
            'product': 'Catálogo de Productos',
            'customer': 'Catálogo de Clientes',
            'saletransaction': 'Transacciones de Venta',
            'accountsreceivable': 'Cuentas por Cobrar',
            'stock': 'Existencias (Stock)',
            'denueinegi': 'Directorio DENUE (INEGI)',
            'denue': 'Directorio DENUE (INEGI)',
        }
        title_label = catalog_titles.get(model_key, model_key.title())

        try:
            report = GeneratedReport.objects.create(
                user=request.user,
                title=f"Importación: {title_label}",
                module_name="uploads",
                file=file_obj,
                file_size=file_obj.size,
                status=GeneratedReport.Status.PENDING,
                filters={'model_key': model_key, 'filename': getattr(file_obj, 'name', '')},
            )

            async_task(
                'apps.core.tasks.process_bulk_upload_task',
                report.id,
                model_key,
                request.user.id,
            )

            messages.info(
                request,
                f"El archivo para {title_label} se ha cargado correctamente y se está procesando en segundo plano. Puedes consultar el progreso y los resultados en 'Mis Archivos'."
            )
        except Exception as e:
            messages.error(request, f"Error al iniciar el procesamiento del archivo: {str(e)}")

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
        {
            'key': 'denueinegi',
            'title': 'Directorio DENUE (INEGI)',
            'model_name': 'DenueInegi',
            'app_label': 'Mapser / Prospección',
            'description': 'Directorio Estadístico Nacional de Unidades Económicas para prospección geográfica y análisis de penetración de mercado.',
            'icon': 'map-pin',
            'tags': ['CSV / Excel', 'INEGI', 'Georreferenciación', 'Alto Volumen'],
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
def report_download_view(request, pk: int):
    """
    secure download handler for generated reports.
    avoids WSGI FileWrapper resource deadlock on macOS / Docker dev mounts
    and validates user permissions.
    """
    report = get_object_or_404(GeneratedReport, pk=pk)

    if not (request.user.is_superuser or report.user == request.user or request.user.has_perm('core.view_generatedreport')):
        messages.error(request, "No tienes permiso para descargar este reporte.")
        return redirect(request.META.get('HTTP_REFERER', '/'))

    if not report.file:
        messages.error(request, "El archivo solicitado no se encuentra disponible.")
        return redirect(request.META.get('HTTP_REFERER', '/'))

    filename = report.file.name.split('/')[-1]
    content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    if filename.endswith('.csv'):
        content_type = 'text/csv'
    elif filename.endswith('.pdf'):
        content_type = 'application/pdf'
    elif filename.endswith('.txt'):
        content_type = 'text/plain'

    try:
        report.file.open('rb')
        file_data = report.file.read()
        report.file.close()

        response = HttpResponse(file_data, content_type=content_type)
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response['Content-Length'] = len(file_data)
        return response
    except Exception as e:
        messages.error(request, f"Error al descargar el archivo: {e}")
        return redirect(request.META.get('HTTP_REFERER', '/'))


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

#used universally
@login_required
def user_options_view(request):
    """
    Returns HTML option items for searchable user dropdowns via HTMX.
    """
    q = request.GET.get('q_user', request.GET.get('q', '')).strip()
    field_name = request.GET.get('field_name', 'user')
    selected_id = request.GET.get('selected_id', '')

    base_qs = User.objects.filter(is_active=True)

    if q:
        from django.db.models import Q
        base_qs = base_qs.filter(
            Q(username__icontains=q) |
            Q(first_name__icontains=q) |
            Q(last_name__icontains=q) |
            Q(email__icontains=q)
        )

    users = base_qs.order_by('first_name', 'last_name', 'username')[:30]

    return render(
        request,
        'core/users/partials/user_options.html',
        {
            'users': users,
            'field_name': field_name,
            'selected_id': str(selected_id),
        }
    )


