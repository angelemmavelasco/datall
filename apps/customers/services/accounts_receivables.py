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
