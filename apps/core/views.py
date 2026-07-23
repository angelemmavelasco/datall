from django.shortcuts import redirect, render
from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse
from django.contrib.auth.views import PasswordChangeView
from django.urls import reverse_lazy
from django.contrib.auth.decorators import login_required
from apps.app_management.models import AppVersion
from .forms import UserForm
from .services.users import UsersService
from django.core.paginator import Paginator

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
    template = "docs/user_docs.html"
    return render(request, template)

@login_required
def app_versions(request):
    template = "app_versions/app_versions.html"
    app_versions = AppVersion.objects.filter(is_published=True).order_by('-release_date', '-version_number')
    context = {
        'app_versions': app_versions
    }
    return render(request, template, context)

@login_required
def user_list(request):
    users_service = UsersService(request.user)
    users = users_service.read_users()
    
    paginator = Paginator(users, 100)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    if request.headers.get('HX-Request') == 'true':
        template = "users/partials/user_rows.html"
    else:
        template = "users/user_list.html"
        
    context = {
        'page_obj': page_obj,
    }
    return render(request, template, context)

@login_required
def user_create_form(request):
    template = "users/user_form.html"
    users_service = UsersService(request.user)

    if request.method == 'POST':
        form = UserForm(request.POST, request.FILES)
        if form.is_valid():
            print('Formulario validado')
            if not form.cleaned_data.get('password'):
                form.add_error('password', 'La contraseña es obligatoria para nuevos usuarios.')
            else:
                new_user = users_service.create_user(**form.cleaned_data)
                if new_user:
                    messages.success(request, 'Usuario creado correctamente.')
                    return redirect('core:user_list')
                else:
                    form.add_error(None, "No tienes permisos suficientes para crear usuarios.")
    else:
        form = UserForm()
    context = {
        'form': form,
    }
    return render(request, template, context)

@login_required
def user_update_form(request, user_id: int):
    template = "users/user_form.html"
    users_service = UsersService(request.user)
    user_to_edit = users_service.read_user(user_id)

    if not user_to_edit:
        messages.error(request, 'Usuario no encontrado.')
        return redirect('core:user_list')

    if request.method == 'POST':
        form = UserForm(request.POST, request.FILES, instance=user_to_edit)
        if form.is_valid():
            print('Formulario validado')
            updated_user = users_service.update_user(user_id, **form.cleaned_data)
            if updated_user:
                messages.success(request, 'Usuario actualizado correctamente.')
                return redirect('core:user_list')
            else:
                form.add_error(None, "No tienes permisos suficientes para actualizar el usuario.")
    else:
        form = UserForm(instance=user_to_edit)
        form.initial['password'] = ''

    context = {
        'form': form,
        'is_editing': True,
    }
    return render(request, template, context)
    