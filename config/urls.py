"""
URL configuration for project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, include
from django.views.generic import RedirectView
from django.conf import settings

urlpatterns = [
    path('', RedirectView.as_view(url='/accounts/login/', permanent=False)),
    path('accounts/', include('django.contrib.auth.urls')),

    #view where user enters their email
    path('reset_password/', auth_views.PasswordResetView.as_view(
        template_name='registration/password/password_reset.html',
        from_email=settings.RESET_PASSWORD_FROM_EMAIL), name='reset_password'),
    #Message saying an email was sent
    path('reset_password_sent/', auth_views.PasswordResetDoneView.as_view(template_name="registration/password/password_reset_sent.html"), name="password_reset_done"),
    #view where pwd is reset
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name="registration/password/password_reset_form.html"), name="password_reset_confirm"),
    #Succesfully reset message
    path('reset_password_complete/', auth_views.PasswordResetCompleteView.as_view(template_name="registration/password/password_reset_done.html"), name="password_reset_complete"),

    path('admin/', admin.site.urls),
    path('data_assistant/', include('apps.data_assistant.urls')),

    path('sales/', include('apps.sales.urls')),
    path('marketing/', include('apps.marketing.urls')),
    path('customers/', include('apps.customers.urls')),
    path('data_admin/', include('apps.data_admin.urls')),
    path('human_resources/', include('apps.human_resources.urls')),
    path('business_intelligence/', include('apps.business_intelligence.urls')),
    path('core/', include('apps.core.urls')),
]

handler404 = 'apps.core.views.custom_404_view'
handler500 = 'apps.core.views.custom_500_view'

from django.conf.urls.static import static

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
