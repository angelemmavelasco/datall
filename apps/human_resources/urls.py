from django.urls import path
from .views import *
app_name = 'human_resources'

urlpatterns = [
    path('departments/', department_list_view, name='department_list_view'),
    path('departments/details/<str:pk>/', department_detail_view, name='department_detail_view'),
    path('departments/create/', department_create_view, name='department_create_view'),
    path('departments/update/<str:pk>/', department_update_view, name='department_update_view'),

    path('positions/', position_list_view, name='position_list_view'),
    path('positions/details/<str:pk>/', position_detail_view, name='position_detail_view'),
    path('positions/create/', position_create_view, name='position_create_view'),
    path('positions/update/<str:pk>/', position_update_view, name='position_update_view'),
    

    path('position-skills/', position_skill_list_view, name='position_skill_list_view'),
    path('positions-skills/<int:pk>/', position_skill_detail_view, name='position_skill_detail_view'),
    path('position-skills/create/', position_skill_create_view, name='position_skill_create_view'),
    path('position-skills/update/<int:pk>/', position_skill_update_view, name='position_skill_update_view'),

    path('monitoring-forms/', monitoring_form_list_view, name='monitoring_form_list_view'),
    path('monitoring-forms/details/<str:pk>/', monitoring_form_detail_view, name='monitoring_form_detail_view'),
    path('monitoring-forms/create/', monitoring_form_create_view, name='monitoring_form_create_view'),
    path('monitoring-forms/update/<str:pk>/', monitoring_form_update_view, name='monitoring_form_update_view'),
]