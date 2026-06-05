from django import template

register = template.Library()

@register.filter(name='can_view_module')
def can_view_module(user, module_name):
    if user.is_superuser:
        return True

    if not user.role:
        return False

    return user.role.permissions.filter(
        module__name=module_name,
        can_view=True
    ).exists()