from django.urls import path
from .views import *

app_name = 'products'

urlpatterns = [
    path('filter-options/', product_filter_options_view, name='product_filter_options_view'),

    path('products/', product_list_view, name='product_list_view'),
    path('products/create/', product_create_view, name='product_create_view'),
    path('products/<str:pk>/', product_detail_view, name='product_detail_view'),
    path('products/<str:pk>/update/', product_update_view, name='product_update_view'),

    path('stock-transfers/', stock_transfers_view, name='stock_transfers_view'),
    path('stock-transfers/export/', export_stock_transfers_view, name='export_stock_transfers_view'),

    path('purchase-orders/', purchase_order_list_view, name='purchase_order_list_view'),
    path('purchase-orders/create/', purchase_order_create_view, name='purchase_order_create_view'),
    path('purchase-orders/<int:pk>/', purchase_order_detail_view, name='purchase_order_detail_view'),
    path('purchase-orders/<int:pk>/status/', purchase_order_status_update_view, name='purchase_order_status_update_view'),
    path('purchase-orders/<int:pk>/export/', export_purchase_order_view, name='export_purchase_order_view'),
]