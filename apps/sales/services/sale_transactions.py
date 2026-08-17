from dataclasses import dataclass
from decimal import Decimal
from typing import ClassVar

from django.db.models import (
    Q,
    QuerySet,
    Count,
    Sum,
    Avg,
)
from django.utils import timezone

from apps.core.services.users import UsersService
from apps.customers.models import Customer, CustomerAssignment
from apps.products.models import ProductClass
from apps.sales.models import SaleTransaction, Route, Warehouse
from apps.sales.services.routes import RoutesService


class ServiceError(Exception):
    pass


class PermissionsError(ServiceError):
    pass


class SaleTransactionNotFound(ServiceError):
    pass


@dataclass
class SaleTransactionsService(UsersService):
    sale_transaction_model: type = SaleTransaction
    route_model: type = Route
    warehouse_model: type = Warehouse
    customer_model: type = Customer
    customer_assignment_model: type = CustomerAssignment
    product_class_model: type = ProductClass

    ACCESS_CONTEXTS: ClassVar[tuple[str, ...]] = (
        'acceso_total_ventas',
        'ventas',
        'acceso_total_rutas',
    )

    def _get_allowed_routes_qs(self) -> QuerySet:
        """
        helper to get allowed routes for the current user using RoutesService
        """
        routes_service = RoutesService(user=self.user)
        return routes_service.get_allowed_routes(can_view=True, can_edit=False)

    def read_transactions_by_allowed_routes(self) -> QuerySet:
        """
        Returns transactions executed/emitted by routes to which the user has access.
        Independent of whether the customer currently belongs to those routes or not.
        """
        base_qs = self.sale_transaction_model.objects.select_related(
            'customer',
            'customer__customer_type',
            'route',
            'route__business_unit',
            'route__sale_channel',
            'warehouse',
            'product',
            'product_class',
            'product_class__product_category',
        )

        if self.has_full_access:
            return base_qs.order_by('-sale_date', '-id')

        allowed_routes = self._get_allowed_routes_qs()
        return base_qs.filter(route__in=allowed_routes).order_by('-sale_date', '-id')

    def read_transactions_by_allowed_customers(self) -> QuerySet:
        """
        Returns transactions corresponding to customers currently assigned to routes
        to which the user has access, regardless of which route historically emitted the transaction.
        """
        base_qs = self.sale_transaction_model.objects.select_related(
            'customer',
            'customer__customer_type',
            'route',
            'route__business_unit',
            'route__sale_channel',
            'warehouse',
            'product',
            'product_class',
            'product_class__product_category',
        )

        if self.has_full_access:
            return base_qs.order_by('-sale_date', '-id')

        today = timezone.localdate()
        allowed_routes = self._get_allowed_routes_qs()

        # Customers currently assigned to allowed routes
        allowed_customers_subquery = self.customer_assignment_model.objects.filter(
            route__in=allowed_routes
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=today)
        ).values('customer_id')

        return base_qs.filter(customer_id__in=allowed_customers_subquery).order_by('-sale_date', '-id')

    def read_transactions(self) -> QuerySet:
        """
        Default transaction listing perspective for general views: based on allowed routes.
        """
        return self.read_transactions_by_allowed_routes()

    def read_transaction(self, *, pk: str | int) -> SaleTransaction:
        """
        Returns a single transaction by ID, validated against allowed routes.
        """
        transaction_obj = self.read_transactions_by_allowed_routes().filter(pk=pk).first()
        if transaction_obj:
            return transaction_obj

        if self.sale_transaction_model.objects.filter(pk=pk).exists():
            raise PermissionsError(f'No tienes permiso para acceder a la transacción con ID "{pk}".')

        raise SaleTransactionNotFound(f'No se encontró ninguna transacción con el ID "{pk}".')

    def _clean_transactions(self, file_obj) -> tuple[bool, str | object]:
        try:
            import pandas as pd
        except ImportError:
            return False, "La librería 'pandas' no está instalada en el entorno."

        from apps.core.services.uploads import BaseETLHelper
        from django.contrib.contenttypes.models import ContentType
        from apps.core.models import Reference

        is_valid, df_or_err = BaseETLHelper.read_file_to_dataframe(file_obj)
        if not is_valid:
            return False, df_or_err

        df = df_or_err
        df = BaseETLHelper.apply_reference_column_mappings(
            df,
            self.sale_transaction_model,
            submodule_name='importacion',
            context='columna'
        )
        df = BaseETLHelper.resolve_foreign_key_columns(df, self.sale_transaction_model)

        if 'sale_date' not in df.columns:
            return False, "El archivo debe contener una columna identificadora mapeada a 'sale_date'."

        if 'product_class_id' in df.columns:
            valid_classes = set(self.product_class_model.objects.values_list('id', flat=True))
            default_class = 'otr' if 'otr' in valid_classes else (next(iter(valid_classes)) if valid_classes else None)

            pc_ctype = ContentType.objects.get_for_model(self.product_class_model)
            st_ctype = ContentType.objects.get_for_model(self.sale_transaction_model)
            type_references = Reference.objects.filter(
                Q(content_type=pc_ctype, context__icontains='valor') |
                Q(content_type=st_ctype, context__icontains='clase') |
                Q(content_type=st_ctype, context__icontains='product_class')
            )
            type_map = {}
            for ref in type_references:
                k = str(ref.key).strip().lower()
                v = str(ref.value).strip() if getattr(ref, 'value', '') else str(getattr(ref, 'reference', '')).strip()
                if k and v:
                    type_map[k] = v
            
            raw_series = df['product_class_id'].astype(str).str.strip().str.lower()
            if type_map:
                mapped_series = raw_series.map(type_map).fillna(raw_series)
            else:
                mapped_series = raw_series

            df['product_class_id'] = mapped_series.apply(
                lambda x: x if x in valid_classes else default_class
            )
        else:
            valid_classes = set(self.product_class_model.objects.values_list('id', flat=True))
            df['product_class_id'] = 'otr' if 'otr' in valid_classes else (next(iter(valid_classes)) if valid_classes else None)

        if 'warehouse_id' in df.columns:
            valid_warehouses = set(self.warehouse_model.objects.values_list('id', flat=True))
            default_warehouse = 'snc' if 'snc' in valid_warehouses else None

            wh_ctype = ContentType.objects.get_for_model(self.warehouse_model)
            st_ctype = ContentType.objects.get_for_model(self.sale_transaction_model)
            warehouse_references = Reference.objects.filter(
                Q(content_type=wh_ctype, context__icontains='valor') |
                Q(content_type=st_ctype, context__icontains='almacen') |
                Q(content_type=st_ctype, context__icontains='cedis') |
                Q(content_type=st_ctype, context__icontains='warehouse')
            )
            warehouse_map = {}
            for ref in warehouse_references:
                k = str(ref.key).strip().lower()
                v = str(ref.value).strip() if getattr(ref, 'value', '') else str(getattr(ref, 'reference', '')).strip()
                if k and v:
                    warehouse_map[k] = v
            
            raw_w_series = df['warehouse_id'].astype(str).str.strip().str.lower()
            if warehouse_map:
                mapped_w_series = raw_w_series.map(warehouse_map).fillna(raw_w_series)
            else:
                mapped_w_series = raw_w_series

            df['warehouse_id'] = mapped_w_series.apply(
                lambda x: x if x in valid_warehouses else default_warehouse
            )

        str_cols = ['customer_id', 'route_id', 'doc_id', 'product_id']
        for col in str_cols:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
                df[col] = df[col].replace({'nan': None, '': None, 'None': None, 'none': None})

        fechas_str = df['sale_date'].astype(str).str.strip().str.replace(' 00:00:00', '', regex=False)
        
        dates_iso = pd.to_datetime(fechas_str, format='%Y-%m-%d', errors='coerce')
        dates_mx = pd.to_datetime(fechas_str, format='%d/%m/%Y', errors='coerce')
        dates_mx_short = pd.to_datetime(fechas_str, format='%d/%m/%y', errors='coerce')
        
        df['sale_date'] = dates_iso.fillna(dates_mx).fillna(dates_mx_short)
        df['sale_date'] = df['sale_date'].ffill().bfill()

        if df['sale_date'].isnull().all():
            return False, "No se pudo parsear ninguna fecha válida en la columna mapeada a sale_date."

        num_cols = ['cost', 'net_amount', 'gross_amount', 'profit', 'quantity']
        for c in num_cols:
            if c in df.columns:
                df[c] = pd.to_numeric(
                    df[c].astype(str).str.replace(r'[$, ]', '', regex=True),
                    errors='coerce'
                ).fillna(0).round(6)

        df = df.where(pd.notnull(df), None)
        df['sale_date'] = df['sale_date'].dt.date

        return True, df

    def bulk_create_transactions(self, file_obj) -> object:
        from apps.core.services.uploads import ImportResult, PermissionsError
        from django.db import transaction

        if not self.has_full_access:
            raise PermissionsError('No tienes permisos suficientes para realizar cargas masivas de transacciones de venta.')

        is_valid, df_or_err = self._clean_transactions(file_obj)
        if not is_valid:
            return ImportResult(success=False, message=df_or_err)

        df = df_or_err

        if df is None or df.empty:
            return ImportResult(success=False, message="El DataFrame está vacío.")

        min_date = df['sale_date'].min()
        max_date = df['sale_date'].max()

        model_fields = [f.name for f in self.sale_transaction_model._meta.get_fields() if not f.is_relation]
        model_fields.extend([f.attname for f in self.sale_transaction_model._meta.get_fields() if f.is_relation and hasattr(f, 'attname')])
        
        valid_columns = [col for col in df.columns if col in model_fields]

        fk_fields = [f for f in self.sale_transaction_model._meta.get_fields() if f.is_relation and hasattr(f, 'attname')]
        for fk in fk_fields:
            column_name = fk.attname         
            related_model = fk.related_model 

            if column_name in df.columns:
                df_ids = set(df[column_name].dropna().unique())
                
                if not df_ids:
                    continue

                db_ids = set(related_model.objects.filter(pk__in=df_ids).values_list('pk', flat=True))

                missing_ids = df_ids - db_ids

                if missing_ids:
                    missing_list = list(missing_ids)
                    sample_missing = missing_list[:10] 
                    return ImportResult(success=False, message=f"Error de Foreign Key: En la columna '{column_name}', los siguientes IDs no existen en el sistema: {sample_missing}{'...' if len(missing_list) > 10 else ''}. Registra estos datos primero e intenta de nuevo.")
        
        transactions_to_create = []

        total_processed = 0

        for _, row in df.iterrows():
            data = {}
            for col in valid_columns:
                val = row[col]
                if val is not None and str(val).lower() not in ['nan', '', 'none']:
                    data[col] = val
            
            if 'sale_date' not in data or 'doc_id' not in data:
                continue

            transactions_to_create.append(self.sale_transaction_model(**data))
            total_processed += 1

        if not transactions_to_create:
            return ImportResult(success=False, message="No se encontraron transacciones válidas para importar.")

        try:
            with transaction.atomic():
                deleted_count, _ = self.sale_transaction_model.objects.filter(sale_date__range=[min_date, max_date]).delete()

                self.sale_transaction_model.objects.bulk_create(
                    transactions_to_create,
                    batch_size=5000
                )

            return ImportResult(
                success=True,
                message=f"Importación exitosa. Se eliminaron {deleted_count} registros antiguos y se crearon {len(transactions_to_create)} nuevos en el rango {min_date} al {max_date}.",
                total_processed=total_processed,
                created_count=len(transactions_to_create),
                updated_count=0
            )

        except Exception as e:
            return ImportResult(
                success=False,
                message=f"Error durante la inserción masiva: {str(e)}",
                total_processed=total_processed,
                errors=[str(e)]
            )


@dataclass
class SaleTransactionsStats:
    '''dedicated only to give general stats about sale transactions'''
    sale_transactions_service: SaleTransactionsService

    @property
    def _base_qs(self) -> QuerySet:
        return self.sale_transactions_service.read_transactions()

    def stats(self, *, qs: QuerySet = None) -> dict:
        base_qs = qs if qs is not None else self._base_qs

        agg = base_qs.aggregate(
            transactions_count=Count('pk', distinct=True),
            total_quantity=Sum('quantity'),
            total_net_amount=Sum('net_amount'),
            total_gross_amount=Sum('gross_amount'),
            total_profit=Sum('profit'),
            avg_ticket=Avg('net_amount'),
            unique_customers_count=Count('customer', distinct=True),
            unique_products_count=Count('product', distinct=True),
        )

        agg['total_quantity'] = agg['total_quantity'] or Decimal('0.0000')
        agg['total_net_amount'] = agg['total_net_amount'] or Decimal('0.00')
        agg['total_gross_amount'] = agg['total_gross_amount'] or Decimal('0.00')
        agg['total_profit'] = agg['total_profit'] or Decimal('0.00')
        agg['avg_ticket'] = agg['avg_ticket'] or Decimal('0.00')

        return agg
