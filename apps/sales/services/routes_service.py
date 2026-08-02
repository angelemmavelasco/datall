from apps.sales.models import Route, RouteAssignment, RouteWarehouseLogistic, UserRouteAccess
from apps.inventory.models import Warehouse
from apps.human_resources.models import Employee, BusinessUnit
from dataclasses import dataclass, field
from django.db.models import QuerySet, Q, Count, Prefetch
from django.db import transaction
from datetime import date
from typing import TYPE_CHECKING, Optional
if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser as UserModel
else:
    UserModel = object

class ServiceError(Exception):
    pass

class UserPermissionError(ServiceError):
    pass

class RouteNotFoundError(ServiceError):
    pass

class RoutePermissionError(ServiceError):
    pass

class AssignmentError(ServiceError):
    pass

@dataclass
class RoutesService:
    '''
    the main function of this service is to validate and return information about the relation
    business_unit -> employe -> route -> warehouse, to avoid cross information between unrelated permissions.

    the most important method in this service is get_allowed_routes, which gives to the user a qset of
    allowed routes, taking into account in order of importance:
    
    1. global access / is superuser
    2. employee tree
    3. explicit access
    '''
    user: 'UserModel'
    RouteModel: type[Route] = Route
    RouteAssignmentModel: type[RouteAssignment] = RouteAssignment
    RouteWarehouseLogisticModel: type[RouteWarehouseLogistic] = RouteWarehouseLogistic
    UserRouteAccessModel: type[UserRouteAccess] = UserRouteAccess
    _is_full_access: bool = field(init=False)


    def __post_init__(self) -> None:
        self._validate_access()
        self._is_full_access = self._checkout_full_access()


    def _validate_access(self) -> None:
        '''
        validates if the user was provided, exists and is authenticated.
        '''
        if not self.user:
            raise UserPermissionError('No se ha proporcionado un usuario válido.')
        if not self.user.is_authenticated:
            raise UserPermissionError('El usuario proporcionado no está autenticado.')
        if not getattr(self.user, 'is_active', True):
            raise UserPermissionError('El usuario se encuentra inactivo.')

    def _checkout_full_access(self) -> bool:
        if getattr(self.user, 'is_superuser', False):
            return True
        return self.user.groups.filter(name__in=[
            'total', 'acceso total', 'admin', 'global', 'acceso global'
        ]).exists()

    def get_allowed_routes(self, *, for_selling: bool = False) -> QuerySet[Route]:
        '''
        return a route qs which the main user has access to (for reading or selling).
        it combines global access, employee tree and UserRouteAccess
        '''
        today = date.today()
        if self._is_full_access:
            base_qs = self.RouteModel.objects.all()
        else:
            route_ids = set()
            user_employees = Employee.objects.filter(user=self.user)

            if for_selling:
                # active assignments owned directly by the user
                own_employee_ids = user_employees.values_list('id', flat=True)
                assigned_route_ids = self.RouteAssignmentModel.objects.filter(
                    Q(employee_id__in=own_employee_ids),
                    Q(date_start__lte=today),
                    Q(date_end__isnull=True) | Q(date_end__gte=today)
                ).values_list('route_id', flat=True)
                route_ids.update(assigned_route_ids)

                # explicit sell permissions via UserRouteAccess
                explicit_route_ids = self.UserRouteAccessModel.objects.filter(
                    user=self.user,
                    can_sell=True
                ).values_list('route_id', flat=True)
                route_ids.update(explicit_route_ids)
            else:
                # full supervision/reading permissions for employee tree / managed business units
                tree_employees_ids = []
                for emp in user_employees:
                    tree_employees_ids.extend(emp.get_reporting_tree_ids())
                tree_employees_set = set(tree_employees_ids)

                # active assignments for user and employee tree currently active today
                assigned_route_ids = self.RouteAssignmentModel.objects.filter(
                    Q(employee_id__in=tree_employees_set),
                    Q(date_start__lte=today),
                    Q(date_end__isnull=True) | Q(date_end__gte=today)
                ).values_list('route_id', flat=True)
                route_ids.update(assigned_route_ids)

                # routes belonging to business units managed by any employee in the reporting tree
                managed_business_units = BusinessUnit.objects.filter(
                    manager_id__in=tree_employees_set
                ).values_list('id', flat=True)

                if managed_business_units:
                    bu_route_ids = self.RouteModel.objects.filter(
                        business_unit__in=managed_business_units
                    ).values_list('id', flat=True)
                    route_ids.update(bu_route_ids)

                # explicit view permissions via UserRouteAccess
                explicit_route_ids = self.UserRouteAccessModel.objects.filter(
                    user=self.user,
                    can_view=True
                ).values_list('route_id', flat=True)
                route_ids.update(explicit_route_ids)

            base_qs = self.RouteModel.objects.filter(id__in=route_ids)

        active_assignments = self.RouteAssignmentModel.objects.filter(
            date_start__lte=today
        ).filter(
            Q(date_end__isnull=True) | Q(date_end__gte=today)
        ).select_related('employee__user').order_by('-date_start')

        return base_qs.select_related(
            'business_unit', 'route_type', 'sale_channel'
        ).prefetch_related(
            Prefetch('sales_route_assignments', queryset=active_assignments, to_attr='active_assignments')
        ).order_by('business_unit__id', 'id')

    def get_allowed_bu_by_routes(self) -> QuerySet[BusinessUnit]:
        return BusinessUnit.objects.filter(
            id__in=self.get_allowed_routes().values_list('business_unit_id', flat=True)
        )

    def get_allowed_warehouses_by_routes(self) -> QuerySet[Warehouse]:
        '''
        returns a qs of warehouse where a user can sell inventory
        '''
        allowed_routes_ids = self.get_allowed_routes(for_selling=True).values_list('id', flat=True)
        return Warehouse.objects.filter(
            sales_route_warehouse_logistics__route_id__in=allowed_routes_ids
        ).distinct().order_by('name')

    def read_routes(self, *, for_selling: bool = False) -> QuerySet[Route]:
        '''
        Returns the QuerySet of routes accessible to the authenticated user.
        Follows project naming conventions (read_employees, read_positions, etc.).
        '''
        return self.get_allowed_routes(for_selling=for_selling)

    def read_route(self, *, pk: str, for_selling: bool = False) -> Optional[Route]:
        '''
        Returns a single Route object by PK if the user has access.
        '''
        return self.read_routes(for_selling=for_selling).filter(pk=pk).first()

    def assignment_history(self, *, pk: str):
        '''
        returns a qs with the history of assignments for a given route, no matter if the user is direct manager of
        the past employees or not.

        this service is only for users who can modify or who are full access.
        :param pk:
        :return: qs of route assignment objects
        '''
        if not self.can_modify_route(pk=pk):
            raise RoutePermissionError('El usuario no tiene permisos para ver el historial de asignaciones.')
        return self.RouteAssignmentModel.objects.filter(route_id=pk).order_by('-date_start')


    def can_modify_route(self, *, pk: str) -> bool:
        '''
        determines if the user can modify a given route.

        rules (or):
          - is full access
          - is the manager of the business unit associated to the route
          - The user (or someone in their employee tree) is the direct manager
             of the Employee currently assigned to the route via an active
             RouteAssignment (date_start <= today and date_end is null or >= today).

        returns false if the route does not exist. Returns False when the route
        has no active assignment and the user is neither full access nor a BU
        manager.
        '''
        if self._is_full_access:
            return True

        route = self.RouteModel.objects.filter(pk=pk).only('id', 'business_unit_id').first()
        if not route:
            return False

        #user manages the BU the route belongs to
        if route.business_unit_id and BusinessUnit.objects.filter(
            id=route.business_unit_id,
            manager__user=self.user
        ).exists():
            return True

        #build the user's tree of employee ids once
        user_employees = list(Employee.objects.filter(user=self.user))
        if not user_employees:
            return False

        tree_ids = set()
        for emp in user_employees:
            tree_ids.update(emp.get_reporting_tree_ids())
        if not tree_ids:
            return False

        today = date.today()
        return self.RouteAssignmentModel.objects.filter(
            route_id=pk,
            date_start__lte=today,
            employee__manager_id__in=tree_ids,
        ).filter(
            Q(date_end__isnull=True) | Q(date_end__gte=today)
        ).exists()

    def create_route(self, *, route_data: dict, user_access_data: list) -> Route:
        '''
        create a new route along with its initial set of UserRouteAccess rows.
        Only full access users can create routes.
        '''
        if not self._is_full_access:
            raise RoutePermissionError('El usuario no tiene permisos para crear rutas.')

        # The pk is provided manually by the user in the form
        route_id = route_data.pop('id', None) or self.RouteModel.objects.count() + 1

        with transaction.atomic():
            new_route = self.RouteModel.objects.create(id=route_id, **route_data)

            for access_data in user_access_data:
                if not access_data:
                    continue

                if access_data.get('DELETE', False):
                    continue

                user = access_data.get('user')
                if user:
                    self.UserRouteAccessModel.objects.create(
                        route=new_route,
                        user=user,
                        can_view=access_data.get('can_view', False),
                    )

        return new_route

    def update_route(self, *, pk: str, route_data: dict, user_access_data: list) -> Route:
        '''
        update a route and sync its UserRouteAccess rows based on the inline formset.
        Allowed for full access or when can_modify_route(pk) is True.
        '''
        route_to_update = self.read_route(pk=pk)
        if route_to_update is None:
            raise RouteNotFoundError(f'No se encontró la ruta con id {pk}.')

        if not self._is_full_access and not self.can_modify_route(pk=pk):
            raise RoutePermissionError('El usuario no tiene permisos para editar esta ruta.')

        # pk is read-only on update
        route_data.pop('id', None)

        with transaction.atomic():
            for attr, value in route_data.items():
                setattr(route_to_update, attr, value)
            route_to_update.save()

            for access_data in user_access_data:
                if not access_data:
                    continue

                access_instance = access_data.get('id')
                if access_data.get('DELETE', False):
                    if access_instance:
                        access_instance.delete()
                    continue

                user = access_data.get('user')
                if not user:
                    continue

                if access_instance:
                    access_instance.user = user
                    access_instance.can_view = access_data.get('can_view', False)
                    access_instance.save()
                else:
                    self.UserRouteAccessModel.objects.create(
                        route=route_to_update,
                        user=user,
                        can_view=access_data.get('can_view', False),
                    )

        return route_to_update


