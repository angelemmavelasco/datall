# pyrefly: ignore [missing-import]
from django.urls import path
from .views import *
# pyrefly: ignore [missing-import]
from django.views.generic import TemplateView

app_name='core'

urlpatterns = [

    path(
        'profile/password/change/', 
        CustomPasswordChangeView.as_view(), 
        name='password_change'
    ),
    path(
        'profile/password/change/done/', TemplateView.as_view(template_name='registration/password/password_change_done.html'), 
        name='password_change_done'
    ),

    path('support/', support, name='support'),
    path('app_versions/', app_versions, name='app_versions'),


    path('user_list/', user_list, name='user_list'),
    path('user/create/', user_create_form, name='user_create'),
    path('user/<int:pk>/edit/', user_update_form, name='user_update'),
    path('user/<int:pk>/', user_details, name='user_details'),
]