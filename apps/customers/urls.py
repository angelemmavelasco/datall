from django.urls import path
from apps.customers.views import *


app_name = 'customers'
urlpatterns = [

    path('customer_agreements/', customer_agreements, name='customer_agreements'),
    path('customer_agreements/<int:pk>', customer_agreement_details, name='customer_agreement_details'),
    path('customer_agreements/create/', create_customer_agreement, name='create_customer_agreement'),
    path('customer_agreements/search_customers/', search_customers_htmx, name='search_customers_htmx'),
    path('customer_agreements/preview/', preview_customer_agreement, name='preview_customer_agreement'),
    path('customer_agreements/validate_margin/', validate_customer_agreement, name='validate_customer_agreement'),
    path('customer_agreements/save/', save_customer_agreement, name='save_customer_agreement'),
    path('customer_agreements/evaluate_action/', evaluate_agreements_action, name='evaluate_agreements_action'),
]