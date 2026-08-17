from django.contrib import admin
from .models import (
    CustomerType,
    Customer,
    CustomerAssignment,
)


class CustomerAssignmentInline(admin.TabularInline):
    model = CustomerAssignment
    extra = 1
    fields = ('route', 'start_date', 'end_date', 'notes')
    autocomplete_fields = ['route']
    show_change_link = True


@admin.register(CustomerType)
class CustomerTypeAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'description')
    search_fields = ('id', 'name')
    ordering = ('id',)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'name',
        'customer_type',
        'registration_date',
        'credit_limit',
        'credit_days',
        'opinion_leader',
    )
    list_filter = ('customer_type', 'opinion_leader', 'registration_date')
    search_fields = ('id', 'name')
    autocomplete_fields = ['customer_type']
    ordering = ('id',)
    inlines = [CustomerAssignmentInline]


@admin.register(CustomerAssignment)
class CustomerAssignmentAdmin(admin.ModelAdmin):
    list_display = ('customer', 'route', 'start_date', 'end_date')
    list_filter = ('start_date', 'end_date', 'route__business_unit', 'route')
    search_fields = (
        'customer__id',
        'customer__name',
        'route__id',
        'route__name',
    )
    autocomplete_fields = ['customer', 'route']
    ordering = ('-start_date',)
