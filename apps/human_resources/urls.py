from django.urls import path
from apps.human_resources.views import *

app_name = 'human_resources'

urlpatterns = [
    path('employees/', employees, name='employees'),
    path('employees/create/', employee_create, name='employee_create'),
    path('employees/<int:user_id>/', employee, name='employee'),

    path('org_chart/', org_chart, name='org_chart'),
    path('get_org_chart_data/', get_org_chart_data, name='get_org_chart_data'),


    path('commissions/', commissions, name='commissions'),
    path('commissions/create/', commission_profile_create, name='commission_profile_create'),
    path('commissions/<int:cp_id>/', commission_profile_detail, name='commission_profile_detail'),

    path('commissions/exceptions/', commission_exceptions, name='commission_exceptions'),
    path('commissions/exceptions/create/', commission_exception_create, name='commission_exception_create'),
    path('commissions/exceptions/<int:ce_id>/', commission_exception_detail, name='commission_exception_detail'),

    path('commissions_report/', commissions_report, name='commissions_report'),
    path('commissions_report/action/', commissions_action, name='commissions_action'),
    path('commissions_report/<int:pk>/', commission_report_detail, name='commission_report_detail'),

    path('departments/', department_list, name='department_list'),
    path('departments/create/', department_create_form, name='department_create'),
    path('departments/<str:pk>/edit/', department_update_form, name='department_update'),
    path('departments/<str:pk>/', department_details, name='department_details'),
]