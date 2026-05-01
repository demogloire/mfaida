from django import template

from utilisateur.permissions import peut_voir_prix_achat_ht as _peut_voir_prix_achat_ht

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


@register.filter(name='peut_voir_prix_achat_ht')
def peut_voir_prix_achat_ht_filter(user):
    """True si l'utilisateur peut voir les prix d'achat / coûts (PA HT, etc.)."""
    return _peut_voir_prix_achat_ht(user)
