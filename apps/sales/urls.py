from django.urls import path
from .views import *
app_name = 'sales'
urlpatterns = [
    path('warehouses/', warehouse_list_view, name='warehouse_list_view'),
    path('warehouses/create/', warehouse_create_view, name='warehouse_create_view'),
    path('warehouses/<str:pk>/', warehouse_detail_view, name='warehouse_detail_view'),
    path('warehouses/<str:pk>/update/', warehouse_update_view, name='warehouse_update_view'),
    
    path('routes/', route_list_view, name='route_list_view'),
    path('routes/create/', route_create_view, name='route_create_view'),
    path('routes/<str:pk>/', route_detail_view, name='route_detail_view'),
    path('routes/<str:pk>/update/', route_update_view, name='route_update_view'),
]