from django.urls import path
from .views import *
app_name = 'sales'
urlpatterns = [
    path('warehouses/', warehouse_list_view, name='warehouse_list_view')
]