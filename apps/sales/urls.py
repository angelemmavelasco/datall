from django.urls import path
from .views import (
    warehouse_list_view,
    warehouse_create_view,
    warehouse_detail_view,
    warehouse_update_view,
    route_list_view,
    route_create_view,
    route_detail_view,
    route_update_view,
    sale_transaction_list_view,
    sale_transaction_detail_view,
    sale_target_list_view,
    sale_target_detail_view,
    sale_target_update_view,
    sale_target_calculator_view,
    export_sale_targets_calculator_data,
    route_options_view
)

app_name = 'sales'

urlpatterns = [
    path('warehouses/', warehouse_list_view, name='warehouse_list_view'),
    path('warehouses/create/', warehouse_create_view, name='warehouse_create_view'),
    path('warehouses/<str:pk>/', warehouse_detail_view, name='warehouse_detail_view'),
    path('warehouses/<str:pk>/update/', warehouse_update_view, name='warehouse_update_view'),
    
    path('routes/', route_list_view, name='route_list_view'),
    path('routes/create/', route_create_view, name='route_create_view'),
    path('routes/options/', route_options_view, name='route_options_view'),
    path('routes/<str:pk>/', route_detail_view, name='route_detail_view'),
    path('routes/<str:pk>/update/', route_update_view, name='route_update_view'),

    path('transactions/', sale_transaction_list_view, name='sale_transaction_list_view'),
    path('transactions/<str:pk>/', sale_transaction_detail_view, name='sale_transaction_detail_view'),

    path('targets/', sale_target_list_view, name='sale_target_list_view'),
    path('targets/<int:pk>/', sale_target_detail_view, name='sale_target_detail_view'),
    path('targets/<int:pk>/update/', sale_target_update_view, name='sale_target_update_view'),

    path('sale-target-calculator/', sale_target_calculator_view, name='sale_target_calculator_view'),
    path('sale-target-calculator/export/', export_sale_targets_calculator_data, name='export_sale_targets_calculator_data'),
]