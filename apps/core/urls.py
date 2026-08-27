from django.urls import path
from django.contrib.auth import views as auth_views
from .views import *

app_name = 'core'

urlpatterns = [
    path('', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    
    # Password Change URLs
    path('password_change/', auth_views.PasswordChangeView.as_view(
        template_name='registration/password/password_change_form.html',
        success_url='/password_change/done/'
    ), name='password_change'),
    path('password_change/done/', auth_views.PasswordChangeDoneView.as_view(
        template_name='registration/password/password_change_done.html'
    ), name='password_change_done'),

    # Password Reset URLs
    path('password_reset/', auth_views.PasswordResetView.as_view(
        template_name='registration/password/password_reset.html',
        email_template_name='registration/password/password_reset_email.html',
        success_url='/password_reset/done/'
    ), name='reset_password'),
    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='registration/password/password_reset_sent.html'
    ), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='registration/password/password_reset_form.html',
        success_url='/reset/done/'
    ), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(
        template_name='registration/password/password_reset_done.html'
    ), name='password_reset_complete'),

    path('hello-world/', hello_world, name='hello_world'),

    path('users/', user_list_view, name='user_list_view'),
    path('users/options/', user_options_view, name='user_options_view'),
    path('users/<int:pk>/', user_detail_view, name='user_detail_view'),
    path('users/create/', user_create_form_view, name='user_create_form_view'),
    path('users/<int:pk>/update/', user_update_form_view, name='user_update_form_view'),

    # Uploads
    path('uploads/', upload_options_list_view, name='upload_options_list_view'),

    # Reports
    path('reports/partial/', user_reports_partial_view, name='user_reports_partial_view'),
    path('reports/indicator/', reports_indicator_view, name='reports_indicator_view'),

    # Error preview routes
    path('403/', error_403_view, name='error_403'),
    path('404/', error_404_view, name='error_404'),
    path('500/', error_500_view, name='error_500'),
]

