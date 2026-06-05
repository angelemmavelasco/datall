from django.urls import path
from apps.human_resources import views

app_name = 'human_resources'

urlpatterns = [
    path('employees/', views.employees, name='employees'),
    path('employees/create/', views.employee_create, name='employee_create'),
    path('employees/<int:user_id>/', views.employee, name='employee'),
]