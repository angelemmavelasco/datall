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
    path('commissions/<int:cp_id>/', commission_profile_detail, name='commission_profile_detail')
]