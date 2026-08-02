from django.urls import path
from apps.sales.views import *

app_name='sales'

urlpatterns = [
    path('products/', products, name='products'),
    path('products/export/', products_export, name='products_export'),
    path('products/<path:product_id>/', product, name='product'),
    path('stock_transfers/', stock_transfers, name='stock_transfers'),
    path('stock_transfers/export/', export_stock_transfer_data, name='export_stock_transfer_data'),

    path('sale_transactions/', sale_transactions, name='sale_transactions'),
    path('sale_transactions/export/', sale_transactions_export, name='sale_transactions_export'),

    path('sale_targets_calculator/', sale_targets_calculator, name='sale_targets_calculator'),
    path('sale_targets_calculator/export/', export_sale_targets_calculator_data, name='export_sale_targets_calculator_data'),



    #erp
    path('routes/', routes_list_view, name='routes_list_view'),
    path('routes/create/', route_create_view, name='route_create_view'),
    path('routes/<str:route_id>/', route_detail_view, name='route_detail_view'),
    path('routes/<str:route_id>/edit/', route_update_view, name='route_update_view'),
    path('sales/', sale_list_view, name='sale_list_view'),
]