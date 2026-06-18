from apps.customers.views import *
from apps.data_admin.urls import app_name
from django.urls import path
app_name = 'customers'

urlpatterns = [

    path('customer_agreements/', customer_agreements, name='customer_agreements'),
    path('customer_agreement_create/', customer_agreement_create, name='customer_agreement_create'  )

]