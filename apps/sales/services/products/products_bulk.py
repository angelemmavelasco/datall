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
                    if val is not None and str_val not in ['nan', '', 'none']:
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


class StocksBulk:

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

            from apps.core.models import Stock, Reference
            ctype = ContentType.objects.get_for_model(Stock)

            references = Reference.objects.filter(
                field_context='column',
                content_type=ctype,
                module__name__iexact='importaciones'
            )

            print(references)
            column_map = {ref.key: ref.reference for ref in references}
            print(column_map)
            df.rename(columns=column_map, inplace=True)
            
            if 'product_id' not in df.columns or 'raw_location' not in df.columns or 'raw_quantity' not in df.columns:
                return False, "Faltan columnas requeridas. Asegúrese de mapear 'product_id', 'raw_location' y 'raw_quantity'."

            warehouse_references = Reference.objects.filter(
                field_context__icontains='value_warehouse',
                content_type=ctype,
                module__name__iexact='importaciones'
            )
            warehouse_map = {str(ref.key).strip(): str(ref.reference).strip() for ref in warehouse_references}
            df['warehouse_id'] = df['raw_location'].astype(str).str.strip().map(warehouse_map)
            type_references = Reference.objects.filter(
                field_context__icontains='value_stock_type',
                content_type=ctype,
                module__name__iexact='importaciones'
            )
            type_map = {str(ref.key).strip().lower(): str(ref.reference).strip().lower() for ref in type_references}
            df['stock_type'] = df['raw_location'].astype(str).str.strip().str.lower().map(type_map)

            df = df.dropna(subset=['warehouse_id', 'stock_type'])
            df = df[df['stock_type'] != 'inactivo']

            df['product_id'] = df['product_id'].astype(str).str.strip()
            df['raw_quantity'] = df['raw_quantity'].astype(str).str.replace(',', '', regex=False)
            df['raw_quantity'] = pd.to_numeric(df['raw_quantity'], errors='coerce').fillna(0)

            df['quantity'] = df.apply(lambda row: row['raw_quantity'] if row['stock_type'] == 'bodega' else 0, axis=1)
            df['in_transit'] = df.apply(lambda row: row['raw_quantity'] if row['stock_type'] == 'transito' else 0, axis=1)
            
            agg_df = df.groupby(['product_id', 'warehouse_id'], as_index=False).agg({
                'quantity': 'sum',
                'in_transit': 'sum'
            })

            return True, agg_df

        except Exception as e:
            return False, f"Error al leer o limpiar el archivo: {str(e)}"

    def create(self, df):
        try:
            if df is None or df.empty:
                return False, "El DataFrame está vacío."

            from apps.core.models import Stock, Product, Warehouse

            product_ids = set(df['product_id'].unique())
            warehouse_ids = set(df['warehouse_id'].unique())

            db_product_ids = set(Product.objects.filter(id__in=product_ids).values_list('id', flat=True))
            db_warehouse_ids = set(Warehouse.objects.filter(id__in=warehouse_ids).values_list('id', flat=True))

            missing_products = product_ids - db_product_ids
            if missing_products:
                sample = list(missing_products)[:10]
                return False, f"Error FK: Faltan productos en el sistema: {sample}"

            missing_warehouses = warehouse_ids - db_warehouse_ids
            if missing_warehouses:
                sample = list(missing_warehouses)[:10]
                return False, f"Error FK: Faltan almacenes en el sistema: {sample}"

            stocks_to_update = []
            stocks_to_create = []

            existing_stocks = Stock.objects.filter(
                product_id__in=product_ids,
                warehouse_id__in=warehouse_ids
            )
            
            stock_dict = {(s.product_id, s.warehouse_id): s for s in existing_stocks}

            for _, row in df.iterrows():
                pid = row['product_id']
                wid = row['warehouse_id']
                qty = row['quantity']
                transit = row['in_transit']

                if (pid, wid) in stock_dict:
                    s = stock_dict[(pid, wid)]
                    s.quantity = qty
                    s.in_transit = transit
                    stocks_to_update.append(s)
                else:
                    stocks_to_create.append(Stock(
                        product_id=pid,
                        warehouse_id=wid,
                        quantity=qty,
                        in_transit=transit
                    ))

            with transaction.atomic():
                if stocks_to_create:
                    Stock.objects.bulk_create(stocks_to_create, batch_size=1000)
                if stocks_to_update:
                    Stock.objects.bulk_update(stocks_to_update, ['quantity', 'in_transit'], batch_size=1000)

            return True, f"Importación exitosa. {len(stocks_to_create)} creados, {len(stocks_to_update)} actualizados."

        except Exception as e:
            print(f"Error detallado en Stock bulk create: {e}")
            return False, f"Error durante la inserción masiva: {str(e)}"