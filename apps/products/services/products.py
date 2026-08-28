from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import ClassVar

from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from django.db.models import (
    Q,
    QuerySet,
    Value,
    BooleanField,
    Prefetch,
    Count,
    Sum,
    Avg,
)
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.core.services.users import UsersService
from ..models import (
    ProductCategory,
    ProductClass,
    ProductProperty,
    Product,
    ProductPropertyValue,
    Stock,
)


class ServiceError(Exception):
    pass


class PermissionsError(ServiceError):
    pass


class ProductNotFound(ServiceError):
    pass


class ProductCategoryNotFound(ServiceError):
    pass


class ProductClassNotFound(ServiceError):
    pass


@dataclass
class ProductsService(UsersService):
    product_model: type = Product
    product_category_model: type = ProductCategory
    product_class_model: type = ProductClass
    product_property_model: type = ProductProperty
    product_property_value_model: type = ProductPropertyValue
    stock_model: type = Stock

    ACCESS_CONTEXTS: ClassVar[tuple[str, ...]] = (
        'acceso_total_productos',
        'productos',
        'acceso_total_inventario',
        'acceso_total_ventas',
        'acceso_total',
    )

    def read_products(self) -> QuerySet:
        """
        returns the qs with products annotated with:
        - select_related: product_class, product_class__product_category
        - annotations: total_stock
        - ordering: name, id
        """
        return (
            self.product_model.objects.select_related(
                'product_class',
                'product_class__product_category'
            )
            .annotate(
                total_stock=Coalesce(
                    Sum('stocks__quantity'),
                    Decimal('0.00'),
                )
            )
            .order_by('name', 'id')
        )

    def read_product(self, *, pk: str) -> Product:
        """
        returns a single product with prefetched property_values and stocks.
        """
        product = (
            self.read_products()
            .filter(pk=pk)
            .prefetch_related(
                Prefetch(
                    'property_values',
                    queryset=self.product_property_value_model.objects.select_related('property').order_by('property__name'),
                ),
                Prefetch(
                    'stocks',
                    queryset=self.stock_model.objects.select_related('warehouse').order_by('warehouse__name', 'expiration_date'),
                ),
            )
            .first()
        )

        if not product:
            raise ProductNotFound(f'No se encontró ningún producto con el ID "{pk}".')

        return product

    def create_product(
        self,
        product_data: dict = None,
        properties_data: list = None,
        stocks_data: list = None,
        **kwargs
    ) -> Product:
        """
        creates a new product along with optional property values and stock records
        """
        if not self.has_full_access:
            raise PermissionsError('No tienes permisos suficientes para registrar productos.')

        data = dict(product_data or {})
        data.update(kwargs)

        try:
            with transaction.atomic():
                new_product = self.product_model(**data)
                new_product.full_clean()
                new_product.save()

                if properties_data:
                    for prop_data in properties_data:
                        if prop_data and not prop_data.get('DELETE', False):
                            p_copy = dict(prop_data)
                            p_copy.pop('DELETE', None)
                            p_copy.pop('id', None)
                            p_copy.pop('product', None)
                            pv = self.product_property_value_model(product=new_product, **p_copy)
                            pv.full_clean()
                            pv.save()

                if stocks_data:
                    for stock_data in stocks_data:
                        if stock_data and not stock_data.get('DELETE', False):
                            s_copy = dict(stock_data)
                            s_copy.pop('DELETE', None)
                            s_copy.pop('id', None)
                            s_copy.pop('product', None)
                            stk = self.stock_model(product=new_product, **s_copy)
                            stk.full_clean()
                            stk.save()

            return new_product

        except ValidationError as e:
            if hasattr(e, 'message_dict'):
                messages = [f"{k}: {', '.join(v)}" for k, v in e.message_dict.items()]
                raise ServiceError(f"Datos inválidos: {'; '.join(messages)}")
            raise ServiceError(f"Datos inválidos: {', '.join(e.messages)}")
        except IntegrityError as e:
            raise ServiceError(f"Error de integridad en la base de datos: {str(e)}")

    def update_product(
        self,
        *,
        pk: str,
        product_data: dict = None,
        properties_data: list = None,
        stocks_data: list = None,
        **kwargs
    ) -> Product:
        """
        updates an existing product along with its property values and stock records
        """
        if not self.has_full_access:
            raise PermissionsError('No tienes permisos suficientes para actualizar productos.')

        product = self.read_product(pk=pk)
        data = dict(product_data or {})
        data.update(kwargs)

        try:
            with transaction.atomic():
                for key, value in data.items():
                    if key != 'id':
                        setattr(product, key, value)

                product.full_clean()
                product.save()

                if properties_data is not None:
                    for prop_data in properties_data:
                        if not prop_data:
                            continue
                        prop_instance = prop_data.get('id')
                        is_delete = prop_data.get('DELETE', False)

                        if is_delete:
                            if prop_instance and getattr(prop_instance, 'pk', None):
                                prop_instance.delete()
                            continue

                        p_copy = dict(prop_data)
                        p_copy.pop('DELETE', None)
                        p_copy.pop('id', None)
                        p_copy.pop('product', None)

                        if prop_instance and getattr(prop_instance, 'pk', None):
                            for f_key, f_val in p_copy.items():
                                setattr(prop_instance, f_key, f_val)
                            prop_instance.full_clean()
                            prop_instance.save()
                        else:
                            pv = self.product_property_value_model(product=product, **p_copy)
                            pv.full_clean()
                            pv.save()

                if stocks_data is not None:
                    for stock_data in stocks_data:
                        if not stock_data:
                            continue
                        stock_instance = stock_data.get('id')
                        is_delete = stock_data.get('DELETE', False)

                        if is_delete:
                            if stock_instance and getattr(stock_instance, 'pk', None):
                                stock_instance.delete()
                            continue

                        s_copy = dict(stock_data)
                        s_copy.pop('DELETE', None)
                        s_copy.pop('id', None)
                        s_copy.pop('product', None)

                        if stock_instance and getattr(stock_instance, 'pk', None):
                            for f_key, f_val in s_copy.items():
                                setattr(stock_instance, f_key, f_val)
                            stock_instance.full_clean()
                            stock_instance.save()
                        else:
                            stk = self.stock_model(product=product, **s_copy)
                            stk.full_clean()
                            stk.save()

            return product

        except ValidationError as e:
            if hasattr(e, 'message_dict'):
                messages = [f"{k}: {', '.join(v)}" for k, v in e.message_dict.items()]
                raise ServiceError(f"Datos inválidos: {'; '.join(messages)}")
            raise ServiceError(f"Datos inválidos: {', '.join(e.messages)}")
        except IntegrityError as e:
            raise ServiceError(f"Error de integridad en la base de datos: {str(e)}")

    def delete_product(self, *, pk: str) -> None:
        """
        deletes an existing product
        """
        if not self.has_full_access:
            raise PermissionsError('No tienes permisos suficientes para eliminar productos.')

        product = self.read_product(pk=pk)
        try:
            product.delete()
        except IntegrityError as e:
            raise ServiceError(f"No se puede eliminar el producto porque tiene registros relacionados: {str(e)}")

    def _clean_products(self, file_obj) -> tuple[bool, str | object]:
        try:
            import pandas as pd
        except ImportError:
            return False, "La librería 'pandas' no está instalada en el entorno."

        from apps.core.services.uploads import BaseETLHelper
        from django.contrib.contenttypes.models import ContentType
        from apps.core.models import Reference
        import datetime

        is_valid, df_or_err = BaseETLHelper.read_file_to_dataframe(file_obj)
        if not is_valid:
            return False, df_or_err

        df = df_or_err
        df = BaseETLHelper.apply_reference_column_mappings(
            df,
            self.product_model,
            submodule_url_name='core:upload_options_list_view',
            context='columna'
        )
        df = BaseETLHelper.resolve_foreign_key_columns(df, self.product_model)

        is_req_valid, req_msg = BaseETLHelper.validate_required_columns(df, {'id': 'Identificador de Producto'})
        if not is_req_valid:
            return False, req_msg

        valid_types_dict = {str(t.id).strip().lower(): t.id for t in self.product_class_model.objects.all()}
        default_type = valid_types_dict.get('otr') or (next(iter(valid_types_dict.values())) if valid_types_dict else None)

        if 'product_class_id' in df.columns:
            df = BaseETLHelper.apply_reference_value_mappings(
                df,
                column='product_class_id',
                target_model=self.product_class_model,
                context='valor_clase_producto',
                submodule_url_name='core:upload_options_list_view'
            )

            df['product_class_id'] = df['product_class_id'].apply(
                lambda x: valid_types_dict.get(str(x).strip().lower(), default_type) if x not in (None, 'None', 'nan', '') else default_type
            )
        elif default_type:
            df['product_class_id'] = default_type

        is_fk_valid, fk_msg = BaseETLHelper.validate_foreign_keys(df, self.product_model)
        if not is_fk_valid:
            return False, fk_msg

        df['id'] = df['id'].astype(str).str.strip()
        df.drop_duplicates(subset=['id'], keep='last', inplace=True)

        for col in df.columns:
            if col not in ['cost', 'price', 'product_class_id', 'id']:
                df[col] = df[col].astype(str).str.strip()
                df[col] = df[col].replace({'nan': None, '': None, 'None': None})

        num_cols = ['cost', 'price']
        for c in num_cols:
            if c in df.columns:
                df[c] = pd.to_numeric(
                    df[c].astype(str).str.replace(r'[$, ]', '', regex=True),
                    errors='coerce'
                ).fillna(0.0)

        df = df.where(pd.notnull(df), None)

        return True, df

    def bulk_create_products(self, file_obj) -> object:
        from apps.core.services.uploads import ImportResult, PermissionsError, BaseETLHelper
        from django.db import transaction

        if not self.has_full_access:
            raise PermissionsError('No tienes permisos suficientes para realizar cargas masivas de productos.')

        is_valid, df_or_err = self._clean_products(file_obj)
        if not is_valid:
            return ImportResult(success=False, message=df_or_err)

        df = df_or_err

        created_count = 0
        updated_count = 0
        total_processed = 0

        model_fields = [f.name for f in self.product_model._meta.get_fields() if not f.is_relation]
        model_fields.extend([f.attname for f in self.product_model._meta.get_fields() if f.is_relation and hasattr(f, 'attname')])
        
        valid_columns = [col for col in df.columns if col in model_fields]

        ids_in_df = df['id'].dropna().astype(str).tolist()
        existing_products = self.product_model.objects.in_bulk(ids_in_df)

        products_to_create = []
        products_to_update = []

        for _, row in df.iterrows():
            cid = str(row.get('id')).strip()
            if not cid or cid in ('None', 'nan', 'null', ''):
                continue

            data = {}
            for col in valid_columns:
                val = row[col]
                if val is not None and str(val).lower() != 'nan':
                    data[col] = val
            data['id'] = cid

            total_processed += 1

            if cid in existing_products:
                product = existing_products[cid]
                for key, value in data.items():
                    setattr(product, key, value)
                products_to_update.append(product)
                updated_count += 1
            else:
                product = self.product_model(**data)
                products_to_create.append(product)
                created_count += 1

        try:
            with transaction.atomic():
                if products_to_create:
                    self.product_model.objects.bulk_create(products_to_create, batch_size=500)
                
                if products_to_update:
                    update_fields = [col for col in valid_columns if col != 'id']
                    if update_fields:
                        self.product_model.objects.bulk_update(products_to_update, update_fields, batch_size=500)
            
            return ImportResult(
                success=True,
                message=f"Importación exitosa. Se crearon {created_count} productos y se actualizaron {updated_count}.",
                total_processed=total_processed,
                created_count=created_count,
                updated_count=updated_count
            )
        except Exception as e:
            humanized_msg = BaseETLHelper.humanize_database_error(e)
            return ImportResult(
                success=False,
                message=humanized_msg,
                total_processed=total_processed,
                errors=[str(e)]
            )

