from django.contrib import admin
from .models import (
    RouteType, SaleChannel, Route, RouteAssignment,
    UserRouteAccess, RouteWarehouseLogistic,
    Sale, SaleLine, SaleLineTax
)

@admin.register(RouteType)
class RouteTypeAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'description')
    search_fields = ('id', 'name')

@admin.register(SaleChannel)
class SaleChannelAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'description')
    search_fields = ('id', 'name')

@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'business_unit','route_type', 'sale_channel')
    list_filter = ('route_type', 'sale_channel', 'business_unit')
    search_fields = ('id', 'name')

@admin.register(RouteAssignment)
class RouteAssignmentAdmin(admin.ModelAdmin):
    list_display = ('route', 'employee', 'date_start', 'date_end')
    list_filter = ('route', 'employee')
    search_fields = ('route__name', 'employee__id', 'employee__user__username')

@admin.register(UserRouteAccess)
class UserRouteAccessAdmin(admin.ModelAdmin):
    list_display = ('user', 'route', 'can_view', 'can_sell')
    list_filter = ('can_view', 'can_sell', 'route')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'route__name')

@admin.register(RouteWarehouseLogistic)
class RouteWarehouseLogisticAdmin(admin.ModelAdmin):
    list_display = ('route', 'warehouse', 'priority')
    list_filter = ('route', 'warehouse', 'priority')
    search_fields = ('route__name', 'warehouse__name')

class SaleLineInline(admin.TabularInline):
    model = SaleLine
    extra = 0

@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ('id', 'sale_status', 'payment_status', 'delivery_status', 'invoice_status', 'customer', 'route', 'seller', 'total', 'sale_date')
    list_filter = ('sale_status', 'payment_status', 'delivery_status', 'invoice_status', 'route', 'sale_date')
    search_fields = ('id', 'customer__name', 'seller__user__first_name', 'seller__user__last_name')
    inlines = [SaleLineInline]

class SaleLineTaxInline(admin.TabularInline):
    model = SaleLineTax
    extra = 0

@admin.register(SaleLine)
class SaleLineAdmin(admin.ModelAdmin):
    list_display = ('id', 'sale', 'variant', 'quantity', 'unit_price', 'subtotal', 'total')
    search_fields = ('sale__id', 'variant__name', 'variant__id')
    inlines = [SaleLineTaxInline]

@admin.register(SaleLineTax)
class SaleLineTaxAdmin(admin.ModelAdmin):
    list_display = ('id', 'sale_line', 'tax_type', 'tax_factor_type', 'rate', 'base', 'amount')
    list_filter = ('tax_type', 'tax_factor_type')
