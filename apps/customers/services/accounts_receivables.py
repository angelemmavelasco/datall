from dataclasses import dataclass
from decimal import Decimal
from typing import ClassVar

from django.db.models import (
    Q,
    QuerySet,
    Count,
    Sum,
)
from django.utils import timezone

from apps.core.services.users import UsersService
from apps.customers.models import Customer, CustomerAssignment, AccountsReceivable
from apps.sales.models import Route
from apps.sales.services.routes import RoutesService


class ServiceError(Exception):
    pass


class PermissionsError(ServiceError):
    pass


class AccountsReceivableNotFound(ServiceError):
    pass


@dataclass
class AccountsReceivablesService(UsersService):
    accounts_receivable_model: type = AccountsReceivable
    route_model: type = Route
    customer_model: type = Customer
    customer_assignment_model: type = CustomerAssignment

    ACCESS_CONTEXTS: ClassVar[tuple[str, ...]] = (
        'acceso_total_clientes',
        'clientes',
        'acceso_total_ventas',
        'ventas',
        'acceso_total_rutas',
    )

    def _get_allowed_routes_qs(self) -> QuerySet:
        """
        Helper to get allowed routes for the current user using RoutesService.
        """
        routes_service = RoutesService(user=self.user)
        return routes_service.get_allowed_routes(can_view=True, can_edit=False)

    def read_ars_by_allowed_routes(self) -> QuerySet:
        """
        Returns accounts receivable for invoices emitted by routes to which the user has access.
        Independent of whether the customer currently belongs to those routes or not.
        """
        base_qs = self.accounts_receivable_model.objects.select_related(
            'customer',
            'customer__customer_type',
            'route',
            'route__business_unit',
            'route__sale_channel',
        )

        if self.has_full_access:
            return base_qs.order_by('-due_date', '-issue_date', '-id')

        allowed_routes = self._get_allowed_routes_qs()
        return base_qs.filter(route__in=allowed_routes).order_by('-due_date', '-issue_date', '-id')

    def read_ars_by_allowed_customers(self) -> QuerySet:
        """
        Returns accounts receivable corresponding to customers currently assigned to routes
        to which the user has access, regardless of which route historically emitted the invoice.
        """
        base_qs = self.accounts_receivable_model.objects.select_related(
            'customer',
            'customer__customer_type',
            'route',
            'route__business_unit',
            'route__sale_channel',
        )

        if self.has_full_access:
            return base_qs.order_by('-due_date', '-issue_date', '-id')

        today = timezone.localdate()
        allowed_routes = self._get_allowed_routes_qs()

        allowed_customers_subquery = self.customer_assignment_model.objects.filter(
            route__in=allowed_routes
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=today)
        ).values('customer_id')

        return base_qs.filter(customer_id__in=allowed_customers_subquery).order_by('-due_date', '-issue_date', '-id')

    def read_ars(self) -> QuerySet:
        """
        Default accounts receivable listing perspective: based on current customer assignments.
        """
        return self.read_ars_by_allowed_customers()

    def read_ar(self, *, pk: str | int) -> AccountsReceivable:
        """
        Returns a single accounts receivable instance by ID, validated against permissions.
        """
        ar_obj = self.read_ars().filter(pk=pk).first()
        if ar_obj:
            return ar_obj

        if self.accounts_receivable_model.objects.filter(pk=pk).exists():
            raise PermissionsError(f'No tienes permiso para acceder a la cuenta por cobrar con ID "{pk}".')

        raise AccountsReceivableNotFound(f'No se encontró ninguna cuenta por cobrar con el ID "{pk}".')

    def _clean_ars(self, file_obj) -> tuple[bool, str | object]:
        try:
            import pandas as pd
        except ImportError:
            return False, "La librería 'pandas' no está instalada en el entorno."

        from apps.core.services.uploads import BaseETLHelper

        is_valid, df_or_err = BaseETLHelper.read_file_to_dataframe(file_obj)
        if not is_valid:
            return False, df_or_err

        df = df_or_err
        df = BaseETLHelper.apply_reference_column_mappings(
            df,
            self.accounts_receivable_model,
            submodule_name='importacion',
            context='columna'
        )
        df = BaseETLHelper.resolve_foreign_key_columns(df, self.accounts_receivable_model)

        if 'customer_id' not in df.columns:
            return False, "El archivo debe contener una columna identificadora mapeada a 'customer' (ID de Cliente)."

        str_cols = ['customer_id', 'route_id', 'doc_id', 'description']
        for col in str_cols:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
                df[col] = df[col].replace({'nan': None, '': None, 'None': None, 'none': None, 'null': None, 'NULL': None})

        df = df.dropna(subset=['customer_id'])
        if df.empty:
            return False, "Después de limpiar las filas sin cliente, el archivo se quedó vacío."

        from django.contrib.contenttypes.models import ContentType
        from apps.core.models import Reference
        ar_ctype = ContentType.objects.get_for_model(self.accounts_receivable_model)

        if 'issue_date' in df.columns:
            issue_refs = Reference.objects.filter(content_type=ar_ctype, context__icontains='emision')
            for ref in issue_refs:
                k = str(ref.key)
                v = str(ref.value).strip().lower() if getattr(ref, 'value', '') else str(getattr(ref, 'reference', '')).strip().lower()
                if v == 'null':
                    df['issue_date'] = df['issue_date'].replace(k, None)
                elif k and v:
                    df['issue_date'] = df['issue_date'].replace(k, v)

        if 'due_date' in df.columns:
            due_refs = Reference.objects.filter(content_type=ar_ctype, context__icontains='pago')
            for ref in due_refs:
                k = str(ref.key)
                v = str(ref.value).strip().lower() if getattr(ref, 'value', '') else str(getattr(ref, 'reference', '')).strip().lower()
                if v == 'null':
                    df['due_date'] = df['due_date'].replace(k, None)
                elif k and v:
                    df['due_date'] = df['due_date'].replace(k, v)

        date_cols = ['issue_date', 'due_date']
        for col in date_cols:
            if col in df.columns:
                df[col] = df[col].replace({'null': None, 'NULL': None, 'nan': None, 'none': None, '': None})
                df[col] = pd.to_datetime(df[col], errors='coerce').dt.date

        num_cols = ['total_balance', 'balance_15', 'balance_30', 'balance_60', 'past_due', 'current_balance']
        for c in num_cols:
            if c in df.columns:
                df[c] = pd.to_numeric(
                    df[c].astype(str).str.replace(r'[$, ]', '', regex=True),
                    errors='coerce'
                ).fillna(0).round(4)

        df = df.where(pd.notnull(df), None)
        return True, df

    def bulk_create_ars(self, file_obj) -> object:
        from apps.core.services.uploads import ImportResult, PermissionsError
        from django.db import transaction

        if not self.has_full_access:
            raise PermissionsError('No tienes permisos suficientes para reemplazar la cartera de cuentas por cobrar.')

        is_valid, df_or_err = self._clean_ars(file_obj)
        if not is_valid:
            return ImportResult(success=False, message=df_or_err)

        df = df_or_err

        model_fields = [f.name for f in self.accounts_receivable_model._meta.get_fields() if not f.is_relation]
        model_fields.extend([f.attname for f in self.accounts_receivable_model._meta.get_fields() if f.is_relation and hasattr(f, 'attname')])
        
        valid_columns = [col for col in df.columns if col in model_fields and col != 'id']

        fk_fields = [f for f in self.accounts_receivable_model._meta.get_fields() if f.is_relation and hasattr(f, 'attname')]
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
        
        records_to_create = []
        total_processed = 0

        for _, row in df.iterrows():
            data = {}
            for col in valid_columns:
                val = row[col]
                if val is not None and str(val).lower() not in ['nan', '', 'none']:
                    data[col] = val
            
            if 'customer_id' not in data or not data['customer_id']:
                continue

            records_to_create.append(self.accounts_receivable_model(**data))
            total_processed += 1

        if not records_to_create:
            return ImportResult(success=False, message="No se encontraron cuentas por cobrar válidas para importar.")

        try:
            with transaction.atomic():
                self.accounts_receivable_model.objects.all().delete()
                
                self.accounts_receivable_model.objects.bulk_create(
                    records_to_create,
                    batch_size=5000
                )

            return ImportResult(
                success=True,
                message=f"Importación exitosa. Se reemplazó la cartera completa con {len(records_to_create)} nuevos registros.",
                total_processed=total_processed,
                created_count=len(records_to_create),
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
class AccountsReceivablesStats:
    '''Dedicated only to give general stats about accounts receivable'''
    accounts_receivables_service: AccountsReceivablesService

    @property
    def _base_qs(self) -> QuerySet:
        return self.accounts_receivables_service.read_ars()

    def stats(self, *, qs: QuerySet = None) -> dict:
        base_qs = qs if qs is not None else self._base_qs

        agg = base_qs.aggregate(
            ars_count=Count('pk', distinct=True),
            total_balance=Sum('total_balance'),
            current_balance=Sum('current_balance'),
            balance_15=Sum('balance_15'),
            balance_30=Sum('balance_30'),
            balance_60=Sum('balance_60'),
            past_due=Sum('past_due'),
            unique_customers_count=Count('customer', distinct=True),
            unique_routes_count=Count('route', distinct=True),
        )

        agg['total_balance'] = agg['total_balance'] or Decimal('0.0000')
        agg['current_balance'] = agg['current_balance'] or Decimal('0.0000')
        agg['balance_15'] = agg['balance_15'] or Decimal('0.0000')
        agg['balance_30'] = agg['balance_30'] or Decimal('0.0000')
        agg['balance_60'] = agg['balance_60'] or Decimal('0.0000')
        agg['past_due'] = agg['past_due'] or Decimal('0.0000')

        return agg
