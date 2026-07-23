from django.urls import path
from .views import CustomPasswordChangeView, support, app_versions
from django.views.generic import TemplateView\

from .views import *

app_name='core'

urlpatterns = [
    path('profile/password/change/', CustomPasswordChangeView.as_view(), name='password_change'),
    path('profile/password/change/done/', TemplateView.as_view(template_name='registration/password/password_change_done.html'), name='password_change_done'),

    path('support/', support, name='support'),
    path('app_versions/', app_versions, name='app_versions'),

    path('user_list/', user_list, name='user_list'),
    path('create_user/', user_form, name='create_user')
]