from django.contrib import admin
from .models import (
    Warehouse,
    RouteType,
    SaleChannel,
    Route,
    RouteAssignment,
    UserRouteAccess,
    SaleTransaction,
    SaleTarget,
)


class RouteAssignmentInline(admin.TabularInline):
    model = RouteAssignment
    extra = 1
    fields = ('employee', 'date_start', 'date_end', 'notes')
    autocomplete_fields = ['employee']
    show_change_link = True


class UserRouteAccessInline(admin.TabularInline):
    model = UserRouteAccess
    extra = 1
    fields = ('user', 'can_view', 'can_edit', 'notes')
    autocomplete_fields = ['user']
    show_change_link = True


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'warehouse_type')
    list_filter = ('warehouse_type',)
    search_fields = ('id', 'name')
    ordering = ('id',)


@admin.register(RouteType)
class RouteTypeAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'description')
    search_fields = ('id', 'name')
    ordering = ('id',)


@admin.register(SaleChannel)
class SaleChannelAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'description')
    search_fields = ('id', 'name')
    ordering = ('id',)


@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'business_unit', 'route_type', 'sale_channel', 'is_active')
    list_filter = ('is_active', 'business_unit', 'route_type', 'sale_channel')
    search_fields = ('id', 'name', 'business_unit__name')
    autocomplete_fields = ['business_unit', 'route_type', 'sale_channel']
    ordering = ('id',)
    inlines = [RouteAssignmentInline, UserRouteAccessInline]


@admin.register(RouteAssignment)
class RouteAssignmentAdmin(admin.ModelAdmin):
    list_display = ('route', 'employee', 'date_start', 'date_end')
    list_filter = ('date_start', 'date_end', 'route__business_unit')
    search_fields = (
        'route__id',
        'route__name',
        'employee__id',
        'employee__user__first_name',
        'employee__user__last_name',
    )
    autocomplete_fields = ['route', 'employee']
    ordering = ('-date_start',)


@admin.register(UserRouteAccess)
class UserRouteAccessAdmin(admin.ModelAdmin):
    list_display = ('user', 'route', 'can_view', 'can_edit')
    list_filter = ('can_view', 'can_edit', 'route__business_unit')
    search_fields = (
        'user__username',
        'user__first_name',
        'user__last_name',
        'route__id',
        'route__name',
    )
    autocomplete_fields = ['user', 'route']
    ordering = ('user', 'route')


@admin.register(SaleTransaction)
class SaleTransactionAdmin(admin.ModelAdmin):
    list_display = (
        'doc_id',
        'sale_date',
        'customer',
        'route',
        'warehouse',
        'product',
        'quantity',
        'gross_amount',
        'net_amount',
    )
    list_filter = ('sale_date', 'warehouse', 'route')
    search_fields = ('doc_id', 'customer__id', 'customer__name', 'product__id', 'product__name')
    autocomplete_fields = ['customer', 'route', 'warehouse', 'product', 'product_class']
    ordering = ('-sale_date', 'doc_id')


@admin.register(SaleTarget)
class SaleTargetAdmin(admin.ModelAdmin):
    list_display = (
        'period',
        'route',
        'warehouse',
        'product_class',
        'target_amount',
        'is_valid_for_comission',
    )
    list_filter = ('period', 'warehouse', 'is_valid_for_comission')
    search_fields = ('route__id', 'route__name', 'product_class__name', 'warehouse__name')
    autocomplete_fields = ['route', 'warehouse', 'product_class']
    ordering = ('-period', 'route')
