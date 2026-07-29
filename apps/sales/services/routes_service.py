from apps.sales.models import Route, RouteAssignment, RouteWarehouseLogistic, UserRouteAccess
from apps.inventory.models import Warehouse
from apps.human_resources.models import Employee, BusinessUnit
from dataclasses import dataclass, field
from django.db.models import QuerySet, Q
from datetime import date
from typing import TYPE_CHECKING, Optional
if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser as UserModel
else:
    UserModel = object


class ServiceError(Exception):
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
            raise PositionNotFoundError('No se ha proporcionado un usuario válido.')
        if not self.user.is_authenticated:
            raise PositionAuthenticationError('El usuario proporcionado no está autenticado.')
        if not getattr(self.user, 'is_active', True):
            raise PositionPermissionError('El usuario se encuentra inactivo.')

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
        #is global/total/super
        if self._is_full_access:
            return self.RouteModel.objects.all().order_by('business_unit__id')

        route_ids = set()
        user_employees = Employee.objects.filter(user=self.user)

        if for_selling:
            #active assignments owned directly by the user
            own_employee_ids = user_employees.values_list('id', flat=True)
            assigned_route_ids = self.RouteAssignmentModel.objects.filter(
                Q(employee_id__in=own_employee_ids),
                Q(date_start__lte=today),
                Q(date_end__isnull=True) | Q(date_end__gte=today)
            ).values_list('route_id', flat=True)
            route_ids.update(assigned_route_ids)

            #explicit sell permissions via UserRouteAccess
            explicit_route_ids = self.UserRouteAccessModel.objects.filter(
                user=self.user,
                can_sell=True
            ).values_list('route_id', flat=True)
            route_ids.update(explicit_route_ids)
        else:
            #full supervision/reading permissions for employee tree / managed business units
            tree_employees_ids = []
            for emp in user_employees:
                tree_employees_ids.extend(emp.get_reporting_tree_ids())

            tree_employees_set = set(tree_employees_ids)

            #active assignments for user and employee tree currently active today
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

        return self.RouteModel.objects.filter(id__in=route_ids).order_by('business_unit__id')

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

    

