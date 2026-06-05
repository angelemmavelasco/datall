from apps.core.models import Reference

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