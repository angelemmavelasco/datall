from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.safestring import mark_safe
from .models import User, Module, Submodule

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('Información Personal Adicional', {
            'fields': (
                'second_last_name',
                'birth_date',
                'gender',
                'unique_personal_id',
                'photo',
                'phone',
            )
        }),
        ('Dirección', {
            'fields': (
                'street',
                'street_no',
                'apt_suite',
                'city',
                'state',
                'country',
                'zipcode',
            )
        }),
        ('Notas', {
            'fields': ('notes',)
        }),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Información Personal Adicional', {
            'fields': (
                'second_last_name',
                'birth_date',
                'gender',
                'unique_personal_id',
                'photo',
                'phone',
                'street',
                'street_no',
                'apt_suite',
                'city',
                'state',
                'country',
                'zipcode',
                'notes',
            )
        }),
    )

    list_display = ('username', 'email', 'first_name', 'last_name', 'second_last_name', 'phone', 'is_staff')
    search_fields = ('username', 'first_name', 'last_name', 'second_last_name', 'email', 'phone', 'unique_personal_id')


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'order', 'is_active')
    list_editable = ('order', 'is_active')


@admin.register(Submodule)
class SubmoduleAdmin(admin.ModelAdmin):
    list_display = ('name', 'module', 'url_name', 'icon_preview', 'order', 'is_active')
    list_filter = ('module', 'is_active')
    list_editable = ('order', 'is_active')
    search_fields = ('name', 'url_name')

    @admin.display(description='Ícono')
    def icon_preview(self, obj):
        if obj.icon:
            return mark_safe(f'<span style="display:inline-flex; align-items:center; width:20px; height:20px; max-width:24px; max-height:24px;">{obj.icon}</span>')
        return '-'