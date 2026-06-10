import pandas as pd
from django.contrib.contenttypes.models import ContentType
from apps.core.models import SaleTransaction, Reference
from django.db import transaction

class SalesTransactionsBulk:

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

            ctype = ContentType.objects.get_for_model(SaleTransaction)

            # 1. Obtener el mapeo de columnas (importaciones)
            references = Reference.objects.filter(
                field_context='column',
                content_type=ctype,
                module__name__iexact='importaciones'
            )
            
            column_map = {ref.key: ref.reference for ref in references}
            df.rename(columns=column_map, inplace=True)

            # 2. RESOLUCIÓN DINÁMICA DE LLAVES FORÁNEAS
            fk_map = {}
            for f in SaleTransaction._meta.get_fields():
                if f.is_relation and hasattr(f, 'attname'):
                    if f.name != f.attname:
                        fk_map[f.name] = f.attname
            
            df.rename(columns=fk_map, inplace=True)

            # Filtrar solo columnas relevantes
            final_mapped_cols = [fk_map.get(val, val) for val in column_map.values()]
            cols_to_keep = [col for col in df.columns if col in final_mapped_cols]
            df = df[cols_to_keep].copy()

            if 'sale_date' not in df.columns:
                return False, "El archivo debe contener una columna identificadora mapeada a 'sale_date'."

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

            if 'warehouse_id' in df.columns:
                warehouse_references = Reference.objects.filter(
                    field_context__icontains='value_warehouse',
                    content_type=ctype,
                    module__name__iexact='importaciones'
                )
                warehouse_map = {str(ref.key).strip(): str(ref.reference).strip() for ref in warehouse_references}
                
                df['warehouse_id'] = df['warehouse_id'].astype(str).str.strip()
                df['warehouse_id'] = df['warehouse_id'].map(warehouse_map).fillna('snc')
                    

            # 4. Limpieza de datos (Strings)
            str_cols = ['customer_id', 'route_id', 'doc_id']
            for col in str_cols:
                if col in df.columns:
                    df[col] = df[col].astype(str).str.strip()
                    df[col] = df[col].replace({'nan': None, '': None, 'none': None})

            print(df['sale_date'].min(), df['sale_date'].max())

            fechas_str = df['sale_date'].astype(str).str.strip().str.replace(' 00:00:00', '', regex=False)
            
            dates_iso = pd.to_datetime(fechas_str, format='%Y-%m-%d', errors='coerce')
            
            dates_mx = pd.to_datetime(fechas_str, format='%d/%m/%Y', errors='coerce')
            
            dates_mx_short = pd.to_datetime(fechas_str, format='%d/%m/%y', errors='coerce')
            
            df['sale_date'] = dates_iso.fillna(dates_mx).fillna(dates_mx_short)

            df['sale_date'] = df['sale_date'].ffill().bfill()

            if df['sale_date'].isnull().all():
                return False, "No se pudo parsear ninguna fecha válida en la columna mapeada a sale_date."
            print(df['sale_date'].min(), df['sale_date'].max())

            if df['sale_date'].isnull().all():
                return False, "No se pudo parsear ninguna fecha válida en la columna mapeada a sale_date."

            num_cols = ['cost', 'net_amount', 'gross_amount', 'profit', 'quantity']
            for c in num_cols:
                if c in df.columns:
                    df[c] = df[c].astype(str).str.replace(',', '', regex=False)
                    df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0).round(6)

            df = df.where(pd.notnull(df), None)
            df['sale_date'] = df['sale_date'].dt.date

            return True, df

        except Exception as e:
            print(e)
            return False, f"Error al leer o limpiar el archivo: {str(e)}"

    def create(self, df):
        try:
            if df is None or df.empty:
                return False, "El DataFrame está vacío."

            min_date = df['sale_date'].min()
            max_date = df['sale_date'].max()

            print(min_date, max_date)



            model_fields = [f.name for f in SaleTransaction._meta.get_fields() if not f.is_relation]
            model_fields.extend([f.attname for f in SaleTransaction._meta.get_fields() if f.is_relation and hasattr(f, 'attname')])
            
            valid_columns = [col for col in df.columns if col in model_fields]

            print(df['sale_date'].min(), df['sale_date'].max())
            

            transactions_to_create = []

            for _, row in df.iterrows():
                data = {}
                for col in valid_columns:
                    val = row[col]
                    str_val = str(val).strip().lower()
                    if val is not None and str_val not in ['nan', '', 'none',]:
                        data[col] = val
                
                if 'sale_date' not in data or 'doc_id' not in data:
                    continue

                transactions_to_create.append(SaleTransaction(**data))

            if not transactions_to_create:
                return False, "No se encontraron transacciones válidas para importar."

            with transaction.atomic():
                # Regla de negocio: Eliminar todos los datos en el rango de fechas (sale_date) 
                # que estamos importando para evitar duplicados y purgar el historico.
                deleted_count, _ = SaleTransaction.objects.filter(sale_date__range=[min_date, max_date]).delete()

                # Crear las nuevas transacciones
                SaleTransaction.objects.bulk_create(
                    transactions_to_create,
                    batch_size=5000
                )

            return True, f"Importación exitosa. Se eliminaron {deleted_count} registros antiguos y se crearon {len(transactions_to_create)} nuevos en el rango {min_date} al {max_date}."

        except Exception as e:
            print(f"Error detallado en SaleTransaction bulk create: {e}")
            return False, f"Error durante la inserción masiva: {str(e)}"
