from dataclasses import dataclass
from typing import ClassVar

from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from django.utils import timezone
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
)

from apps.core.services.users import UsersService
from apps.human_resources.models import Employee
from ..models import (
    RouteType,
    SaleChannel,
    Route,
    RouteAssignment,
    UserRouteAccess,
)


class ServiceError(Exception):
    pass


class PermissionsError(ServiceError):
    pass


class RouteNotFound(ServiceError):
    pass


class ValidationError(ServiceError):
    pass


class IntegrityError(ServiceError):
    pass


@dataclass
class RoutesService(UsersService):
    route_model: type = Route
    route_type_model: type = RouteType
    sale_channel_model: type = SaleChannel
    route_assignment_model: type = RouteAssignment
    user_route_access_model: type = UserRouteAccess
    ACCESS_CONTEXTS: ClassVar[tuple[str, ...]] = (
        'acceso_total_rutas',
    )

    def get_allowed_routes(self, *, can_view: bool = True, can_edit: bool = False) -> QuerySet:
        '''
        returns a qs with the allowed routes by the main user.

        params:
        -------
            can_view: bool = True -> if true, adds routes the user can view
            can_edit: bool = False -> if true, adds routes the user can edit

        returns:
        --------
            QuerySet: filtered queryset

        exceptions:
        -----------
            ValueError: if can_view and can_edit are both False
        '''
        if not can_view and not can_edit:
            raise ValueError('El filtro can_view y can_edit no pueden ser ambos falsos')

        base_qs = self.route_model.objects.select_related(
            'business_unit', 'route_type', 'sale_channel'
        )

        if self.has_full_access:
            return base_qs.annotate(
                can_view=Value(True, output_field=BooleanField()),
                can_edit=Value(True, output_field=BooleanField()),
            )

        today = timezone.now().date()
        user_employees = Employee.objects.filter(user=self.user)
        tree_ids = set()
        for emp in user_employees:
            tree_ids.update(emp.get_reporting_tree_ids())

        has_direct_edit = Exists(
            self.user_route_access_model.objects.filter(
                route=OuterRef('pk'),
                user=self.user,
                can_edit=True
            )
        )

        has_direct_view = Exists(
            self.user_route_access_model.objects.filter(
                route=OuterRef('pk'),
                user=self.user,
                can_view=True
            )
        )

        when_view_conditions = [
            When(has_direct_view, then=Value(True)),
            When(has_direct_edit, then=Value(True)),
        ]

        if tree_ids:
            has_tree_assignment = Exists(
                self.route_assignment_model.objects.filter(
                    route=OuterRef('pk'),
                    employee_id__in=tree_ids,
                ).filter(
                    Q(date_end__isnull=True) | Q(date_end__gte=today)
                )
            )
            when_view_conditions.append(When(has_tree_assignment, then=Value(True)))

        annotated_qs = base_qs.annotate(
            can_view=Case(
                *when_view_conditions,
                default=Value(False),
                output_field=BooleanField()
            ),
            can_edit=Case(
                When(has_direct_edit, then=Value(True)),
                default=Value(False),
                output_field=BooleanField()
            )
        )

        if can_view and can_edit:
            return annotated_qs.filter(Q(can_view=True) | Q(can_edit=True))
        elif can_edit:
            return annotated_qs.filter(can_edit=True)
        else:
            return annotated_qs.filter(can_view=True)

    def read_routes(self) -> QuerySet:
        """
        returns the qs with the allowed routes for the main user annotated with:
        - select_related: business_unit, route_type, sale_channel
        - annotations: can_view, can_edit, current_employee_id, current_employee_first_name, current_employee_last_name, current_employee_username, current_assignment_date_start
        - prefetch_related: route_assignments (active only)
        - ordering: id
        
        returns:
        --------
            QuerySet: filtered queryset
        """
        today = timezone.now().date()

        active_assignment_qs = self.route_assignment_model.objects.filter(
            route=OuterRef('pk')
        ).filter(
            Q(date_end__isnull=True) | Q(date_end__gte=today)
        ).order_by('-date_start')

        base_qs = self.get_allowed_routes(can_view=True, can_edit=False)

        return base_qs.annotate(
            current_employee_id=Subquery(active_assignment_qs.values('employee__id')[:1]),
            current_employee_first_name=Subquery(active_assignment_qs.values('employee__user__first_name')[:1]),
            current_employee_last_name=Subquery(active_assignment_qs.values('employee__user__last_name')[:1]),
            current_employee_username=Subquery(active_assignment_qs.values('employee__user__username')[:1]),
            current_assignment_date_start=Subquery(active_assignment_qs.values('date_start')[:1]),
        ).prefetch_related(
            Prefetch(
                'route_assignments',
                queryset=self.route_assignment_model.objects.select_related(
                    'employee',
                    'employee__user',
                    'employee__position',
                    'employee__business_unit'
                ).order_by('-date_start'),
            ),
            Prefetch(
                'userrouteaccess_set',
                queryset=self.user_route_access_model.objects.select_related('user').order_by('user__first_name', 'user__last_name'),
            ),
        ).order_by('id')

    def read_route(self, *, pk: str) -> Route:
        """
        returns a single route with the same annotations and prefetch_related as read_routes.
        
        params:
        -------
            pk: str -> id of the route to read

        returns:
        --------
            Route: filtered queryset
        
        exceptions:
        -----------
            RouteNotFound: if the route does not exist
            PermissionsError: if the user does not have permission to access the route
        """
        route = self.read_routes().filter(pk=pk).first()
        if route:
            return route

        if self.route_model.objects.filter(pk=pk).exists():
            raise PermissionsError(f'No tienes permiso para acceder a la ruta con ID "{pk}".')

        raise RouteNotFound(f'No se encontró ninguna ruta con el ID "{pk}".')

    def create_route(
        self,
        route_data: dict = None,
        assignments_data: list = None,
        accesses_data: list = None,
        **kwargs
    ) -> Route:
        """
        creates a new route along with optional assignments and user accesses
        """
        if not self.has_full_access:
            raise PermissionsError('No tienes permisos suficientes para crear rutas.')

        data = dict(route_data or {})
        data.update(kwargs)

        try:
            with transaction.atomic():
                new_route = self.route_model(**data)
                new_route.full_clean()
                new_route.save()

                if assignments_data:
                    for assignment_data in assignments_data:
                        if assignment_data and not assignment_data.get('DELETE', False):
                            assign_copy = dict(assignment_data)
                            assign_copy.pop('DELETE', None)
                            assign_copy.pop('id', None)
                            assign_copy.pop('route', None)

                            assignment = self.route_assignment_model(route=new_route, **assign_copy)
                            assignment.full_clean()
                            assignment.save()

                if accesses_data:
                    for access_data in accesses_data:
                        if access_data and not access_data.get('DELETE', False):
                            access_copy = dict(access_data)
                            access_copy.pop('DELETE', None)
                            access_copy.pop('id', None)
                            access_copy.pop('route', None)

                            user_access = self.user_route_access_model(route=new_route, **access_copy)
                            user_access.full_clean()
                            user_access.save()

            return new_route

        except ValidationError as e:
            if hasattr(e, 'message_dict'):
                messages = [f"{k}: {', '.join(v)}" for k, v in e.message_dict.items()]
                raise ServiceError(f"Datos inválidos: {'; '.join(messages)}")
            raise ServiceError(f"Datos inválidos: {', '.join(e.messages)}")
        except IntegrityError as e:
            raise ServiceError(f"Ya existe una ruta con ese identificador o se violó una restricción de asignación/acceso: {str(e)}")
        except Exception as e:
            raise ServiceError(f"Error al crear la ruta: {str(e)}")

    def update_route(
        self,
        *,
        pk: str,
        route_data: dict = None,
        assignments_data: list = None,
        accesses_data: list = None,
        **kwargs
    ) -> Route:
        """
        updates an existing route along with assignments and user accesses
        """
        route_to_update = self.read_route(pk=pk)

        if not self.has_full_access:
            raise PermissionsError('No tienes permisos suficientes para actualizar rutas.')

        data = dict(route_data or {})
        data.update(kwargs)

        disallowed = {'id', 'pk'}
        for key in disallowed:
            data.pop(key, None)

        try:
            with transaction.atomic():
                for attr, value in data.items():
                    setattr(route_to_update, attr, value)

                route_to_update.full_clean()
                route_to_update.save()

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
                        assign_copy.pop('route', None)

                        if assignment_instance and assignment_instance.pk:
                            for k, v in assign_copy.items():
                                setattr(assignment_instance, k, v)
                            assignment_instance.full_clean()
                            assignment_instance.save()
                        else:
                            new_assignment = self.route_assignment_model(route=route_to_update, **assign_copy)
                            new_assignment.full_clean()
                            new_assignment.save()

                if accesses_data is not None:
                    for access_data in accesses_data:
                        if not access_data:
                            continue

                        access_instance = access_data.get('id')
                        should_delete = access_data.get('DELETE', False)

                        if should_delete:
                            if access_instance and access_instance.pk:
                                access_instance.delete()
                            continue

                        access_copy = dict(access_data)
                        access_copy.pop('DELETE', None)
                        access_copy.pop('id', None)
                        access_copy.pop('route', None)

                        if access_instance and access_instance.pk:
                            for k, v in access_copy.items():
                                setattr(access_instance, k, v)
                            access_instance.full_clean()
                            access_instance.save()
                        else:
                            new_access = self.user_route_access_model(route=route_to_update, **access_copy)
                            new_access.full_clean()
                            new_access.save()

            return route_to_update

        except ValidationError as e:
            if hasattr(e, 'message_dict'):
                messages = [f"{k}: {', '.join(v)}" for k, v in e.message_dict.items()]
                raise ServiceError(f"Datos inválidos: {'; '.join(messages)}")
            raise ServiceError(f"Datos inválidos: {', '.join(e.messages)}")
        except IntegrityError as e:
            raise ServiceError(f"Error de integridad en base de datos: {str(e)}")
        except Exception as e:
            raise ServiceError(f"Error al actualizar la ruta: {str(e)}")

    def delete_route(self, *, pk: str) -> None:
        """
        deletes a route by id
        """
        route_to_delete = self.read_route(pk=pk)

        if not self.has_full_access:
            raise PermissionsError('No tienes permisos suficientes para eliminar rutas.')

        try:
            with transaction.atomic():
                route_to_delete.delete()
        except IntegrityError:
            raise ServiceError("No se puede eliminar la ruta porque tiene asignaciones u otros registros asociados.")
        except Exception as e:
            raise ServiceError(f"Error al eliminar la ruta: {str(e)}")