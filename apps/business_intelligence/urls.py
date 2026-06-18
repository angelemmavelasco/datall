from apps.business_intelligence.views import monthly_breakdown_by_warehouse
from django.urls import path
from .views import *

app_name = 'business_intelligence'

urlpatterns = [
    path('sales_dashboard/', sales_dashboard, name='sales_dashboard'),  
    path('routes_kpis/', routes_kpis, name='routes_kpis'),
    path('warehouses_kpis/', warehouses_kpis, name='warehouses_kpis'),
    path('products_kpis/', products_kpis, name='products_kpis'),



    path('customers_kpis/', customers_kpis, name='customers_kpis'),
    path('customers_kpis/export/', export_customers_kpis_data, name='export_customers_kpis_data'),
    path('customer_kpis/<str:customer_id>/', customer_kpis, name='customer_kpis'),



    path('commercial_risk/', commercial_risk, name='commercial_risk'),
    path('export_risk/', export_commercial_risk_data, name='export_commercial_risk_data'),



    path('target_scope/', target_scope, name='target_scope'),

    path('monthly_breakdown_by_warehouse/', monthly_breakdown_by_warehouse, name='monthly_breakdown_by_warehouse'),
    path('export_monthly_breakdown_data/', export_monthly_breakdown_data, name='export_monthly_breakdown_data'),



    path('sales_breakdown/', sales_breakdown, name='sales_breakdown'),
    path('export_sales_breakdown_data/', export_sales_breakdown_data, name='export_sales_breakdown_data'),



    path('unique_customers/', unique_customers, name='unique_customers'),





    path('sale_targets/', sale_targets, name='sale_targets'),
    path('sale_targets/export/', sale_targets_export, name='sale_targets_export'),
]