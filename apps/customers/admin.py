from django.contrib import admin
from .models import (
    CustomerType,
    Customer,
    CustomerAssignment,
    CustomerClassMargin,
    AccountsReceivable,
    CustomerNote,
    CommercialBenefit,
    CustomerAgreement,
    AgreementClassTarget,
    AgreementEvaluationPeriod,
)


class CustomerAssignmentInline(admin.TabularInline):
    model = CustomerAssignment
    extra = 1
    fields = ('route', 'start_date', 'end_date', 'notes')
    autocomplete_fields = ['route']
    show_change_link = True


class CustomerClassMarginInline(admin.TabularInline):
    model = CustomerClassMargin
    extra = 1
    fields = ('product_class', 'min_margin_percentage')
    autocomplete_fields = ['product_class']
    show_change_link = True


class CustomerNoteInline(admin.TabularInline):
    model = CustomerNote
    extra = 0
    fields = ('category', 'content', 'is_pinned', 'author', 'current_route', 'created_at')
    readonly_fields = ('created_at',)
    autocomplete_fields = ['author', 'current_route']
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
    inlines = [CustomerAssignmentInline, CustomerClassMarginInline, CustomerNoteInline]


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


@admin.register(CustomerClassMargin)
class CustomerClassMarginAdmin(admin.ModelAdmin):
    list_display = ('customer', 'product_class', 'min_margin_percentage')
    list_filter = ('product_class__product_category', 'product_class')
    search_fields = (
        'customer__id',
        'customer__name',
        'product_class__id',
        'product_class__name',
    )
    autocomplete_fields = ['customer', 'product_class']
    ordering = ('customer', 'product_class')


@admin.register(AccountsReceivable)
class AccountsReceivableAdmin(admin.ModelAdmin):
    list_display = (
        'doc_id',
        'customer',
        'route',
        'issue_date',
        'due_date',
        'current_balance',
        'balance_15',
        'balance_30',
        'balance_60',
        'past_due',
        'total_balance',
    )
    list_filter = (
        'route__business_unit',
        'route',
        'issue_date',
        'due_date',
    )
    search_fields = (
        'doc_id',
        'description',
        'customer__id',
        'customer__name',
        'route__id',
        'route__name',
    )
    autocomplete_fields = ['customer', 'route']
    ordering = ('-due_date', '-issue_date')


@admin.register(CustomerNote)
class CustomerNoteAdmin(admin.ModelAdmin):
    list_display = (
        'customer',
        'category',
        'is_pinned',
        'author',
        'current_route',
        'created_at',
        'short_content',
    )
    list_filter = (
        'category',
        'is_pinned',
        'created_at',
        'current_route__business_unit',
        'current_route',
    )
    search_fields = (
        'customer__id',
        'customer__name',
        'author__username',
        'author__first_name',
        'author__last_name',
        'content',
    )
    autocomplete_fields = ['customer', 'author', 'current_route']
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-is_pinned', '-created_at')

    @admin.display(description='Contenido')
    def short_content(self, obj):
        if not obj.content:
            return ''
        return obj.content[:60] + ('...' if len(obj.content) > 60 else '')


class AgreementClassTargetInline(admin.TabularInline):
    model = AgreementClassTarget
    extra = 0
    fields = ('product_class', 'is_mandatory', 'required_target')
    autocomplete_fields = ['product_class']
    show_change_link = True


class AgreementEvaluationPeriodInline(admin.TabularInline):
    model = AgreementEvaluationPeriod
    extra = 0
    fields = (
        'period_number',
        'start_date',
        'end_date',
        'expected_global_target',
        'achieved_global_sales',
        'amortized_benefit_cost',
        'period_profit',
        'period_margin',
        'status',
        'penalty_applied',
    )
    readonly_fields = ('period_number', 'start_date', 'end_date', 'expected_global_target')
    show_change_link = True


@admin.register(CommercialBenefit)
class CommercialBenefitAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'benefit_type', 'cost', 'is_active')
    list_filter = ('benefit_type', 'is_active')
    search_fields = ('name',)
    ordering = ('name',)


@admin.register(CustomerAgreement)
class CustomerAgreementAdmin(admin.ModelAdmin):
    list_display = (
        'doc_id',
        'customer',
        'route',
        'benefit',
        'agreement_type',
        'start_date',
        'end_date',
        'global_target_amount',
        'target_frequency',
        'penalty_amount',
        'created_at',
    )
    list_filter = (
        'agreement_type',
        'target_frequency',
        'start_date',
        'end_date',
        'benefit',
        'route__business_unit',
    )
    search_fields = (
        'doc_id',
        'customer__id',
        'customer__name',
        'route__id',
        'route__name',
        'benefit__name',
    )
    autocomplete_fields = ['customer', 'route', 'benefit', 'created_by']
    readonly_fields = ('created_at', 'updated_at')
    inlines = [AgreementClassTargetInline, AgreementEvaluationPeriodInline]
    ordering = ('-start_date', '-created_at')

