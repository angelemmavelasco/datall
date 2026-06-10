import pandas as pd
from django.contrib.contenttypes.models import ContentType
from apps.core.models import SaleTarget, Reference
from django.db import transaction

class SaleTargetsBulk:

    def clean(self, file_obj):
        try:
            filename = getattr(file_obj, 'name', '')
            if filename.endswith('.csv'):
                df = pd.read_csv(file_obj, dtype=str)
            elif filename.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(file_obj, dtype=str)
            else:
                return False, "Formato no soportado. Use .csv o .xlsx"

            if df.empty:
                return False, "El archivo está vacío."

            ctype = ContentType.objects.get_for_model(SaleTarget)

            references = Reference.objects.filter(
                field_context='column',
                content_type=ctype,
                module__name__iexact='importaciones'
            )
            column_map = {ref.key: ref.reference for ref in references}
            df.rename(columns=column_map, inplace=True)

            # 2. Resolución dinámica de llaves foráneas
            fk_map = {}
            for f in SaleTarget._meta.get_fields():
                if f.is_relation and hasattr(f, 'attname'):
                    if f.name != f.attname:
                        fk_map[f.name] = f.attname
            
            df.rename(columns=fk_map, inplace=True)

            final_mapped_cols = [fk_map.get(val, val) for val in column_map.values()]
            cols_to_keep = [col for col in df.columns if col in final_mapped_cols]
            df = df[cols_to_keep].copy()

            if 'period' not in df.columns:
                return False, "El archivo debe contener una columna identificadora mapeada a 'period'."

            # 3. Mapeo de valores con diccionarios de referencia (product_class_id)
            if 'product_class_id' in df.columns:
                type_references = Reference.objects.filter(
                    field_context__icontains='value_product_class',
                    content_type=ctype,
                    module__name__iexact='importaciones'
                )
                type_map = {str(ref.key).strip(): str(ref.reference).strip() for ref in type_references}
                
                df['product_class_id'] = df['product_class_id'].astype(str).str.strip()
                df['product_class_id'] = df['product_class_id'].map(type_map).fillna('otr')

            # Mapeo de valores de warehouse_id
            if 'warehouse_id' in df.columns:
                warehouse_references = Reference.objects.filter(
                    field_context__icontains='value_warehouse',
                    content_type=ctype,
                    module__name__iexact='importaciones'
                )
                warehouse_map = {str(ref.key).strip(): str(ref.reference).strip() for ref in warehouse_references}
                
                df['warehouse_id'] = df['warehouse_id'].astype(str).str.strip()
                df['warehouse_id'] = df['warehouse_id'].map(warehouse_map).fillna('snc')

            # 4. Limpieza de datos
            str_cols = ['route_id', 'warehouse_id', 'product_class_id']
            for col in str_cols:
                if col in df.columns:
                    df[col] = df[col].astype(str).str.strip()
                    df[col] = df[col].replace({'nan': None, '': None, 'none': None})

            # 5. Fechas (period) - Parsear y truncar al primer día del mes
            fechas_str = df['period'].astype(str).str.strip().str.replace(' 00:00:00', '', regex=False)
            
            dates_iso = pd.to_datetime(fechas_str, format='%Y-%m-%d', errors='coerce')
            dates_mx = pd.to_datetime(fechas_str, format='%d/%m/%Y', errors='coerce')
            dates_mx_short = pd.to_datetime(fechas_str, format='%d/%m/%y', errors='coerce')
            
            df['period'] = dates_iso.fillna(dates_mx).fillna(dates_mx_short)
            df['period'] = df['period'].ffill().bfill()
            
            if df['period'].isnull().all():
                return False, "No se pudo parsear ninguna fecha válida en la columna mapeada a period."

            # Truncar al primer día del mes
            df['period'] = df['period'].dt.to_period('M').dt.to_timestamp().dt.date

            # Limpiar booleanos (is_valid_for_comission)
            if 'is_valid_for_comission' in df.columns:
                df['is_valid_for_comission'] = df['is_valid_for_comission'].astype(str).str.strip().str.lower()
                df['is_valid_for_comission'] = df['is_valid_for_comission'].map({
                    'true': True, '1': True, 'si': True, 'sí': True, 'yes': True,
                    'false': False, '0': False, 'no': False
                }).fillna(True)
            else:
                df['is_valid_for_comission'] = True

            # Limpiar valores decimales (target_amount)
            if 'target_amount' in df.columns:
                df['target_amount'] = df['target_amount'].astype(str).str.replace('$', '', regex=False).str.replace(',', '', regex=False)
                df['target_amount'] = pd.to_numeric(df['target_amount'], errors='coerce').fillna(0).round(6)
            else:
                df['target_amount'] = 0.0

            return True, df

        except Exception as e:
            return False, f"Error inesperado al limpiar el archivo: {e}"

    def create(self, df):
        try:
            records = df.to_dict('records')
            instances = []
            
            for row in records:
                target = SaleTarget(
                    period=row.get('period'),
                    route_id=row.get('route_id'),
                    warehouse_id=row.get('warehouse_id'),
                    product_class_id=row.get('product_class_id'),
                    target_amount=row.get('target_amount', 0),
                    is_valid_for_comission=row.get('is_valid_for_comission', True)
                )
                instances.append(target)

            with transaction.atomic():
                # Opcionalmente, se podría eliminar metas del mismo mes y ruta para reemplazar,
                # o usar bulk_create con ignore_conflicts/update_conflicts.
                SaleTarget.objects.bulk_create(
                    instances,
                    update_conflicts=True,
                    unique_fields=['period', 'route_id', 'product_class_id'],
                    update_fields=['warehouse_id', 'target_amount', 'is_valid_for_comission']
                )

            return True, f"{len(instances)} metas procesadas e insertadas correctamente."

        except Exception as e:
            return False, f"Error al procesar la inserción de datos: {e}"
