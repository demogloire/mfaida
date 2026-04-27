from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """{{ dict|get_item:key }} — accès à un dict par clé dynamique."""
    return dictionary.get(key)


@register.filter
def getattr_filter(obj, attr):
    """{{ obj|getattr_filter:'field_name' }} — accès à un attribut dynamique."""
    if obj is None:
        return False
    return getattr(obj, attr, False)


@register.filter
def in_set(value, container):
    """{{ value|in_set:some_set }} — True si value est dans le set/liste."""
    try:
        return value in container
    except TypeError:
        return False
