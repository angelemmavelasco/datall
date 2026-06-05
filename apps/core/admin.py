from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from apps.core.models import (
    User, MenuSection, SystemModule, Department, TaxSystem,
    PayrollType, Periodicity, Position, Warehouse, Employee,
    ProductCategory, ProductClass, Product, Reference,
    RouteType, SaleChannel, Route, RouteAssignment
)

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'second_last_name', 'is_staff', 'is_active')
    search_fields = ('username', 'first_name', 'last_name', 'email', 'tax_id', 'unique_personal_id')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'gender')
    fieldsets = UserAdmin.fieldsets + (
        ('Additional Personal Info', {
            'fields': (
                'second_last_name', 'birth_date', 'gender', 'phone',
                'tax_id', 'unique_personal_id', 'notes'
            )
        }),
        ('Address', {
            'fields': (
                'street', 'street_no', 'apt_suite', 'city', 'state', 'country', 'zipcode'
            )
        }),
    )

@admin.register(MenuSection)
class MenuSectionAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'order')
    search_fields = ('name',)
    ordering = ('order',)

@admin.register(SystemModule)
class SystemModuleAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'section', 'url_name', 'order')
    search_fields = ('name', 'url_name', 'section__name')
    list_filter = ('section',)
    filter_horizontal = ('allowed_groups',)

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'description')
    search_fields = ('id', 'name')

@admin.register(TaxSystem)
class TaxSystemAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'description')
    search_fields = ('id', 'name')

@admin.register(PayrollType)
class PayrollTypeAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'description')
    search_fields = ('id', 'name')

@admin.register(Periodicity)
class PeriodicityAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('id', 'name')

@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'department', 'description')
    search_fields = ('id', 'name', 'department__name')
    list_filter = ('department',)

@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'manager')
    search_fields = ('id', 'name', 'manager__user__first_name', 'manager__user__last_name')

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'user', 'position', 'warehouse', 'manager',
        'hire_date', 'termination_date', 'payroll_type',
        'payroll_amount', 'payroll_periodicity', 'tax_system'
    )
    search_fields = (
        'user__username', 'user__first_name', 'user__last_name',
        'position__name', 'warehouse__name'
    )
    list_filter = (
        'position', 'warehouse', 'payroll_type',
        'payroll_periodicity', 'tax_system'
    )

@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'description')
    search_fields = ('id', 'name')

@admin.register(ProductClass)
class ProductClassAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'product_category')
    search_fields = ('id', 'name', 'product_category__name')
    list_filter = ('product_category',)

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('id', 'barcode', 'name', 'product_class', 'cost', 'price', 'unit_of_measure')
    search_fields = ('id', 'barcode', 'name', 'product_class__name')
    list_filter = ('product_class', 'unit_of_measure')

@admin.register(Reference)
class ReferenceAdmin(admin.ModelAdmin):
    list_display = ('id', 'module', 'field_context', 'key', 'reference')
    search_fields = ('field_context', 'key', 'reference', 'module__name')
    list_filter = ('module', 'field_context')


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
    list_display = ('id', 'name', 'warehouse', 'sale_channel', 'route_type', 'commission_type', 'commission')
    search_fields = ('id', 'name', 'warehouse__name', 'sale_channel__name', 'route_type__name')
    list_filter = ('warehouse', 'sale_channel', 'route_type', 'commission_type')


@admin.register(RouteAssignment)
class RouteAssignmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'route', 'employee', 'start_date', 'end_date')
    search_fields = ('route__id', 'route__name', 'employee__user__first_name', 'employee__user__last_name')
    list_filter = ('route', 'employee', 'start_date', 'end_date')


