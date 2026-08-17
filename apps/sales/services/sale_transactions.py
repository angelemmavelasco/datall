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
    customer_model: type = Customer
    customer_assignment_model: type = CustomerAssignment

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
