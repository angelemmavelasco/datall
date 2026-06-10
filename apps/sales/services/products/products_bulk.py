import pandas as pd
from django.contrib.contenttypes.models import ContentType
from apps.core.models import Product, Reference, ProductClass
from django.db import transaction

class ProductsBulk:

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

            ctype = ContentType.objects.get_for_model(Product)

            references = Reference.objects.filter(
                field_context='column',
                content_type=ctype,
                module__name__iexact='importaciones'
            )
            column_map = {ref.key: ref.reference for ref in references}
            df.rename(columns=column_map, inplace=True)

            fk_map = {}
            for f in Product._meta.get_fields():
                if f.is_relation and hasattr(f, 'attname'):
                    if f.name != f.attname:
                        fk_map[f.name] = f.attname
            
            df.rename(columns=fk_map, inplace=True)

            final_mapped_cols = [fk_map.get(val, val) for val in column_map.values()]
            
            cols_to_keep = [col for col in df.columns if col in final_mapped_cols]
            df = df[cols_to_keep].copy()

            if 'id' not in df.columns:
                return False, "Falta la columna identificadora 'id'."

            # 3. Mapeo de valores de la Clase de Producto
            if 'product_class_id' in df.columns:
                type_references = Reference.objects.filter(
                    field_context__icontains='value_product_class',
                    content_type=ctype,
                    module__name__iexact='importaciones'
                )
                type_map = {str(ref.key).strip(): str(ref.reference).strip() for ref in type_references}
                
                df['product_class_id'] = df['product_class_id'].astype(str).str.strip()
                df['product_class_id'] = df['product_class_id'].map(type_map).fillna('otr')

            df['id'] = df['id'].astype(str).str.strip()
            df.drop_duplicates(subset=['id'], keep='last', inplace=True)
            
            for col in df.columns:
                if col not in ['cost', 'price', 'product_class_id', 'id']:
                    df[col] = df[col].astype(str).str.strip()
                    df[col] = df[col].replace({'nan': None, '': None, 'None': None})

            num_cols = ['cost', 'price']
            for c in num_cols:
                if c in df.columns:
                    df[c] = df[c].astype(str).str.replace(',', '', regex=False)

                    df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)

            df = df.where(pd.notnull(df), None)

            return True, df

        except Exception as e:
            return False, f"Error al leer o limpiar el archivo: {str(e)}"

    def create(self, df):
        try:
            if df is None or df.empty:
                return False, "El DataFrame está vacío."

            model_fields = [f.name for f in Product._meta.get_fields() if not f.is_relation]
            model_fields.extend([f.attname for f in Product._meta.get_fields() if f.is_relation and hasattr(f, 'attname')])
            
            valid_columns = [col for col in df.columns if col in model_fields]

            products_to_create = []

            for _, row in df.iterrows():
                cid = str(row.get('id')).strip()
                if not cid or cid == 'None' or cid.lower() == 'nan':
                    continue

                data = {}
                for col in valid_columns:
                    val = row[col]
                    str_val = str(val).strip().lower()
                    if val is not None and str_val not in ['nan', '', 'none', 'nat']:
                        data[col] = val
                
                data['id'] = cid
                products_to_create.append(Product(**data))

            if not products_to_create:
                return False, "No se encontraron productos válidos para importar."

            update_fields = [col for col in valid_columns if col != 'id']

            with transaction.atomic():
                Product.objects.bulk_create(
                    products_to_create,
                    update_conflicts=True,
                    unique_fields=['id'],
                    update_fields=update_fields,
                    batch_size=500
                )

            return True, f"Importación exitosa. Se procesaron y guardaron {len(products_to_create)} productos."

        except Exception as e:
            print(f"Error detallado: {e}")
            return False, f"Error durante la inserción masiva: {str(e)}"