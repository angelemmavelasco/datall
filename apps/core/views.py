from django.shortcuts import redirect, render
from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse
from django.contrib.auth.views import PasswordChangeView
from django.urls import reverse_lazy
from django.contrib.auth.decorators import login_required
from apps.app_management.models import AppVersion

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
def user_list_view(request):
    template = "users/user_list.html"
    from apps.core.services.users import UsersService
    users_service = UsersService(request.user)
    users = users_service.read_users()
    context = {
        'users': users,
    }
    return render(request, template, context)
    