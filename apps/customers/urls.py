from django.urls import path
from .views import *

app_name = 'customers'

urlpatterns = [
    path('', customer_list_view, name='customer_list_view'),
    path('create/', customer_create_view, name='customer_create_view'),
    path('<str:pk>/', customer_detail_view, name='customer_detail_view'),
    path('<str:pk>/update/', customer_update_view, name='customer_update_view'),
]