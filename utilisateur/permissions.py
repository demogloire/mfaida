"""Règles métier transverses (hors RBAC Django pur)."""

# Sous-chaînes du nom de rôle (insensible à la casse) considérées comme « manager ».
MANAGER_ROLE_KEYWORDS = (
    'manager',
    'gestionnaire',
    'directeur',
    'direction',
    'responsable',
)


def peut_voir_prix_achat_ht(user) -> bool:
    """
    Prix d'achat / coûts : réservés aux administrateurs métier, superusers,
    rôles « manager » (heuristique sur le nom du rôle), ou permission explicite
    `voir_prix_achat_ht` sur le rôle.
    """
    if not user or not user.is_authenticated:
        return False
    if getattr(user, 'is_superuser', False):
        return True
    if getattr(user, 'admin', False):
        return True
    if hasattr(user, 'a_la_permission') and user.a_la_permission('voir_prix_achat_ht'):
        return True
    role = getattr(user, 'role', None)
    if role and role.nom:
        n = role.nom.strip().lower()
        if any(kw in n for kw in MANAGER_ROLE_KEYWORDS):
            return True
    return False
