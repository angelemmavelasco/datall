from dataclasses import dataclass
from typing import ClassVar

from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from django.utils import timezone
from decimal import Decimal
from django.db.models import (
    Q,
    QuerySet,
    Exists,
    OuterRef,
    Subquery,
    Case,
    When,
    Value,
    BooleanField,
    Prefetch,
    Count,
    Sum,
    Avg,
)

from apps.core.services.users import UsersService
from apps.sales.services.routes import RoutesService
from ..models import (
    CustomerType,
    Customer,
    CustomerAssignment,
)

class ServiceError(Exception):
    pass

class PermissionsError(ServiceError):
    pass

class CustomerNotFound(ServiceError):
    pass

class CustomerTypeNotFound(ServiceError):
    pass

@dataclass
class CustomersService(UsersService):
    customer_model: type = Customer
    customer_type_model: type = CustomerType
    customer_assignment_model: type = CustomerAssignment
    ACCESS_CONTEXTS: ClassVar[tuple[str, ...]] = (
        'acceso_total_clientes',
        'clientes',
        'acceso_total_ventas',
    )

    def get_allowed_customers(self, *, can_view: bool = True, can_edit: bool = False) -> QuerySet:
        """
        returns a qs with the allowed customers by the main user.

        params:
        -------
            can_view: bool = True -> if true, adds customers the user can view
            can_edit: bool = False -> if true, adds customers the user can edit

        returns:
        --------
            QuerySet: filtered queryset

        exceptions:
        -----------
            ValueError: if can_view and can_edit are both False
        """
        if not can_view and not can_edit:
            raise ValueError('El filtro can_view y can_edit no pueden ser ambos falsos')

        base_qs = self.customer_model.objects.select_related('customer_type')

        if self.has_full_access:
            return base_qs.annotate(
                can_view=Value(True, output_field=BooleanField()),
                can_edit=Value(True, output_field=BooleanField()),
            )

        today = timezone.now().date()
        routes_service = RoutesService(user=self.user)
        allowed_routes_qs = routes_service.get_allowed_routes(can_view=True, can_edit=False)

        has_allowed_route_assignment = Exists(
            self.customer_assignment_model.objects.filter(
                customer=OuterRef('pk'),
                route__in=allowed_routes_qs,
            ).filter(
                Q(end_date__isnull=True) | Q(end_date__gte=today)
            )
        )

        annotated_qs = base_qs.annotate(
            can_view=Case(
                When(has_allowed_route_assignment, then=Value(True)),
                default=Value(False),
                output_field=BooleanField()
            ),
            can_edit=Value(False, output_field=BooleanField())
        )

        if can_view and can_edit:
            return annotated_qs.filter(Q(can_view=True) | Q(can_edit=True))
        elif can_edit:
            return annotated_qs.filter(can_edit=True)
        else:
            return annotated_qs.filter(can_view=True)

    def read_customers(self) -> QuerySet:
        """
        returns the qs with the allowed customers for the main user annotated with:
        - select_related: customer_type
        - annotations: can_view, can_edit, current_route_id, current_route_name,
                       current_route_business_unit, current_route_sale_channel,
                       current_assignment_start_date
        - prefetch_related: assignments (with route and details)
        - ordering: name, id

        returns:
        --------
            QuerySet: filtered queryset
        """
        today = timezone.now().date()

        active_assignment_qs = self.customer_assignment_model.objects.filter(
            customer=OuterRef('pk')
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=today)
        ).order_by('-start_date')

        base_qs = self.get_allowed_customers(can_view=True, can_edit=False)

        return base_qs.annotate(
            current_route_id=Subquery(active_assignment_qs.values('route__id')[:1]),
            current_route_name=Subquery(active_assignment_qs.values('route__name')[:1]),
            current_route_business_unit=Subquery(active_assignment_qs.values('route__business_unit__name')[:1]),
            current_route_sale_channel=Subquery(active_assignment_qs.values('route__sale_channel__name')[:1]),
            current_assignment_start_date=Subquery(active_assignment_qs.values('start_date')[:1]),
        ).prefetch_related(
            Prefetch(
                'assignments',
                queryset=self.customer_assignment_model.objects.select_related(
                    'route',
                    'route__business_unit',
                    'route__sale_channel',
                    'route__route_type'
                ).order_by('-start_date'),
            )
        ).order_by('name', 'id')

    def read_customer(self, *, pk: str) -> Customer:
        """
        returns a single customer with the same annotations and prefetch_related as read_customers.

        params:
        -------
            pk: str -> id of the customer to read

        returns:
        --------
            Customer: filtered customer object

        exceptions:
        -----------
            CustomerNotFound: if the customer does not exist
            PermissionsError: if the user does not have permission to access the customer
        """
        customer = self.read_customers().filter(pk=pk).first()
        if customer:
            return customer

        if self.customer_model.objects.filter(pk=pk).exists():
            raise PermissionsError(f'No tienes permiso para acceder al cliente con ID "{pk}".')

        raise CustomerNotFound(f'No se encontró ningún cliente con el ID "{pk}".')

    def create_customer(
        self,
        customer_data: dict = None,
        assignments_data: list = None,
        **kwargs
    ) -> Customer:
        """
        creates a new customer along with optional route assignments
        """
        if not self.has_full_access:
            raise PermissionsError('No tienes permisos suficientes para registrar clientes.')

        data = dict(customer_data or {})
        data.update(kwargs)

        try:
            with transaction.atomic():
                new_customer = self.customer_model(**data)
                new_customer.full_clean()
                new_customer.save()

                if assignments_data:
                    for assignment_data in assignments_data:
                        if assignment_data and not assignment_data.get('DELETE', False):
                            assign_copy = dict(assignment_data)
                            assign_copy.pop('DELETE', None)
                            assign_copy.pop('id', None)
                            assign_copy.pop('customer', None)

                            assignment = self.customer_assignment_model(customer=new_customer, **assign_copy)
                            assignment.full_clean()
                            assignment.save()

            return new_customer

        except ValidationError as e:
            if hasattr(e, 'message_dict'):
                messages = [f"{k}: {', '.join(v)}" for k, v in e.message_dict.items()]
                raise ServiceError(f"Datos inválidos: {'; '.join(messages)}")
            raise ServiceError(f"Datos inválidos: {', '.join(e.messages)}")
        except IntegrityError as e:
            raise ServiceError(f"Error de integridad en base de datos (clave duplicada o restricción violada): {str(e)}")
        except Exception as e:
            raise ServiceError(f"Error al registrar el cliente: {str(e)}")

    def update_customer(
        self,
        *,
        pk: str,
        customer_data: dict = None,
        assignments_data: list = None,
        **kwargs
    ) -> Customer:
        """
        updates an existing customer along with route assignments
        """
        customer_to_update = self.read_customer(pk=pk)

        if not self.has_full_access:
            raise PermissionsError('No tienes permisos suficientes para actualizar clientes.')

        data = dict(customer_data or {})
        data.update(kwargs)

        disallowed = {'id', 'pk'}
        for key in disallowed:
            data.pop(key, None)

        try:
            with transaction.atomic():
                for attr, value in data.items():
                    setattr(customer_to_update, attr, value)

                customer_to_update.full_clean()
                customer_to_update.save()

                if assignments_data is not None:
                    for assignment_data in assignments_data:
                        if not assignment_data:
                            continue

                        assignment_instance = assignment_data.get('id')
                        should_delete = assignment_data.get('DELETE', False)

                        if should_delete:
                            if assignment_instance and assignment_instance.pk:
                                assignment_instance.delete()
                            continue

                        assign_copy = dict(assignment_data)
                        assign_copy.pop('DELETE', None)
                        assign_copy.pop('id', None)
                        assign_copy.pop('customer', None)

                        if assignment_instance and assignment_instance.pk:
                            for k, v in assign_copy.items():
                                setattr(assignment_instance, k, v)
                            assignment_instance.full_clean()
                            assignment_instance.save()
                        else:
                            new_assignment = self.customer_assignment_model(customer=customer_to_update, **assign_copy)
                            new_assignment.full_clean()
                            new_assignment.save()

            return customer_to_update

        except ValidationError as e:
            if hasattr(e, 'message_dict'):
                messages = [f"{k}: {', '.join(v)}" for k, v in e.message_dict.items()]
                raise ServiceError(f"Datos inválidos: {'; '.join(messages)}")
            raise ServiceError(f"Datos inválidos: {', '.join(e.messages)}")
        except IntegrityError as e:
            raise ServiceError(f"Error de integridad en base de datos: {str(e)}")
        except Exception as e:
            raise ServiceError(f"Error al actualizar el cliente: {str(e)}")

    def delete_customer(self, *, pk: str) -> None:
        """
        deletes a customer by id
        """
        customer_to_delete = self.read_customer(pk=pk)

        if not self.has_full_access:
            raise PermissionsError('No tienes permisos suficientes para eliminar clientes.')

        try:
            with transaction.atomic():
                customer_to_delete.delete()
        except IntegrityError:
            raise ServiceError("No se puede eliminar el cliente porque tiene asignaciones u otros registros vinculados.")
        except Exception as e:
            raise ServiceError(f"Error al eliminar el cliente: {str(e)}")


@dataclass
class CustomersStats:
    '''dedicated only to give general stats about customers'''
    customers_service: CustomersService

    @property
    def _base_qs(self) -> QuerySet:
        return self.customers_service.read_customers()

    def stats(self, *, qs: QuerySet = None) -> dict:
        base_qs = qs if qs is not None else self._base_qs

        agg = base_qs.aggregate(
            customers_count=Count('pk', distinct=True),
            assigned_customers_count=Count(
                'pk',
                filter=Q(current_route_id__isnull=False),
                distinct=True
            ),
            unassigned_customers_count=Count(
                'pk',
                filter=Q(current_route_id__isnull=True),
                distinct=True
            ),
            opinion_leaders_count=Count(
                'pk',
                filter=Q(opinion_leader=True),
                distinct=True
            ),
            total_credit_limit=Sum('credit_limit'),
            avg_credit_limit=Avg('credit_limit'),
            avg_credit_days=Avg('credit_days'),
        )

        agg['total_credit_limit'] = agg['total_credit_limit'] or Decimal('0.00')
        agg['avg_credit_limit'] = agg['avg_credit_limit'] or Decimal('0.00')
        agg['avg_credit_days'] = agg['avg_credit_days'] or 0

        return agg

