from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from apps.core.models import (
    User, MenuSection, SystemModule, Department, TaxSystem,
    PayrollType, Periodicity, Position, Region, Warehouse, Employee,
    ProductCategory, ProductClass, Product, Reference,
    RouteType, SaleChannel, Route, RouteAssignment,
    CommissionProfile, CommissionTier, RouteCommissionSetup,
    RouteCommissionException, CommissionSettlement, Novelty,
    CustomerClassMargin, CommercialBenefit, CustomerAgreement, 
    AgreementClassTarget, AgreementEvaluationPeriod, AgreementPeriodClassResult,
    AppVersion
)
from datetime import date
from django.db.models import Q

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'second_last_name', 'is_staff', 'is_active')
    search_fields = ('username', 'first_name', 'last_name', 'email', 'tax_id', 'unique_personal_id')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'gender')
    fieldsets = UserAdmin.fieldsets + (
        ('Additional Personal Info', {
            'fields': (
                'second_last_name', 'birth_date', 'gender', 'phone',
                'tax_id', 'unique_personal_id', 'notes', 'photo'
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


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'manager')
    search_fields = ('id', 'name', 'manager__user__first_name', 'manager__user__last_name')


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
    list_display = ('id', 'name', 'warehouse', 'sale_channel', 'route_type', 'is_active')
    search_fields = ('id', 'name', 'warehouse__name', 'sale_channel__name', 'route_type__name')
    list_filter = ('warehouse', 'sale_channel', 'route_type', 'is_active')


@admin.register(RouteAssignment)
class RouteAssignmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'route', 'employee', 'start_date', 'end_date')
    search_fields = ('route__id', 'route__name', 'employee__user__first_name', 'employee__user__last_name')
    list_filter = ('route', 'employee', 'start_date', 'end_date')


class CommissionTierInline(admin.TabularInline):
    model = CommissionTier
    extra = 1

class RouteCommissionSetupInline(admin.TabularInline):
    model = RouteCommissionSetup
    extra = 1
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        today = date.today()
        # Only active: end_date is null or greater/equal to today
        return qs.filter(Q(end_date__isnull=True) | Q(end_date__gte=today))

@admin.register(CommissionProfile)
class CommissionProfileAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'is_active')
    search_fields = ('name',)
    list_filter = ('is_active',)
    inlines = [CommissionTierInline, RouteCommissionSetupInline]


@admin.register(RouteCommissionException)
class RouteCommissionExceptionAdmin(admin.ModelAdmin):
    list_display = ('id', 'route', 'start_date', 'end_date', 'scope_tolerance_pct', 'guaranteed_flat_bonus')
    search_fields = ('route__name', 'route__id')
    list_filter = ('start_date', 'end_date')


@admin.register(CommissionSettlement)
class CommissionSettlementAdmin(admin.ModelAdmin):
    list_display = ('id', 'employee', 'route', 'period_start', 'period_end', 'status', 'final_calculated_bonus')
    search_fields = ('employee__user__first_name', 'employee__user__last_name', 'route__name', 'route__id')
    list_filter = ('status', 'period_start', 'period_end')


@admin.register(CommissionTier)
class CommissionTierAdmin(admin.ModelAdmin):
    list_display = ('id', 'commission_profile', 'min_global_scope_pct', 'min_completed_classes', 'bonus_multiplier_pct', 'extra_flat_bonus')
    search_fields = ('commission_profile__name',)
    list_filter = ('commission_profile',)


@admin.register(RouteCommissionSetup)
class RouteCommissionSetupAdmin(admin.ModelAdmin):
    list_display = ('id', 'route', 'profile', 'start_date', 'end_date', 'bonus_type', 'base_bonus_amount')
    search_fields = ('route__name', 'route__id', 'profile__name')
    list_filter = ('start_date', 'end_date', 'bonus_type', 'profile')

@admin.register(Novelty)
class NoveltyAdmin(admin.ModelAdmin):
    list_display = ('title', 'is_active', 'created_at')
    search_fields = ('title', 'content')
    list_filter = ('is_active', 'created_at')
    list_editable = ('is_active',)
    readonly_fields = ('created_at',)
    fieldsets = (
        ('Información Principal', {
            'fields': ('title', 'content', 'image')
        }),
        ('Configuración y Estado', {
            'fields': ('is_active', 'created_at')
        }),
    )

@admin.register(AppVersion)
class AppVersionAdmin(admin.ModelAdmin):
    list_display = ('version_number', 'release_date', 'release_type', 'is_published', 'title')
    search_fields = ('version_number', 'title', 'description')
    list_filter = ('release_type', 'is_published', 'release_date')
    list_editable = ('is_published',)

@admin.register(CustomerClassMargin)
class CustomerClassMarginAdmin(admin.ModelAdmin):
    list_display = ('customer', 'product_class', 'min_margin_percentage')
    search_fields = ('customer__name', 'product_class__name')
    list_filter = ('product_class',)

@admin.register(CommercialBenefit)
class CommercialBenefitAdmin(admin.ModelAdmin):
    list_display = ('name', 'benefit_type', 'is_active', 'cost')
    search_fields = ('name', 'description')
    list_filter = ('benefit_type', 'is_active')

class AgreementClassTargetInline(admin.TabularInline):
    model = AgreementClassTarget
    extra = 1

class AgreementEvaluationPeriodInline(admin.TabularInline):
    model = AgreementEvaluationPeriod
    extra = 0
    show_change_link = True

@admin.register(CustomerAgreement)
class CustomerAgreementAdmin(admin.ModelAdmin):
    list_display = ('doc_id', 'agreement_name', 'customer', 'route', 'agreement_type', 'start_date', 'end_date', 'global_target_amount')
    search_fields = ('doc_id', 'agreement_name', 'customer__name', 'route__name')
    list_filter = ('agreement_type', 'start_date', 'end_date')
    inlines = [AgreementClassTargetInline, AgreementEvaluationPeriodInline]

class AgreementPeriodClassResultInline(admin.TabularInline):
    model = AgreementPeriodClassResult
    extra = 0

@admin.register(AgreementEvaluationPeriod)
class AgreementEvaluationPeriodAdmin(admin.ModelAdmin):
    list_display = ('agreement', 'period_number', 'start_date', 'end_date', 'status', 'expected_global_target', 'achieved_global_sales')
    search_fields = ('agreement__agreement_name', 'agreement__doc_id')
    list_filter = ('status', 'start_date', 'end_date', 'penalty_applied')
    inlines = [AgreementPeriodClassResultInline]

@admin.register(AgreementPeriodClassResult)
class AgreementPeriodClassResultAdmin(admin.ModelAdmin):
    list_display = ('evaluation_period', 'product_class', 'expected_class_target', 'achieved_class_sales')
    search_fields = ('evaluation_period__agreement__agreement_name', 'product_class__name')
    list_filter = ('product_class',)
