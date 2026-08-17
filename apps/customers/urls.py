from django.urls import path
from .views import customer_list_view, customer_detail_view

app_name = 'customers'

urlpatterns = [
    path('', customer_list_view, name='customer_list_view'),
    path('<str:pk>/', customer_detail_view, name='customer_detail_view'),
]