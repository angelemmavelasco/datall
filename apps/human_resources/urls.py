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
    

    path('position-skills/', position_skill_list_view, name='position_skill_list_view'),
    path('positions-skills/<int:pk>/', position_skill_detail_view, name='position_skill_detail_view'),
]