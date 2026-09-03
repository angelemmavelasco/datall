from django import template

register = template.Library()

@register.filter(name='has_group')
def has_group(user, group_name):
    if not user or not user.is_authenticated:
        return False
    if not hasattr(user, '_group_names_cache'):
        user._group_names_cache = set(user.groups.values_list('name', flat=True))
    return group_name in user._group_names_cache
