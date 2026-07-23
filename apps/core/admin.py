from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from apps.core.models import (
    User, Periodicity, Reference
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
                'tax_id', 'unique_personal_id', 'notes', 'photo'
            )
        }),
        ('Address', {
            'fields': (
                'street', 'street_no', 'apt_suite', 'city', 'state', 'country', 'zipcode'
            )
        }),
    )

@admin.register(Periodicity)
class PeriodicityAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('id', 'name')

@admin.register(Reference)
class ReferenceAdmin(admin.ModelAdmin):
    list_display = ('context', 'key', 'value', 'content_type')
    list_filter = ('content_type', 'context')
    search_fields = ('key', 'value')