from dataclasses import dataclass
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


@dataclass
class ProductsStats:
    '''dedicated only to give general stats about products'''
    products_service: ProductsService

    @property
    def _base_qs(self) -> QuerySet:
        return self.products_service.read_products()

    def stats(self, *, qs: QuerySet = None) -> dict:
        base_qs = qs if qs is not None else self._base_qs

        agg = base_qs.aggregate(
            products_count=Count('pk', distinct=True),
            active_products_count=Count('pk', filter=Q(is_active=True), distinct=True),
            inactive_products_count=Count('pk', filter=Q(is_active=False), distinct=True),
            categories_count=Count('product_class__product_category', distinct=True),
            classes_count=Count('product_class', distinct=True),
            avg_price=Avg('price'),
            total_stock=Sum('stocks__quantity'),
        )

        agg['total_stock'] = agg['total_stock'] or Decimal('0.00')
        agg['avg_price'] = agg['avg_price'] or Decimal('0.00')

        return agg
