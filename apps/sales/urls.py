from django.urls import path
from apps.sales.views import products, product, products_export, sale_transactions, sale_transactions_export

app_name='sales'

urlpatterns = [
    path('products/', products, name='products'),
    path('products/export/', products_export, name='products_export'),
    path('products/<path:product_id>/', product, name='product'),

    path('sale_transactions/', sale_transactions, name='sale_transactions'),
    path('sale_transactions/export/', sale_transactions_export, name='sale_transactions_export'),
    
]