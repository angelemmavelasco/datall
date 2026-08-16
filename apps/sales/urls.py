from django.urls import path
from .views import *
app_name = 'sales'
urlpatterns = [
    path('warehouses/', warehouse_list_view, name='warehouse_list_view'),
    path('warehouses/create/', warehouse_create_view, name='warehouse_create_view'),
    path('warehouses/<str:pk>/', warehouse_detail_view, name='warehouse_detail_view'),
    path('warehouses/<str:pk>/update/', warehouse_update_view, name='warehouse_update_view'),
]