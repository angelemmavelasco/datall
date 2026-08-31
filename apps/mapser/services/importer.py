from dataclasses import dataclass
from typing import ClassVar, Any
from django.db import transaction

from apps.core.services.uploads import BaseETLHelper, ImportResult, PermissionsError
from apps.core.services.users import UsersService, ServiceError
from apps.mapser.models import DenueInegi


@dataclass
class DenueImportService(UsersService):
    '''
    service dedicated to clean, validate and bulk import denue inegi records
    '''
    denue_model: type = DenueInegi
    ACCESS_CONTEXTS: ClassVar[tuple[str, ...]] = (
        'acceso_total_mapser',
        'mapser',
        'acceso_total_analitica',
        'acceso_total',
    )

    DENUE_COLUMN_MAPPING: ClassVar[dict[str, str]] = {
        # corrupted encoding variants as delivered in raw inegi csv files
        'id': 'id',
        'clee': 'clee',
        'nombre de la unidad econûmica': 'unit_name',
        'razûn social': 'tax_name',
        'cûdigo de la clase de actividad scian': 'scian_code',
        'nombre de clase de la actividad': 'scian_name',
        'descripcion estrato personal ocupado': 'personal_occupied_stratum',
        'tipo de vialidad': 'viality_type',
        'nombre de la vialidad': 'viality_name',
        'tipo de entre vialidad 1': 'cross_viality_type_1',
        'nombre de entre vialidad 1': 'cross_viality_name_1',
        'tipo de entre vialidad 2': 'cross_viality_type_2',
        'nombre de entre vialidad 2': 'cross_viality_name_2',
        'tipo de entre vialidad 3': 'cross_viality_type_3',
        'nombre de entre vialidad 3': 'cross_viality_name_3',
        'n˙mero exterior o kilÛmetro': 'external_number',
        'letra exterior': 'external_letter',
        'edificio': 'building',
        'edificio piso': 'building_floor',
        'n˙mero interior': 'internal_number',
        'letra interior': 'internal_letter',
        'tipo de asentamiento humano': 'settlement_type',
        'nombre de asentamiento humano': 'settlement_name',
        'tipo centro comercial': 'shopping_center_type',
        'corredor industrial, centro comercial o mercado p˙blico': 'industrial_commercial_public_market',
        'n˙mero de local': 'unit_number',
        'cÛdigo postal': 'zip_code',
        'clave entidad': 'state_code',
        'entidad federativa': 'state_name',
        'clave municipio': 'municipality_code',
        'municipio': 'municipality_name',
        'clave localidad': 'locality_code',
        'localidad': 'locality_name',
        '¡rea geoestadÌstica b·sica': 'basic_geostatistical_area',
        '¡rea geoestadistica basica': 'basic_geostatistical_area',
        'manzana': 'block',
        'n˙mero de telÈfono': 'phone_number',
        'correo electrÛnico': 'email',
        'sitio en internet': 'website',
        'tipo de establecimiento': 'establishment_type',
        'latitud': 'latitude',
        'longitud': 'longitude',
        'fecha de incorporaciÛn al denue': 'denue_incorporation_date',

        # standard accented spanish
        'nombre de la unidad económica': 'unit_name',
        'razón social': 'tax_name',
        'código de la clase de actividad scian': 'scian_code',
        'código de la clase de la actividad scian': 'scian_code',
        'descripción estrato personal ocupado': 'personal_occupied_stratum',
        'número exterior o kilómetro': 'external_number',
        'número interior': 'internal_number',
        'corredor industrial, centro comercial o mercado público': 'industrial_commercial_public_market',
        'número de local': 'unit_number',
        'código postal': 'zip_code',
        'área geoestadística básica': 'basic_geostatistical_area',
        'área geoestadística básica (ageb)': 'basic_geostatistical_area',
        'número de teléfono': 'phone_number',
        'correo electrónico': 'email',
        'fecha de incorporación al denue': 'denue_incorporation_date',

        # standard unaccented spanish
        'nombre de la unidad economica': 'unit_name',
        'razon social': 'tax_name',
        'codigo de la clase de actividad scian': 'scian_code',
        'codigo de la clase de la actividad scian': 'scian_code',
        'numero exterior o kilometro': 'external_number',
        'numero interior': 'internal_number',
        'corredor industrial, centro comercial o mercado publico': 'industrial_commercial_public_market',
        'numero de local': 'unit_number',
        'codigo postal': 'zip_code',
        'area geoestadistica basica': 'basic_geostatistical_area',
        'numero de telefono': 'phone_number',
        'correo electronico': 'email',
        'fecha de incorporacion al denue': 'denue_incorporation_date',

        # inegi technical acronyms
        'nom_estab': 'unit_name',
        'raz_social': 'tax_name',
        'codigo_act': 'scian_code',
        'nombre_act': 'scian_name',
        'per_ocu': 'personal_occupied_stratum',
        'tipo_vial': 'viality_type',
        'nom_vial': 'viality_name',
        'tipo_v_e_1': 'cross_viality_type_1',
        'nom_v_e_1': 'cross_viality_name_1',
        'tipo_v_e_2': 'cross_viality_type_2',
        'nom_v_e_2': 'cross_viality_name_2',
        'tipo_v_e_3': 'cross_viality_type_3',
        'nom_v_e_3': 'cross_viality_name_3',
        'numero_ext': 'external_number',
        'letra_ext': 'external_letter',
        'edificio_e': 'building_floor',
        'numero_int': 'internal_number',
        'letra_int': 'internal_letter',
        'tipo_asent': 'settlement_type',
        'nomb_asent': 'settlement_name',
        'tipo_cen_com': 'shopping_center_type',
        'nom_cen_com': 'industrial_commercial_public_market',
        'num_local': 'unit_number',
        'cod_postal': 'zip_code',
        'cve_ent': 'state_code',
        'entidad': 'state_name',
        'cve_mun': 'municipality_code',
        'municipio': 'municipality_name',
        'cve_loc': 'locality_code',
        'localidad': 'locality_name',
        'ageb': 'basic_geostatistical_area',
        'telefono': 'phone_number',
        'correoe': 'email',
        'sitio_internet': 'website',
        'tipo_estab': 'establishment_type',
        'fecha_alta': 'denue_incorporation_date',

        # direct model fields
        'unit_name': 'unit_name',
        'tax_name': 'tax_name',
        'scian_code': 'scian_code',
        'scian_name': 'scian_name',
        'personal_occupied_stratum': 'personal_occupied_stratum',
        'viality_type': 'viality_type',
        'viality_name': 'viality_name',
        'cross_viality_type_1': 'cross_viality_type_1',
        'cross_viality_name_1': 'cross_viality_name_1',
        'cross_viality_type_2': 'cross_viality_type_2',
        'cross_viality_name_2': 'cross_viality_name_2',
        'cross_viality_type_3': 'cross_viality_type_3',
        'cross_viality_name_3': 'cross_viality_name_3',
        'external_number': 'external_number',
        'external_letter': 'external_letter',
        'building': 'building',
        'building_floor': 'building_floor',
        'internal_number': 'internal_number',
        'internal_letter': 'internal_letter',
        'settlement_type': 'settlement_type',
        'settlement_name': 'settlement_name',
        'shopping_center_type': 'shopping_center_type',
        'industrial_commercial_public_market': 'industrial_commercial_public_market',
        'unit_number': 'unit_number',
        'zip_code': 'zip_code',
        'state_code': 'state_code',
        'state_name': 'state_name',
        'municipality_code': 'municipality_code',
        'municipality_name': 'municipality_name',
        'locality_code': 'locality_code',
        'locality_name': 'locality_name',
        'basic_geostatistical_area': 'basic_geostatistical_area',
        'block': 'block',
        'phone_number': 'phone_number',
        'email': 'email',
        'website': 'website',
        'establishment_type': 'establishment_type',
        'latitude': 'latitude',
        'longitude': 'longitude',
        'denue_incorporation_date': 'denue_incorporation_date',
    }

    def _clean_denues(self, file_obj) -> tuple[bool, str | object]:
        '''
        reads, maps columns and cleans denue records from tabular file
        '''
        try:
            import pandas as pd
        except ImportError:
            return False, "La librería 'pandas' no está instalada en el entorno."

        is_valid, df_or_err = BaseETLHelper.read_file_to_dataframe(file_obj)
        if not is_valid:
            return False, df_or_err

        df = df_or_err

        # normalize raw column headers
        normalized_cols = {}
        for col in df.columns:
            clean_header = str(col).strip().lower()
            if clean_header in self.DENUE_COLUMN_MAPPING:
                normalized_cols[col] = self.DENUE_COLUMN_MAPPING[clean_header]

        df.rename(columns=normalized_cols, inplace=True)

        df = BaseETLHelper.apply_reference_column_mappings(
            df,
            self.denue_model,
            submodule_url_name='core:upload_options_list_view',
            context='columna'
        )

        is_req_valid, req_msg = BaseETLHelper.validate_required_columns(
            df,
            {'id': 'Identificador único de la unidad económica'}
        )
        if not is_req_valid:
            return False, req_msg

        # clean numeric coordinates
        for coord_col in ('latitude', 'longitude'):
            if coord_col in df.columns:
                df[coord_col] = pd.to_numeric(
                    df[coord_col].astype(str).str.strip().str.replace(',', '.', regex=False),
                    errors='coerce'
                )

        # clean text fields
        model_fields = [f.name for f in self.denue_model._meta.get_fields() if not f.is_relation]
        for field_name in model_fields:
            if field_name in df.columns and field_name not in ('latitude', 'longitude'):
                df[field_name] = df[field_name].astype(str).str.strip()
                df[field_name] = df[field_name].replace({'nan': '', 'none': '', 'None': '', 'null': '', 'NULL': ''})

        df = df.dropna(subset=['id'])
        df = df[df['id'] != '']
        df = df.drop_duplicates(subset=['id'], keep='last')

        if df.empty:
            return False, 'El archivo no contiene registros válidos del DENUE.'

        df = df.where(pd.notnull(df), None)

        return True, df

    def bulk_create_denues(self, file_obj) -> object:
        '''
        bulk creates and updates denue records using batch processing
        '''
        if not self.has_full_access:
            raise PermissionsError('No tienes permisos suficientes para realizar cargas masivas del DENUE.')

        is_valid, df_or_err = self._clean_denues(file_obj)
        if not is_valid:
            return ImportResult(success=False, message=df_or_err)

        df = df_or_err

        model_fields = [f.name for f in self.denue_model._meta.get_fields() if not f.is_relation]
        valid_columns = [col for col in df.columns if col in model_fields]
        update_fields = [col for col in valid_columns if col != 'id']

        instances = []
        total_processed = 0

        for _, row in df.iterrows():
            record_data = {}
            for col in valid_columns:
                val = row[col]
                if val is not None and str(val).lower() not in ('nan', 'none', 'null'):
                    record_data[col] = val

            unit_id = str(record_data.get('id', '')).strip()
            if not unit_id:
                continue

            instances.append(self.denue_model(**record_data))
            total_processed += 1

        if not instances:
            return ImportResult(success=False, message='No se encontraron unidades económicas válidas para importar.')

        try:
            with transaction.atomic():
                self.denue_model.objects.bulk_create(
                    instances,
                    batch_size=2000,
                    update_conflicts=True,
                    update_fields=update_fields,
                    unique_fields=['id']
                )

            return ImportResult(
                success=True,
                message=f'Importación exitosa. Se procesaron e insertaron {len(instances)} registros del DENUE.',
                total_processed=total_processed,
                created_count=len(instances),
                updated_count=0
            )

        except Exception as e:
            humanized_msg = BaseETLHelper.humanize_database_error(e)
            return ImportResult(
                success=False,
                message=humanized_msg,
                total_processed=total_processed,
                errors=[str(e)]
            )
