from django.shortcuts import redirect, render
from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse
from django.contrib.auth.views import PasswordChangeView
from django.urls import reverse_lazy
from django.contrib.auth.decorators import login_required
from apps.data_admin.services.data_history.data_history_crud import ActivityLogger
from apps.core.models import SystemModule, AppVersion

from django.core.paginator import Paginator
from apps.core.filters import UserFilter
from apps.core.services.users import (
    UsersService, 
    UsersKPIsService, 
    ServiceError, 
    UserPermissionError, 
    UserNotFoundError
)
from apps.core.forms import UserForm
from apps.human_resources.services.employees_service import EmployeesService


def custom_csrf_failure(request, reason=""):
    messages.warning(request, "Tu sesión expiró por inactividad. Por favor, vuelve a ingresar.")
    if "HX-Request" in request.headers:
        response = HttpResponse()
        response['HX-Redirect'] = settings.LOGIN_URL
        return response
    return redirect(settings.LOGIN_URL)

def custom_404_view(request, exception):
    context = {
        'LOGIN_REDIRECT_URL': settings.LOGIN_REDIRECT_URL
    }
    return render(request, 'errors/404.html', context, status=404)

def custom_500_view(request):
    context = {
        'LOGIN_REDIRECT_URL': settings.LOGIN_REDIRECT_URL
    }
    return render(request, 'errors/500.html', context, status=500)


class CustomPasswordChangeView(PasswordChangeView):
    template_name = 'registration/password/password_change_form.html'
    success_url = reverse_lazy('core:password_change_done')

    def form_valid(self, form):
        return super().form_valid(form)


@login_required
def support(request):
    
    module = SystemModule.objects.filter(url_name='core:support').first()
    ActivityLogger.log_read(
        user=request.user,
        module=module,
        description="visualización del manual de usuario / soporte."
    )
    
    template = "docs/user_docs.html"
    return render(request, template)

@login_required
def app_versions(request):
    template = "app_versions/app_versions.html"

    app_versions = AppVersion.objects.filter(is_published=True).order_by('-release_date', '-version_number')
    print(app_versions)

    context = {
        'app_versions': app_versions
    }



    module = SystemModule.objects.filter(url_name='core:app_versions').first()
    ActivityLogger.log_read(
        user=request.user,
        module=module,
        description="visualización de las versiones de la aplicación."
    )
    
    return render(request, template, context)


@login_required
def user_list(request):
    template = 'core/users/user_list.html'
    users_service = UsersService(user=request.user)
    users_kpis_service = UsersKPIsService(users_service=users_service)
    can_create = users_service._checkout_full_access

    users_qs = users_service.read_users().order_by('first_name')
    user_filter = UserFilter(request.GET, queryset=users_qs)
    users_qs = user_filter.qs

    paginator = Paginator(users_qs, 100)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    query_dict = request.GET.copy()
    if 'page' in query_dict: del query_dict['page']

    users = page_obj.object_list

    kpis = users_kpis_service.stats

    context = {
        'users': users,
        'kpis': kpis,
        'query_string': query_dict.urlencode(),
        'page_obj': page_obj,
        'can_create': can_create,
        'filter': user_filter
    }

    if request.htmx:
        return render(request, 'core/users/partials/user_list_rows.html', context)

    return render(request, template, context)

@login_required
def user_create_form(request):
    template = 'core/users/user_form.html'
    users_service = UsersService(user=request.user)
    creating = True
    can_update_access = users_service._checkout_full_access

    if request.method == 'POST':
        form = UserForm(
            request.POST, 
            request.FILES,
            requesting_user=request.user,
            is_full_access=users_service._is_full_access
        )
        if form.is_valid():
            try:
                new_user = users_service.create_user(**form.cleaned_data)
                messages.success(request, 'Usuario creado correctamente.')
                return redirect('core:user_details', pk=new_user.id)
            except ServiceError as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, f"Ocurrió un error inesperado: {str(e)}")
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
        'can_update_access': can_update_access
    }

    return render(request, template, context)

@login_required
def user_details(request, pk):
    template = 'core/users/user_details.html'
    users_service = UsersService(user=request.user)
    employees_service = EmployeesService(user=request.user)
    can_update_access = users_service._checkout_full_access

    user_instance = users_service.read_user(pk=pk)
    user_positions = employees_service.read_employees_by_user(user_id=user_instance.id)
    if not user_instance:
        messages.error(request, 'Usuario no encontrado o no tienes permisos para verlo.')
        return redirect('core:user_list')

    context = {
        'user_instance': user_instance,
        'user_positions': user_positions,
        'can_update_access': can_update_access
    }
    return render(request, template, context)


@login_required
def user_update_form(request, pk):
    template = 'core/users/user_form.html'
    users_service = UsersService(user=request.user)
    can_update_access = users_service._checkout_full_access
    creating = False

    user_instance = users_service.read_user(pk=pk)
    if not user_instance:
        messages.error(request, 'Usuario no encontrado o no tienes permisos para editarlo.')
        return redirect('core:user_list')

    if request.method == 'POST':
        form = UserForm(
            request.POST, 
            request.FILES,
            instance=user_instance,
            requesting_user=request.user,
            is_full_access=users_service._is_full_access
        )
        if form.is_valid():
            try:
                updated_user = users_service.update_user(pk=pk, **form.cleaned_data)
                messages.success(request, 'Usuario actualizado correctamente.')
                return redirect('core:user_details', updated_user.pk)
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
            is_full_access=users_service._is_full_access
        )

    context = {
        'form': form,
        'creating': creating,
        'can_update_access': can_update_access
    }

    return render(request, template, context)
    

    

    