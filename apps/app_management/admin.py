from django.contrib import admin
from .models import MenuSection, SystemModule, AppVersion, Novelty

@admin.register(MenuSection)
class MenuSectionAdmin(admin.ModelAdmin):
    list_display = ('name', 'order')
    search_fields = ('name',)

@admin.register(SystemModule)
class SystemModuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'section', 'url_name', 'order', 'is_active')
    list_filter = ('section', 'is_active')
    search_fields = ('name', 'url_name')
    filter_horizontal = ('allowed_groups',)

@admin.register(AppVersion)
class AppVersionAdmin(admin.ModelAdmin):
    list_display = ('version_number', 'release_type', 'release_date', 'is_published')
    list_filter = ('release_type', 'is_published', 'release_date')
    search_fields = ('version_number', 'title')

@admin.register(Novelty)
class NoveltyAdmin(admin.ModelAdmin):
    list_display = ('title', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('title', 'content')
