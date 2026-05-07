"""Context processor : compteurs d'approbations en attente pour la sidebar."""

from utilisateur.acces_metier import utilisateur_peut_permission


def approbations_en_attente(request):
    user = getattr(request, 'user', None)
    if not user or not getattr(user, 'is_authenticated', False):
        return {}
    if not utilisateur_peut_permission(user, 'approuver_facture_proforma'):
        return {'approbations_total': 0}

    from facturation.models import FactureProforma, RetourVente
    from stock.access import get_entreprise_utilisateur, utilisateur_est_admin

    try:
        entreprise = get_entreprise_utilisateur(user)
        admin      = utilisateur_est_admin(user)
        branche    = getattr(user, 'branche', None)

        pf_qs = FactureProforma.objects.filter(statut='EN_ATTENTE')
        rv_qs = RetourVente.objects.filter(statut='EN_ATTENTE')

        if entreprise:
            pf_qs = pf_qs.filter(branche__entreprise=entreprise)
            rv_qs = rv_qs.filter(point_vente__branche__entreprise=entreprise)
        if not admin and branche:
            pf_qs = pf_qs.filter(branche=branche)
            rv_qs = rv_qs.filter(point_vente__branche=branche)

        total = pf_qs.count() + rv_qs.count()
    except Exception:
        total = 0

    return {'approbations_total': total}
