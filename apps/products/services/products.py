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
