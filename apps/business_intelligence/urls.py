from django.urls import path
from .views import *

app_name = 'business_intelligence'

urlpatterns = [
    path('sales_dashboard/', sales_dashboard, name='sales_dashboard'),  
    path('routes_kpis/', routes_kpis, name='routes_kpis'),
    path('warehouses_kpis/', warehouses_kpis, name='warehouses_kpis'),
    path('products_kpis/', products_kpis, name='products_kpis'),
    path('customers_kpis/', customers_kpis, name='customers_kpis'),



    path('commercial_risk/', commercial_risk, name='commercial_risk'),




    path('sales_breakdown/', sales_breakdown, name='sales_breakdown'),
    path('sale_targets/', sale_targets, name='sale_targets'),
    path('sale_targets/export/', sale_targets_export, name='sale_targets_export'),
]