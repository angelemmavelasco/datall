from apps.core.models import Reference, Route, RouteAssignment, Employee
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

    if user.groups.filter(name='acceso global').exists() or user.is_superuser:
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