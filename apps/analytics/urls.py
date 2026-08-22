from django.urls import path
from .views import *

app_name = 'analytics'

urlpatterns = [
    path('sales-dashboard/', sales_dashboard_view, name='sales_dashboard_view'),

    path('customer-kpis/', customer_kpis_view, name='customer_kpis_view'),
    path('customer-kpis/export/', customer_kpis_export_view, name='customer_kpis_export_view'),
    
    path('route-kpis/', route_kpis_view, name='route_kpis_view'),

    path('collections-dashboard/', collections_dashboard_view, name='collections_dashboard_view'),
    
    path('product-kpis/', product_kpis_view, name='product_kpis_view'),
    path('commercial-risk/', commercial_risk_view, name='commercial_risk_view'),
    path('target-achievement/', target_achievement_view, name='target_achievement_view'),
    path('annual-sale-breakdown/', annual_sale_breakdown_view, name='annual_sale_breakdown_view'),
    path('monthly-sale-breakdown/', monthly_sale_breakdown_view, name='monthly_sale_breakdown_view'),
    path('business-unit-sale-breakdown/', business_unit_sale_breakdown_view, name='business_unit_sale_breakdown_view'),
    path('unique-customer-count/', unique_customer_count_view, name='unique_customer_count_view'),
]