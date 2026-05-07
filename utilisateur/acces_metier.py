"""Vérification centralisée des permissions métier (hors groupe Django Auth)."""


def utilisateur_est_admin_metier(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    return bool(getattr(user, 'admin', False) or getattr(user, 'is_superuser', False))


def utilisateur_peut_permission(user, code: str) -> bool:
    if not code:
        return True
    if not user or not user.is_authenticated:
        return False
    if utilisateur_est_admin_metier(user):
        return True
    role = getattr(user, 'role', None)
    if not role:
        return False
    from .models import RolePermission
    return RolePermission.objects.filter(
        role_id=role.pk, permission__code=code,
    ).exists()


def utilisateur_peut_au_moins_un(user, codes) -> bool:
    if utilisateur_est_admin_metier(user):
        return True
    if not user or not user.is_authenticated:
        return False
    role = getattr(user, 'role', None)
    if not role:
        return False
    codes = tuple(c for c in codes if c)
    if not codes:
        return False
    from .models import RolePermission
    return RolePermission.objects.filter(
        role_id=role.pk, permission__code__in=codes,
    ).exists()
