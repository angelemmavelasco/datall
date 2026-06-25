from apps.core.models import (
    AccountsReceivable,
    Reference,
    Customer,
    Route
)
from django.db.models import QuerySet, Q
from typing import List
from datetime import datetime, date


class AccountsReceivableCrud:
    def __init__(self, *, allowed_routes=None, allowed_customers=None, allowed_warehouses=None):
        self.allowed_routes = allowed_routes
        self.allowed_customers = allowed_customers
        self.allowed_warehouses = allowed_warehouses
    
    def read(self, **kwargs):
        qs = AccountsReceivable.objects.select_related('customer', 'route', 'customer__route', 'customer__route__warehouse')

        #if date start/end exists, the reports will asume issue date
        date_start = kwargs.get('date_start')
        date_end = kwargs.get('date_end')
        
        issue_date_start = kwargs.get('issue_date_start', date_start)
        issue_date_end = kwargs.get('issue_date_end', date_end)
        due_date_start = kwargs.get('due_date_start')
        due_date_end = kwargs.get('due_date_end')
        q_search = kwargs.get('q')

        if q_search:
            qs = qs.filter(Q(doc_id__icontains=q_search) | Q(description__icontains=q_search))

        # iisue date always includes null values because that kind of discounts alwya affects collections
        if issue_date_start and issue_date_end:
            qs = qs.filter(Q(issue_date__range=(issue_date_start, issue_date_end)) | Q(issue_date__isnull=True))
        elif issue_date_start:
            qs = qs.filter(Q(issue_date__gte=issue_date_start) | Q(issue_date__isnull=True))
        elif issue_date_end:
            qs = qs.filter(Q(issue_date__lte=issue_date_end) | Q(issue_date__isnull=True))

        #duedate filters
        if due_date_start and due_date_end:
            qs = qs.filter(Q(due_date__range=(due_date_start, due_date_end)) | Q(due_date__isnull=True))
        elif due_date_start:
            qs = qs.filter(Q(due_date__gte=due_date_start) | Q(due_date__isnull=True))
        elif due_date_end:
            qs = qs.filter(Q(due_date__lte=due_date_end) | Q(due_date__isnull=True))

        if kwargs.get('customers'):
            customer_list = kwargs['customers']
        else:
            customer_list = self.allowed_customers.values_list('id', flat=True) if self.allowed_customers else []

        qs = qs.filter(
            customer_id__in=customer_list,
            customer__route__in=self.allowed_routes 
        )
        return qs
            



import pandas as pd
from django.db import transaction
from django.contrib.contenttypes.models import ContentType
from apps.core.models import Reference, AccountsReceivable

class AR_bulk:
    def __init__(self, *, allowed_routes=None, allowed_customers=None, allowed_warehouses=None):
        self.allowed_routes = allowed_routes
        self.allowed_customers = allowed_customers
        self.allowed_warehouses = allowed_warehouses
    
    def clean(self, file_obj):
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

            df.columns = df.columns.str.strip()

            ctype = ContentType.objects.get_for_model(AccountsReceivable)

            col_refs = Reference.objects.filter(
                field_context='column',
                module__url_name='data_admin:uploads',
                content_type=ctype
            )
            column_map = {ref.key: ref.reference for ref in col_refs}
            df.rename(columns=column_map, inplace=True)

            fk_map = {}
            for f in AccountsReceivable._meta.get_fields():
                if f.is_relation and hasattr(f, 'attname'):
                    if f.name != f.attname:
                        fk_map[f.name] = f.attname
            df.rename(columns=fk_map, inplace=True)

            issue_date_refs = Reference.objects.filter(
                field_context='value_issue_date',
                module__url_name='data_admin:uploads',
                content_type=ctype
            )
            for ref in issue_date_refs:
                if ref.reference.lower() == 'null':
                    if 'issue_date' in df.columns:
                        df['issue_date'] = df['issue_date'].replace(ref.key, None)
            
            due_date_refs = Reference.objects.filter(
                field_context='value_due_date',
                module__url_name='data_admin:uploads',
                content_type=ctype
            )
            for ref in due_date_refs:
                if ref.reference.lower() == 'null':
                    if 'due_date' in df.columns:
                        df['due_date'] = df['due_date'].replace(ref.key, None)

            if 'issue_date' in df.columns:
                df['issue_date'] = pd.to_datetime(df['issue_date'], errors='coerce').dt.date
            if 'due_date' in df.columns:
                df['due_date'] = pd.to_datetime(df['due_date'], errors='coerce').dt.date

            df = df.where(pd.notnull(df), None)

            return True, df

        except Exception as e:
            return False, f"Error al leer o limpiar el archivo: {str(e)}"

    def create(self, df):
        try:
            if df is None or df.empty:
                return False, "El DataFrame proporcionado está vacío o es inválido."

            if 'customer_id' not in df.columns:
                return False, "El archivo no contiene la columna de Cliente (customer_id)."

            df['customer_id'] = df['customer_id'].replace(['None', 'nan', 'NaN', '', ' '], pd.NA)

            df = df.dropna(subset=['customer_id'])

            if df.empty:
                return False, "Después de limpiar las filas sin cliente, el archivo se quedó vacío."

            created_count = 0

            model_fields = [f.name for f in AccountsReceivable._meta.get_fields() if not f.is_relation]
            model_fields.extend([f.attname for f in AccountsReceivable._meta.get_fields() if f.is_relation and hasattr(f, 'attname')])
            
            valid_columns = [col for col in df.columns if col in model_fields and col != 'id']

            existing_customers = set(Customer.objects.filter(id__in=df['customer_id'].dropna().unique()).values_list('id', flat=True))
            
            if 'route_id' in df.columns:
                existing_routes = set(Route.objects.filter(id__in=df['route_id'].dropna().unique()).values_list('id', flat=True))
            else:
                existing_routes = set()

            records_to_create = []

            for _, row in df.iterrows():

                data = {}
                for col in valid_columns:
                    val = row[col]
                    if val is not None and str(val).lower() != 'nan':
                        data[col] = val

                if 'customer_id' not in data or not data['customer_id']:
                    continue

                cid = str(data['customer_id']).strip()
                if cid not in existing_customers:
                    return False, f"El cliente con ID '{cid}' no existe en la base de datos. Por favor regístrelo antes de importar sus adeudos."

                if 'route_id' in data and data['route_id']:
                    rid = str(data['route_id']).strip()
                    if rid not in existing_routes:
                        return False, f"La ruta con ID '{rid}' no existe en la base de datos."
                    data['route_id'] = rid

                data['customer_id'] = cid
                
                records_to_create.append(AccountsReceivable(**data))
                created_count += 1

            with transaction.atomic():
                AccountsReceivable.objects.all().delete()
                if records_to_create:
                    AccountsReceivable.objects.bulk_create(records_to_create, batch_size=1000)

            msg = f"Importación exitosa. Se reemplazó la cartera con {created_count} nuevos registros."
            return True, msg

        except Exception as e:
            return False, f"Error durante la inserción masiva: {str(e)}"
