from django.urls import path
from .views import (
    customer_list_view,
    customer_create_view,
    customer_detail_view,
    customer_update_view,
    customer_filter_options_view,
    ar_list_view,
    ar_detail_view,
)

app_name = 'customers'

urlpatterns = [
    path('filter-options/', customer_filter_options_view, name='customer_filter_options_view'),

    path('customers/', customer_list_view, name='customer_list_view'),
    path('create/', customer_create_view, name='customer_create_view'),
    path('<str:pk>/', customer_detail_view, name='customer_detail_view'),
    path('<str:pk>/update/', customer_update_view, name='customer_update_view'),

    path('accounts-receivable/', ar_list_view, name='ar_list_view'),
    path('accounts-receivable/<str:pk>/', ar_detail_view, name='ar_detail_view'),
]