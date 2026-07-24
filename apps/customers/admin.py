from django.contrib import admin
from .models import CustomerType, Customer, CustomerAssignment, CustomerClassMargin

admin.site.register(CustomerType)
admin.site.register(Customer)
admin.site.register(CustomerAssignment)
admin.site.register(CustomerClassMargin)
