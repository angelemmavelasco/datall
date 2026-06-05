from django.urls import path
from apps.sales.views import products, product, product_import

app_name='sales'

urlpatterns = [
    path('products/', products, name='products'),
    path('products/<str:product_id>/', product, name='product'),
    path('products/import/', product_import, name='product_import'),

]