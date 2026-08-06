from django.urls import path
from .views import *
app_name = 'human_resources'

urlpatterns = [
    path('departments/', department_list_view, name='department_list_view'),
]