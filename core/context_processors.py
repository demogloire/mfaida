"""Context processors globaux : données d'en-tête disponibles sur toutes les pages."""

from django.db.models import F

from stock.access import get_entreprise_utilisateur, utilisateur_est_admin


def header_context(request):
    """
    Injecte dans chaque template :
      - entreprise_courante, branche_courante
      - branches_disponibles  (admins : toutes ; sinon : branche du compte)
      - notifs_header         (dict de compteurs pour la cloche)
    """
    user = getattr(request, 'user', None)
    if not user or not getattr(user, 'is_authenticated', False):
        return {}

    try:
        entreprise = get_entreprise_utilisateur(user)
        admin      = utilisateur_est_admin(user)
        branche    = getattr(user, 'branche', None)

        # ── Branches disponibles ────────────────────────────────────────────
        from entreprise.models import Branche
        if admin and entreprise:
            branches_disponibles = list(
                Branche.objects.filter(
                    entreprise=entreprise, est_actif=True
                ).order_by('nom')
            )
        elif branche:
            branches_disponibles = [branche]
        else:
            branches_disponibles = []

        # ── Notifications ───────────────────────────────────────────────────
        from stock.models import Stock
        from rh.models import Conge, AvanceSalaire
        from facturation.models import Facture

        # Ruptures : Stock dont quantite_reelle ≤ seuil alerte du produit
        rup_qs = Stock.objects.select_related('produit', 'depot__branche')
        if entreprise:
            rup_qs = rup_qs.filter(depot__branche__entreprise=entreprise)
        if not admin and branche:
            rup_qs = rup_qs.filter(depot__branche=branche)
        nb_ruptures = rup_qs.filter(
            quantite_reelle__lte=F('produit__stock_alerte')
        ).count()

        # Congés en attente d'approbation
        cg_qs = Conge.objects.filter(statut='DEMANDE')
        if entreprise:
            cg_qs = cg_qs.filter(employe__branche__entreprise=entreprise)
        if not admin and branche:
            cg_qs = cg_qs.filter(employe__branche=branche)
        nb_conges = cg_qs.count()

        # Avances approuvées en attente de décaissement
        av_qs = AvanceSalaire.objects.filter(statut='APPROUVEE')
        if entreprise:
            av_qs = av_qs.filter(employe__branche__entreprise=entreprise)
        if not admin and branche:
            av_qs = av_qs.filter(employe__branche=branche)
        nb_avances = av_qs.count()

        # Factures en attente d'encaissement (statut EN_CAISSE)
        fc_qs = Facture.objects.filter(statut='EN_CAISSE')
        if entreprise:
            fc_qs = fc_qs.filter(point_vente__branche__entreprise=entreprise)
        if not admin and branche:
            fc_qs = fc_qs.filter(point_vente__branche=branche)
        nb_factures_caisse = fc_qs.count()

        notifs_header = {
            'ruptures':        nb_ruptures,
            'conges':          nb_conges,
            'avances':         nb_avances,
            'factures_caisse': nb_factures_caisse,
            'total':           nb_ruptures + nb_conges + nb_avances + nb_factures_caisse,
        }

    except Exception:
        entreprise           = None
        branche              = None
        branches_disponibles = []
        notifs_header = {
            'ruptures': 0, 'conges': 0, 'avances': 0,
            'factures_caisse': 0, 'total': 0,
        }

    return {
        'entreprise_courante':  entreprise,
        'branche_courante':     branche,
        'branches_disponibles': branches_disponibles,
        'notifs_header':        notifs_header,
    }
