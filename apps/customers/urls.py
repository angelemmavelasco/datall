from django.urls import path
from apps.customers.views import *


app_name = 'customers'
urlpatterns = [

    path('customer_agreements/', customer_agreements, name='customer_agreements'),
    path('customer_agreements/create/', create_customer_agreement, name='create_customer_agreement'),
    path('customer_agreements/validate_margin/', validate_customer_agreement, name='validate_customer_agreement'),
    path('customer_agreements/save/', save_customer_agreement, name='save_customer_agreement'),
    path('customer_agreements/evaluate_action/', evaluate_agreements_action, name='evaluate_agreements_action'),
    path('customer_agreements/add_class_target_row/', add_class_target_row, name='add_class_target_row'),

]