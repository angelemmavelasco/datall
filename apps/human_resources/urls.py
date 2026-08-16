from django.urls import path
from .views import *
app_name = 'human_resources'

urlpatterns = [
    path('business-units/', business_unit_list_view, name='business_unit_list_view'),
    path('business-units/details/<str:pk>/', business_unit_detail_view, name='business_unit_detail_view'),
    path('business-units/create/', business_unit_create_view, name='business_unit_create_view'),
    path('business-units/update/<str:pk>/', business_unit_update_view, name='business_unit_update_view'),

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

    path('monitoring-form-fields/', monitoring_form_field_list_view, name='monitoring_form_field_list_view'),
    path('monitoring-form-fields/details/<str:pk>/', monitoring_form_field_detail_view, name='monitoring_form_field_detail_view'),
    path('monitoring-form-fields/create/', monitoring_form_field_create_view, name='monitoring_form_field_create_view'),
    path('monitoring-form-fields/update/<str:pk>/', monitoring_form_field_update_view, name='monitoring_form_field_update_view'),

    path('monitoring-forms/', monitoring_form_list_view, name='monitoring_form_list_view'),
    path('monitoring-forms/details/<str:pk>/', monitoring_form_detail_view, name='monitoring_form_detail_view'),
    path('monitoring-forms/create/', monitoring_form_create_view, name='monitoring_form_create_view'),
    path('monitoring-forms/update/<str:pk>/', monitoring_form_update_view, name='monitoring_form_update_view'),

    path('monitoring-submissions/', monitoring_form_submission_list_view, name='monitoring_form_submission_list_view'),
    path('monitoring-submissions/details/<int:pk>/', monitoring_form_submission_detail_view, name='monitoring_form_submission_detail_view'),
    path('monitoring-submissions/create/<int:period_id>/', monitoring_form_submission_create_view, name='monitoring_form_submission_create_view'),
    path('monitoring-submissions/update/<int:pk>/', monitoring_form_submission_update_view, name='monitoring_form_submission_update_view'),
    path('monitoring-submissions/delete/<int:pk>/', monitoring_form_submission_delete_view, name='monitoring_form_submission_delete_view'),
]