from django.urls import path
from apps.customers.views import *


app_name = 'customers'
urlpatterns = [

    path('customer_agreements/', customer_agreements, name='customer_agreements'),

]