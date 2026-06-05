from django.urls import path
from .views import *

app_name = 'business_intelligence'

urlpatterns = [
    path('sales_dashboard/', sales_dashboard, name='sales_dashboard'),  
    path('routes_kpis/', routes_kpis, name='routes_kpis'),
    path('warehouses_kpis/', warehouses_kpis, name='warehouses_kpis'),
    path('products_kpis/', products_kpis, name='products_kpis'),
    path('customers_kpis/', customers_kpis, name='customers_kpis'),
]