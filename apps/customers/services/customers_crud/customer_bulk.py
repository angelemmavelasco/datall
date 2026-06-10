import pandas as pd
from datetime import datetime
from django.contrib.contenttypes.models import ContentType
from apps.core.models import Customer, Reference, CustomerType
from django.db import transaction

class CustomersBulk:

    def clean(self, file_obj):
        """
        Lee el archivo crudo, limpia los datos, mapea las columnas utilizando
        el modelo Reference, y asegura el formato correcto para los campos.
        """
        try:
            filename = getattr(file_obj, 'name', '')
            if filename.endswith('.csv'):
                df = pd.read_csv(file_obj)
            elif filename.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(file_obj)
            else:
                return False, "Formato de archivo no soportado. Debe ser CSV o Excel."

            if df.empty:
                return False, "El archivo está vacío."

            # 1. Obtener el ContentType para Customer
            ctype = ContentType.objects.get_for_model(Customer)

            # 2. Traer las referencias de columnas (importaciones)
            references = Reference.objects.filter(
                field_context='column',
                content_type=ctype,
                module__name__iexact='importaciones'
            )
            
            # 3. Crear mapa de renombre: { nombre_crudo: nombre_modelo }
            column_map = {ref.key: ref.reference for ref in references}
            df.rename(columns=column_map, inplace=True)

            # 4. RESOLUCIÓN DINÁMICA DE LLAVES FORÁNEAS (El truco mágico)
            # Inspeccionamos el modelo buscando relaciones (ForeignKeys)
            # f.name suele ser "customer_type", f.attname suele ser "customer_type_id"
            fk_map = {}
            for f in Customer._meta.get_fields():
                if f.is_relation and hasattr(f, 'attname'):
                    if f.name != f.attname:
                        fk_map[f.name] = f.attname
            
            # Renombramos las columnas si el usuario mapeó al nombre base sin el '_id'
            df.rename(columns=fk_map, inplace=True)

            # 5. Verificar si existe al menos la columna ID y name después del mapeo
            if 'id' not in df.columns:
                return False, "El archivo debe contener una columna identificadora mapeada a 'id'."

            # 6. Mapeo de valores para la columna customer_type (ahora garantizada como customer_type_id)
            if 'customer_type_id' in df.columns:
                ct_type = ContentType.objects.get_for_model(CustomerType)
                type_references = Reference.objects.filter(
                    field_context='value',
                    content_type=ct_type,
                    module__name__iexact='importaciones'
                )
                
                type_map = {ref.key: ref.reference for ref in type_references}
                type_map.update({str(ref.key): ref.reference for ref in type_references})
                
                if type_map:
                    df['customer_type_id'] = df['customer_type_id'].map(type_map).fillna('otr')

            # 7. Limpieza de fechas (registration_date)
            if 'registration_date' in df.columns:
                df['registration_date'] = pd.to_datetime(df['registration_date'], errors='coerce')
                df['registration_date'] = df['registration_date'].fillna(pd.Timestamp('2020-01-01')).dt.date
            else:
                df['registration_date'] = datetime.strptime('2020-01-01', '%Y-%m-%d').date()

            # 8. Asegurar que los NaN de pandas sean tratados como None
            df = df.where(pd.notnull(df), None)

            return True, df

        except Exception as e:
            return False, f"Error al leer o limpiar el archivo: {str(e)}"

    def create(self, df):
        """
        Toma el DataFrame limpio y ejecuta un bulk_create o bulk_update.
        Solo actualiza los campos mapeados.
        Si el ID ya existe, lo actualiza, preservando el campo 'opinion_leader'.
        Si no existe, lo crea.
        """
        try:
            if df is None or df.empty:
                return False, "El DataFrame proporcionado está vacío o es inválido."

            if 'id' not in df.columns:
                return False, "El archivo debe contener una columna identificadora mapeada a 'id'."

            created_count = 0
            updated_count = 0

            # Obtener todos los campos válidos del modelo Customer (incluyendo _id)
            model_fields = [f.name for f in Customer._meta.get_fields() if not f.is_relation]
            model_fields.extend([f.attname for f in Customer._meta.get_fields() if f.is_relation and hasattr(f, 'attname')])
            
            # Excluimos 'opinion_leader' explícitamente
            valid_columns = [col for col in df.columns if col in model_fields and col != 'opinion_leader']

            ids_in_df = df['id'].dropna().astype(str).tolist()
            existing_customers = Customer.objects.in_bulk(ids_in_df)

            customers_to_create = []
            customers_to_update = []

            for _, row in df.iterrows():
                cid = str(row.get('id')).strip()
                # Filtrar valores vacíos o los "nan" de pandas
                if not cid or cid == 'None' or cid.lower() == 'nan':
                    continue

                # Construir el diccionario de datos limpiando cualquier float 'nan' residual
                data = {}
                for col in valid_columns:
                    val = row[col]
                    if val is not None and str(val).lower() != 'nan':
                        data[col] = val
                
                data['id'] = cid

                if cid in existing_customers:
                    customer = existing_customers[cid]
                    for key, value in data.items():
                        if key != 'opinion_leader':
                            setattr(customer, key, value)
                    customers_to_update.append(customer)
                    updated_count += 1
                else:
                    customer = Customer(**data)
                    customers_to_create.append(customer)
                    created_count += 1

            with transaction.atomic():
                if customers_to_create:
                    Customer.objects.bulk_create(customers_to_create, batch_size=500)
                
                if customers_to_update:
                    update_fields = [col for col in valid_columns if col != 'id' and col != 'opinion_leader']
                    if update_fields:
                        Customer.objects.bulk_update(customers_to_update, update_fields, batch_size=500)

            msg = f"Importación exitosa. Se crearon {created_count} clientes y se actualizaron {updated_count}."
            return True, msg

        except Exception as e:
            return False, f"Error durante la inserción/actualización masiva: {str(e)}"