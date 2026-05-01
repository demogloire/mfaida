"""Périmètre entreprise et accès dépôts / PDV pour l'application stock."""

from django.db.models import Q

from entreprise.models import Depot, PointVente


def get_entreprise_utilisateur(user):
    if getattr(user, 'branche_id', None):
        return user.branche.entreprise
    from entreprise.models import Entreprise

    return Entreprise.objects.filter(user=user).first()


def utilisateur_est_admin(user):
    return getattr(user, 'admin', False) or getattr(user, 'is_superuser', False)


def queryset_depots_visibles(user, entreprise, admin):
    """
    Dépôts visibles : toujours limités à l'entreprise de l'utilisateur.
    Sans entreprise résolue → aucun dépôt (le module stock exige une société).
    """
    qs = Depot.objects.select_related('branche__entreprise').filter(est_actif=True)
    if not entreprise:
        return Depot.objects.none()
    qs = qs.filter(branche__entreprise=entreprise)
    if admin or user.is_superuser:
        return qs.order_by('branche_id', 'nom')
    depot_ids = list(
        user.acces_depots.filter(peut_voir=True).values_list('depot_id', flat=True)
    )
    return qs.filter(pk__in=depot_ids)


def queryset_points_vente_visibles(user, entreprise, admin):
    """
    Points de vente de l'entreprise ; accès restreint par AccesPointVente pour les non-admins.
    """
    qs = (
        PointVente.objects.select_related('branche__entreprise', 'depot_source')
        .filter(branche__entreprise=entreprise, est_actif=True)
        .order_by('nom')
        if entreprise
        else PointVente.objects.none()
    )
    if admin or user.is_superuser:
        return qs
    pids = list(
        user.acces_points_vente.filter(peut_voir=True).values_list('point_vente_id', flat=True)
    )
    return qs.filter(pk__in=pids)


def peut_modifier_stock_au_depot(user, depot: Depot, admin: bool):
    """Ajustements / inventaire dépôt : inventaire ou admin dépôt, sinon administrateur métier."""
    if admin or user.is_superuser:
        return True
    if not depot:
        return False
    return user.acces_depots.filter(depot_id=depot.pk).filter(
        Q(peut_inventorier=True) | Q(peut_administrer=True)
    ).exists()


def peut_modifier_stock_au_point_vente(user, point_vente: PointVente, admin: bool):
    """
    Stock côté PDV : même exigence sur le dépôt source + droit PDV inventaire/admin si défini,
    sinon repli sur les droits du dépôt source.
    """
    if admin or user.is_superuser:
        return True
    if not point_vente or not point_vente.depot_source_id:
        return False
    if user.acces_points_vente.filter(point_vente_id=point_vente.pk).filter(
        Q(peut_administrer=True)
    ).exists():
        return True
    return peut_modifier_stock_au_depot(user, point_vente.depot_source, admin=False)


def mouvements_disponibles_pour_point_vente(point_vente):
    """Mouvements pouvant être facturés depuis ce PV (dépôt source + périmètre lot)."""
    from stock.models import MouvementStock

    depot_id = point_vente.depot_source_id
    if not depot_id:
        return MouvementStock.objects.none()
    return MouvementStock.objects.filter(
        depot_id=depot_id,
        quantite_active__gt=0,
    ).filter(Q(pointvente__isnull=True) | Q(pointvente_id=point_vente.pk))
