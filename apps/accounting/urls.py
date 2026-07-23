from django.urls import path
from .views import tax_system_list, tax_system_create_form, tax_system_update_form

app_name = 'accounting'

urlpatterns = [
    path('tax_systems/', tax_system_list, name='tax_system_list'),
    path('create_tax_system/', tax_system_create_form, name='create_tax_system'),
    path('update_tax_system/<str:tax_system_id>/', tax_system_update_form, name='update_tax_system'),
]