@dataclass
class RoutesKpisService:
    '''
    Dedicated to read general stats and information about routes accessible to
    the user. Reuses RoutesService.read_routes() as the base queryset so the
    visibility rules stay consistent with the rest of the module.

    KPIs:
      - registered_routes: total routes the user is allowed to see (read scope).
      - active_routes: routes flagged as is_active=True (apt for assignment or
        currently operating). Counted only within the user's read scope.
      - assigned_routes: visible routes with an active assignment to a third
        party (i.e. the assigned employee is NOT the current user).
      - own_routes: visible routes with an active assignment to the current
        user themselves.

    An assignment is considered active when date_start <= today and
    date_end is null or date_end >= today.
    '''
    routes_service: 'RoutesService'

    @property
    def _base_qs(self) -> QuerySet:
        '''
        Reuse the RoutesService base logic to bring allowed routes and
        calculate KPIs over them.
        '''
        return self.routes_service.read_routes()

    def stats(self, qs=None) -> dict:
        '''
        Returns a dictionary with general route stats scoped to the user.
        '''
        today = date.today()
        base_qs = qs if qs is not None else self._base_qs
        route_ids = list(base_qs.values_list('id', flat=True))

        if not route_ids:
            return {
                'registered_routes': 0,
                'active_routes': 0,
                'assigned_routes': 0,
                'own_routes': 0,
            }

        user_employee_ids = list(
            Employee.objects.filter(user=self.routes_service.user).values_list('id', flat=True)
        )

        # Active assignments only, restricted to the visible route ids
        active_assignments = self.routes_service.RouteAssignmentModel.objects.filter(
            route_id__in=route_ids,
            date_start__lte=today,
        ).filter(
            Q(date_end__isnull=True) | Q(date_end__gte=today)
        )

        if user_employee_ids:
            own_filter = Q(employee_id__in=user_employee_ids)
            other_filter = ~Q(employee_id__in=user_employee_ids)
        else:
            # User has no Employee record -> everything is "assigned to others"
            own_filter = Q(pk__isnull=True)
            other_filter = Q(pk__isnull=False)

        assignment_stats = active_assignments.aggregate(
            assigned_to_others=Count('route_id', distinct=True, filter=other_filter),
            own_routes=Count('route_id', distinct=True, filter=own_filter),
        )

        return {
            'registered_routes': base_qs.count(),
            'active_routes': base_qs.filter(is_active=True).count(),
            'assigned_routes': assignment_stats['assigned_to_others'] or 0,
            'own_routes': assignment_stats['own_routes'] or 0,
        }