@dataclass
class ProductsStats:
    '''dedicated only to give general stats about products'''
    products_service: ProductsService

    @property
    def _base_qs(self) -> QuerySet:
        return self.products_service.read_products()

    def stats(self, *, qs: QuerySet = None) -> dict:
        base_qs = qs if qs is not None else self._base_qs

        today = timezone.localdate()
        limit_date = today + timedelta(days=30)

        agg = base_qs.aggregate(
            products_count=Count('pk', distinct=True),
            active_products_count=Count('pk', filter=Q(is_active=True), distinct=True),
            inactive_products_count=Count('pk', filter=Q(is_active=False), distinct=True),
            categories_count=Count('product_class__product_category', distinct=True),
            classes_count=Count('product_class', distinct=True),
            avg_price=Avg('price'),
            total_stock=Sum('stocks__quantity'),
            next_to_expire=Sum(
                'stocks__quantity',
                filter=Q(
                    stocks__expiration_date__isnull=False,
                    stocks__expiration_date__lte=limit_date,
                    stocks__expiration_date__gte=today,
                ),
            ),
        )

        agg['total_stock'] = agg['total_stock'] or Decimal('0.00')
        agg['next_to_expire'] = agg['next_to_expire'] or Decimal('0.00')
        agg['avg_price'] = agg['avg_price'] or Decimal('0.00')

        return agg
