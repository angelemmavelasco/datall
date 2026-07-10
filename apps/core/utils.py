from apps.core.models import Reference, Route, RouteAssignment, Warehouse
from django.db.models import Q


def get_reference(module: str, field_context: str, key: str, default: str | int | float | None = None):

    """
    Look for a reference rule for a given module, context and raw value.
    
    Parameters:
    - module: The module to look for a reference rule, where is being used, example: "customer'
    - field_context: The context of the field, example: 'customer_type'
    - key: The raw value to look for a reference rule, example: 'VET'
    - default: Value to return if the rule is not found.

    Returns:
    - The reference value if found
    - The default value if the rule is not found
    """

    if key is None or str(key).strip() == "":
        return default

    cleaned_key = str(key).strip()

    filters = {
        'field_context': field_context,
        'key': cleaned_key
    }

    if isinstance(module, str):
        filters['module__name__iexact'] = module.strip()
    else:
        filters['module'] = module

    rule = Reference.objects.filter(**filters).first()

    if rule:
        return rule.reference

    return default



def get_allowed_routes_for_user(user):
    """
    Returns a QuerySet of routes to which the user has access, based on their global group, CEDIS or their subordinate tree.
    """


    if user.is_superuser:
        return Route.objects.all()

    user_group_names = [name.strip() for name in user.groups.values_list('name', flat=True)]
    
    if not user_group_names:
        return Route.objects.none()

    group_query = Q()
    for name in user_group_names:
        group_query |= Q(key__iexact=name)

    has_global_access = Reference.objects.filter(
        group_query,
        field_context='allowed_routes'
    ).filter(
        Q(reference__iexact='1') | 
        Q(reference__iexact='true') | 
        Q(reference__icontains='1')
    ).exists()

    if has_global_access:
        return Route.objects.all()

    employee = user.employees.first()
    if not employee:
        return Route.objects.none()

    team_ids = employee.get_reporting_tree_ids()
    

    assigned_routes = RouteAssignment.objects.filter(
        employee_id__in=team_ids,
        end_date__isnull=True
    ).values_list('route_id', flat=True)
    
    return Route.objects.filter(id__in=assigned_routes).distinct()


def get_allowed_warehouses_for_user(user):
    """
    Returns a QuerySet of warehouses to which the user has access, based on their global group or their allowed routes.
    """

    #validate user access
    if user.is_superuser:
        return Warehouse.objects.all()
    
    #validate user group access
    user_group_names = [name.strip() for name in user.groups.values_list('name', flat=True)]
    
    # if user has no groups, return none
    if not user_group_names:
        return Warehouse.objects.none()

    group_query = Q()
    for name in user_group_names:
        group_query |= Q(key__iexact=name)

    has_global_access = Reference.objects.filter(
        group_query,
        field_context='allowed_routes'
    ).filter(
        Q(reference__iexact='1') | 
        Q(reference__iexact='true') | 
        Q(reference__icontains='1')
    ).exists()

    if has_global_access or user.groups.filter(name__iexact='acceso global').exists():
        return Warehouse.objects.all()

    allowed_routes = get_allowed_routes_for_user(user)
    allowed_warehouse_ids = allowed_routes.exclude(warehouse__isnull=True).values_list('warehouse_id', flat=True)
    
    return Warehouse.objects.filter(id__in=allowed_warehouse_ids).distinct()

