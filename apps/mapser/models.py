from django.db import models
from decimal import Decimal

class DenueInegi(models.Model):
    '''
    Directorio Estadístico Nacional de Unidades Económicas (DENUE - INEGI).
    https://www.inegi.org.mx/contenidos/productos/prod_serv/contenidos/espanol/bvinegi/productos/nueva_estruc/889463930044.pdf
    '''
    # Unique identifier of the economic unit at inegi database
    id = models.CharField(max_length=100, primary_key=True, help_text='Identificador único de la unidad económica en INEGI')
    clee = models.CharField(max_length=100, blank=True, default='', help_text='Clave Estadística Empresarial (CLEE)')
    unit_name = models.CharField(max_length=255, blank=True, default='', db_index=True, help_text='Nombre de la unidad económica')
    tax_name = models.CharField(max_length=255, blank=True, default='', help_text='Razón social')

    # Actividad económica (SCIAN)
    scian_code = models.CharField(max_length=100, db_index=True, help_text='Código de la clase de la actividad SCIAN')
    scian_name = models.CharField(max_length=255, blank=True, default='', help_text='Nombre de clase de la actividad')
    personal_occupied_stratum = models.CharField(max_length=100, blank=True, default='', help_text='Descripción estrato personal ocupado')

    # Vialidades y domicilio
    viality_type = models.CharField(max_length=100, blank=True, default='', help_text='Tipo de vialidad')
    viality_name = models.CharField(max_length=255, blank=True, default='', help_text='Nombre de la vialidad')
    cross_viality_type_1 = models.CharField(max_length=100, blank=True, default='', help_text='Tipo de entre vialidad 1')
    cross_viality_name_1 = models.CharField(max_length=255, blank=True, default='', help_text='Nombre de entre vialidad 1')
    cross_viality_type_2 = models.CharField(max_length=100, blank=True, default='', help_text='Tipo de entre vialidad 2')
    cross_viality_name_2 = models.CharField(max_length=255, blank=True, default='', help_text='Nombre de entre vialidad 2')
    cross_viality_type_3 = models.CharField(max_length=100, blank=True, default='', help_text='Tipo de entre vialidad 3')
    cross_viality_name_3 = models.CharField(max_length=255, blank=True, default='', help_text='Nombre de entre vialidad 3')
    external_number = models.CharField(max_length=100, blank=True, default='', help_text='Número exterior o kilómetro')
    external_letter = models.CharField(max_length=100, blank=True, default='', help_text='Letra exterior')
    building = models.CharField(max_length=255, blank=True, default='', help_text='Edificio')
    building_floor = models.CharField(max_length=100, blank=True, default='', help_text='Edificio Piso')
    internal_number = models.CharField(max_length=100, blank=True, default='', help_text='Número interior')
    internal_letter = models.CharField(max_length=100, blank=True, default='', help_text='Letra interior')

    # Asentamiento y ubicación
    settlement_type = models.CharField(max_length=100, blank=True, default='', help_text='Tipo de asentamiento humano')
    settlement_name = models.CharField(max_length=255, blank=True, default='', db_index=True, help_text='Nombre de asentamiento humano')
    shopping_center_type = models.CharField(max_length=100, blank=True, default='', help_text='Tipo centro comercial')
    industrial_commercial_public_market = models.CharField(max_length=255, blank=True, default='', help_text='Corredor industrial, centro comercial o mercado público')
    unit_number = models.CharField(max_length=100, blank=True, default='', help_text='Número de local')
    zip_code = models.CharField(max_length=100, blank=True, default='', db_index=True, help_text='Código Postal')

    # Claves geoestadísticas INEGI
    state_code = models.CharField(max_length=100, db_index=True, help_text='Clave entidad')
    state_name = models.CharField(max_length=255, blank=True, default='', db_index=True, help_text='Entidad federativa')
    municipality_code = models.CharField(max_length=100, db_index=True, help_text='Clave municipio')
    municipality_name = models.CharField(max_length=255, blank=True, default='', db_index=True, help_text='Municipio')
    locality_code = models.CharField(max_length=100, blank=True, default='', help_text='Clave localidad')
    locality_name = models.CharField(max_length=255, blank=True, default='', help_text='Localidad')
    basic_geostatistical_area = models.CharField(max_length=100, blank=True, default='', help_text='Área geoestadística básica (AGEB)')
    block = models.CharField(max_length=100, blank=True, default='', help_text='Manzana')

    # Contacto y características
    phone_number = models.CharField(max_length=100, blank=True, default='', help_text='Número de teléfono')
    email = models.CharField(max_length=255, blank=True, default='', help_text='Correo electrónico')
    website = models.CharField(max_length=255, blank=True, default='', help_text='Sitio en Internet')
    establishment_type = models.CharField(max_length=100, blank=True, default='', help_text='Tipo de establecimiento')

    # Coordenadas geográficas y fecha
    latitude = models.DecimalField(max_digits=12, decimal_places=9, null=True, blank=True, db_index=True, help_text='Latitud')
    longitude = models.DecimalField(max_digits=12, decimal_places=9, null=True, blank=True, db_index=True, help_text='Longitud')
    denue_incorporation_date = models.CharField(max_length=100, blank=True, default='', help_text='Fecha de incorporación al DENUE')

    class Meta:
        verbose_name = 'Unidad Económica DENUE'
        verbose_name_plural = 'Unidades Económicas DENUE'
        indexes = [
            models.Index(fields=['latitude', 'longitude']),
            models.Index(fields=['state_code', 'municipality_code']),
            models.Index(fields=['scian_code', 'state_code']),
        ]

    def __str__(self):
        return f'{self.id} - {self.unit_name} ({self.municipality_name})'


    