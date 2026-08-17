from django.urls import path
from .views import (
    product_list_view,
    product_detail_view,
    product_create_view,
    product_update_view,
    product_filter_options_view,
)

app_name = 'products'

urlpatterns = [
    path('filter-options/', product_filter_options_view, name='product_filter_options_view'),

    path('products/', product_list_view, name='product_list_view'),
    path('products/create/', product_create_view, name='product_create_view'),
    path('products/<str:pk>/', product_detail_view, name='product_detail_view'),
    path('products/<str:pk>/update/', product_update_view, name='product_update_view'),
]