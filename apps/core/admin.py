import logging
import traceback
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.utils.safestring import mark_safe
from .models import User, Module, Submodule, Reference, AppVersion, SupportCategory, SupportArticle, ActivityLog

logger = logging.getLogger(__name__)

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


class ReferenceInline(admin.TabularInline):
    model = Reference
    extra = 1
    fields = ('content_type', 'context', 'key', 'value')


@admin.register(Submodule)
class SubmoduleAdmin(admin.ModelAdmin):
    list_display = ('name', 'module', 'url_name', 'icon_preview', 'order', 'is_active')
    list_filter = ('module', 'is_active')
    list_editable = ('order', 'is_active')
    search_fields = ('name', 'url_name')
    inlines = [ReferenceInline]

    @admin.display(description='Ícono')
    def icon_preview(self, obj):
        if obj.icon:
            return mark_safe(f'<span style="display:inline-flex; align-items:center; width:20px; height:20px; max-width:24px; max-height:24px;">{obj.icon}</span>')
        return '-'


@admin.register(Reference)
class ReferenceAdmin(admin.ModelAdmin):
    list_display = ('submodule', 'content_type', 'context', 'key', 'value')
    list_filter = ('submodule', 'content_type', 'context')
    search_fields = ('context', 'key', 'value', 'submodule__name')
    list_select_related = ('submodule', 'content_type')


@admin.register(AppVersion)
class AppVersionAdmin(admin.ModelAdmin):
    list_display = ('version_number', 'title', 'release_type', 'release_date', 'is_published')
    list_filter = ('release_type', 'is_published', 'release_date')
    search_fields = ('version_number', 'title', 'description')
    list_editable = ('is_published',)

    def save_model(self, request, obj, form, change):
        try:
            super().save_model(request, obj, form, change)
        except Exception as e:
            tb = traceback.format_exc()
            logger.critical("Error in AppVersion save_model:\n%s", tb)
            print(f"\n[DATALL APP_VERSION SAVE ERROR]\n{tb}\n", flush=True)
            messages.error(request, f"Error en save_model: {type(e).__name__} - {str(e)}")
            raise

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        try:
            return super().changeform_view(request, object_id, form_url, extra_context)
        except Exception as e:
            tb = traceback.format_exc()
            logger.critical("Error in AppVersion changeform_view:\n%s", tb)
            print(f"\n[DATALL APP_VERSION CHANGEFORM ERROR]\n{tb}\n", flush=True)
            messages.error(request, f"Error al procesar versión: {type(e).__name__}: {str(e)}")
            if request.method == 'POST':
                try:
                    request.method = 'GET'
                    return super().changeform_view(request, object_id, form_url, extra_context)
                except Exception:
                    pass
            raise

@admin.register(SupportCategory)
class SupportCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'order', 'icon', 'is_active', 'articles_count')
    list_display_links = ('name',)
    list_editable = ('order', 'is_active')
    search_fields = ('name', 'description')

    def articles_count(self, obj):
        return obj.articles.count()
    articles_count.short_description = "Artículos"

@admin.register(SupportArticle)
class SupportArticleAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'order', 'is_published', 'is_highlighted', 'updated_at')
    list_display_links = ('title',)
    list_filter = ('category', 'is_published', 'is_highlighted')
    list_editable = ('order', 'is_published', 'is_highlighted')
    search_fields = ('title', 'content', 'category__name')
    list_select_related = ('category',)


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'user', 'action', 'view_name', 'path', 'http_method', 'status_code', 'result', 'duration_ms', 'ip_address')
    list_filter = ('action', 'result', 'http_method', 'status_code', 'created_at')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'view_name', 'path', 'ip_address')
    readonly_fields = ('user', 'path', 'view_name', 'http_method', 'submodule', 'action', 'result', 'status_code', 'content_type', 'object_id', 'params', 'changes', 'ip_address', 'user_agent', 'duration_ms', 'created_at')
    ordering = ('-created_at',)

    def has_add_permission(self, request):
        return False