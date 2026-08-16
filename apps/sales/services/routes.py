from dataclasses import dataclass
from typing import ClassVar

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
            current_employee_business_unit=Subquery(active_assignment_qs.values('employee__business_unit__name')[:1]),
        ).prefetch_related(
            Prefetch(
                'route_assignments',
                queryset=self.route_assignment_model.objects.filter(
                    Q(date_end__isnull=True) | Q(date_end__gte=today)
                ).select_related(
                    'employee',
                    'employee__user',
                    'employee__position',
                    'employee__business_unit'
                ).order_by('-date_start'),
                to_attr='active_assignments'
            )
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