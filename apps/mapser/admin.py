from django.contrib import admin
from .models import DenueInegi, CustomerGeoProfile


@admin.register(DenueInegi)
class DenueInegiAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'unit_name',
        'scian_code',
        'scian_name',
        'personal_occupied_stratum',
        'municipality_name',
        'state_name',
        'zip_code',
        'latitude',
        'longitude',
    )
    list_filter = (
        'state_name',
        'personal_occupied_stratum',
        'establishment_type',
    )
    search_fields = (
        'id',
        'clee',
        'unit_name',
        'tax_name',
        'scian_code',
        'scian_name',
        'zip_code',
        'municipality_name',
        'settlement_name',
    )
    ordering = ('id',)
    fieldsets = (
        ('Identificación', {
            'fields': ('id', 'clee', 'unit_name', 'tax_name', 'establishment_type', 'denue_incorporation_date')
        }),
        ('Actividad Económica (SCIAN)', {
            'fields': ('scian_code', 'scian_name', 'personal_occupied_stratum')
        }),
        ('Ubicación y Domicilio', {
            'fields': (
                'viality_type', 'viality_name', 'external_number', 'external_letter',
                'internal_number', 'internal_letter', 'building', 'building_floor',
                'settlement_type', 'settlement_name', 'zip_code',
                'cross_viality_type_1', 'cross_viality_name_1',
                'cross_viality_type_2', 'cross_viality_name_2',
                'cross_viality_type_3', 'cross_viality_name_3',
                'shopping_center_type', 'industrial_commercial_public_market', 'unit_number'
            )
        }),
        ('Datos Geoestadísticos INEGI', {
            'fields': (
                'state_code', 'state_name', 'municipality_code', 'municipality_name',
                'locality_code', 'locality_name', 'basic_geostatistical_area', 'block'
            )
        }),
        ('Coordenadas Geográficas', {
            'fields': ('latitude', 'longitude')
        }),
        ('Contacto', {
            'fields': ('phone_number', 'email', 'website')
        }),
    )


@admin.register(CustomerGeoProfile)
class CustomerGeoProfileAdmin(admin.ModelAdmin):
    list_display = (
        'customer',
        'zip_code',
        'municipality',
        'state',
        'latitude',
        'longitude',
        'geocoding_source',
        'is_verified',
        'matched_denue',
    )
    list_filter = (
        'geocoding_source',
        'is_verified',
        'state',
    )
    search_fields = (
        'customer__id',
        'customer__name',
        'zip_code',
        'municipality',
        'street_address',
        'neighborhood',
    )
    autocomplete_fields = ['customer', 'matched_denue']
    ordering = ('customer__id',)
    fieldsets = (
        ('Cliente', {
            'fields': ('customer', 'matched_denue')
        }),
        ('Dirección', {
            'fields': ('street_address', 'neighborhood', 'municipality', 'state', 'zip_code')
        }),
        ('Georreferenciación', {
            'fields': ('latitude', 'longitude', 'geocoding_source', 'is_verified', 'last_geocoded_at')
        }),
    )
