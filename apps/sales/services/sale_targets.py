from dataclasses import dataclass
from decimal import Decimal
from typing import ClassVar

from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from django.db.models import (
    QuerySet,
    Count,
    Sum,
    Avg,
)

from apps.core.services.users import UsersService
from apps.human_resources.models import BusinessUnit
from apps.products.models import ProductClass
from apps.sales.models import SaleTarget, Route
from apps.sales.services.routes import RoutesService


class ServiceError(Exception):
    pass


class PermissionsError(ServiceError):
    pass


class SaleTargetNotFound(ServiceError):
    pass


@dataclass
class SaleTargetsService(UsersService):
    sale_target_model: type = SaleTarget
    route_model: type = Route
    business_unit_model: type = BusinessUnit
    product_class_model: type = ProductClass

    ACCESS_CONTEXTS: ClassVar[tuple[str, ...]] = (
        'acceso_total_ventas',
        'ventas',
        'acceso_total_rutas',
        'acceso_total_cuotas',
        'cuotas',
    )

    def _get_allowed_routes_qs(self) -> QuerySet:
        """
        helper to get allowed routes for the current user using RoutesService
        """
        routes_service = RoutesService(user=self.user)
        return routes_service.get_allowed_routes(can_view=True, can_edit=False)

    def read_sale_targets(self) -> QuerySet:
        """
        Returns the queryset of sale targets for routes the user is allowed to view.
        Selects related: route (and metadata), business_unit (gerencia), product_class (and category).
        """
        base_qs = self.sale_target_model.objects.select_related(
            'route',
            'route__business_unit',
            'route__route_type',
            'route__sale_channel',
            'business_unit',
            'product_class',
            'product_class__product_category',
        )

        if self.has_full_access:
            return base_qs.order_by('-period', 'route__name', 'product_class__name')

        allowed_routes = self._get_allowed_routes_qs()
        return base_qs.filter(route__in=allowed_routes).order_by('-period', 'route__name', 'product_class__name')

    def read_sale_target(self, *, pk: str | int) -> SaleTarget:
        """
        Returns a single sale target by ID if the user has access to its route.

        exceptions:
        -----------
            SaleTargetNotFound: if the sale target does not exist
            PermissionsError: if the user does not have permission to access the sale target
        """
        target_obj = self.read_sale_targets().filter(pk=pk).first()
        if target_obj:
            return target_obj

        if self.sale_target_model.objects.filter(pk=pk).exists():
            raise PermissionsError(f'No tienes permiso para acceder al objetivo de venta con ID "{pk}".')

        raise SaleTargetNotFound(f'No se encontró ningún objetivo de venta con el ID "{pk}".')

    def update_sale_target(
        self,
        *,
        pk: int | str,
        target_data: dict = None,
        **kwargs
    ) -> SaleTarget:
        """
        updates an existing sale target
        """
        target_to_update = self.read_sale_target(pk=pk)

        if not self.has_full_access:
            raise PermissionsError('No tienes permisos suficientes para actualizar objetivos de venta.')

        data = dict(target_data or {})
        data.update(kwargs)

        disallowed = {'id', 'pk'}
        for key in disallowed:
            data.pop(key, None)

        try:
            with transaction.atomic():
                for attr, value in data.items():
                    setattr(target_to_update, attr, value)

                target_to_update.full_clean()
                target_to_update.save()

            return target_to_update

        except ValidationError as e:
            if hasattr(e, 'message_dict'):
                messages = [f"{k}: {', '.join(v)}" for k, v in e.message_dict.items()]
                raise ServiceError(f"Datos inválidos: {'; '.join(messages)}")
            raise ServiceError(f"Datos inválidos: {', '.join(e.messages)}")
        except IntegrityError:
            raise ServiceError("Ya existe un objetivo de venta para ese periodo, ruta y clase de producto.")
        except Exception as e:
            raise ServiceError(f"Error al actualizar el objetivo de venta: {str(e)}")


@dataclass
class SaleTargetsStats:
    '''dedicated only to give general stats about sale targets'''
    sale_targets_service: SaleTargetsService

    @property
    def _base_qs(self) -> QuerySet:
        return self.sale_targets_service.read_sale_targets()

    def stats(self, *, qs: QuerySet = None) -> dict:
        base_qs = qs if qs is not None else self._base_qs

        agg = base_qs.aggregate(
            targets_count=Count('pk', distinct=True),
            total_target_amount=Sum('target_amount'),
            avg_target_amount=Avg('target_amount'),
            unique_routes_count=Count('route', distinct=True),
            unique_business_units_count=Count('business_unit', distinct=True),
            unique_product_classes_count=Count('product_class', distinct=True),
        )

        agg['total_target_amount'] = agg['total_target_amount'] or Decimal('0.00')
        agg['avg_target_amount'] = agg['avg_target_amount'] or Decimal('0.00')

        return agg
