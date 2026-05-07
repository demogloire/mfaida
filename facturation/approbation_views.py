"""Hub des approbations en attente (proformas + retours)."""

from django.contrib import messages
from django.shortcuts import redirect, render

from stock.access import get_entreprise_utilisateur, utilisateur_est_admin
from utilisateur.acces_metier import utilisateur_peut_permission
from utilisateur.decorators import login_requis

from .models import FactureProforma, RetourVente


def _peut_approuver(user):
    return utilisateur_peut_permission(user, 'approuver_facture_proforma')


def _scope_proformas_attente(user, entreprise, admin):
    qs = FactureProforma.objects.filter(statut='EN_ATTENTE').select_related(
        'client', 'branche', 'vendeur',
    ).order_by('soumis_le')
    if entreprise:
        qs = qs.filter(branche__entreprise=entreprise)
    if not admin:
        branche = getattr(user, 'branche', None)
        if branche:
            qs = qs.filter(branche=branche)
    return qs


def _scope_retours_attente(user, entreprise, admin):
    qs = RetourVente.objects.filter(statut='EN_ATTENTE').select_related(
        'client', 'point_vente', 'vendeur', 'facture_origine',
    ).order_by('soumis_le')
    if entreprise:
        qs = qs.filter(point_vente__branche__entreprise=entreprise)
    if not admin:
        branche = getattr(user, 'branche', None)
        if branche:
            qs = qs.filter(point_vente__branche=branche)
    return qs


@login_requis
def hub_approbations(request):
    if not _peut_approuver(request.user):
        messages.error(request, 'Accès réservé aux managers.')
        return redirect('entreprise:dashboard')

    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)

    proformas = _scope_proformas_attente(request.user, entreprise, admin)
    retours   = _scope_retours_attente(request.user, entreprise, admin)

    sections = [
        {
            'titre':       'Factures proforma',
            'description': 'Devis soumis par les vendeurs en attente de votre approbation.',
            'icone':       'ti-file-invoice',
            'couleur':     'primary',
            'count':       proformas.count(),
            'items':       proformas[:20],
            'type':        'proforma',
            'url_detail':  'facturation:detail-proforma',
            'champ_date':  'soumis_le',
        },
        {
            'titre':       'Retours clients',
            'description': 'Retours de marchandises soumis par les vendeurs.',
            'icone':       'ti-arrow-back-up',
            'couleur':     'warning',
            'count':       retours.count(),
            'items':       retours[:20],
            'type':        'retour',
            'url_detail':  'facturation:detail-retour',
            'champ_date':  'soumis_le',
        },
    ]

    total = sum(s['count'] for s in sections)

    return render(request, 'facturation/approbations/hub.html', {
        'sections': sections,
        'total':    total,
        'actif':    'approbations',
    })
