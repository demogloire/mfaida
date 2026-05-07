"""Vues Transferts de stock — entre dépôts et points de vente."""

from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from entreprise.models import Depot, PointVente
from stock.access import get_entreprise_utilisateur, utilisateur_est_admin
from stock.models import MouvementStock, TransfertStock, LigneTransfert
from stock.services import valider_transfert_stock
from utilisateur.acces_metier import utilisateur_peut_permission
from utilisateur.decorators import login_requis


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

PERM_PAR_TYPE = {
    'DEPOT_PDV':   'acces_transfert_depot_pdv',
    'PDV_DEPOT':   'acces_transfert_pdv_depot',
    'DEPOT_DEPOT': 'acces_transfert_depot_depot',
    'PDV_PDV':     'acces_transfert_pdv_pdv',
}

TYPES_AUTORISES = list(PERM_PAR_TYPE.keys())


def _types_autorises(user):
    return [t for t, p in PERM_PAR_TYPE.items() if utilisateur_peut_permission(user, p)]


def _peut_au_moins_un(user):
    return bool(_types_autorises(user))


def _scope_transferts(user, entreprise, admin):
    qs = TransfertStock.objects.select_related(
        'source_depot', 'source_pdv', 'dest_depot', 'dest_pdv',
        'effectue_par', 'valide_par',
    ).order_by('-date_creation')
    if entreprise:
        qs = qs.filter(
            Q(source_depot__branche__entreprise=entreprise)
            | Q(source_pdv__branche__entreprise=entreprise)
        )
    return qs


# ─────────────────────────────────────────────
# Liste
# ─────────────────────────────────────────────

@login_requis
def liste_transferts(request):
    if not _peut_au_moins_un(request.user):
        messages.error(request, 'Accès refusé.')
        return redirect('entreprise:dashboard')

    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    qs         = _scope_transferts(request.user, entreprise, admin)

    q_f      = (request.GET.get('q') or '').strip()
    type_f   = (request.GET.get('type_transfert') or '').strip()
    statut_f = (request.GET.get('statut') or '').strip()
    types_ok  = set(TYPES_AUTORISES)
    statuts_ok = {c[0] for c in TransfertStock.STATUTS}

    if type_f in types_ok:
        qs = qs.filter(type_transfert=type_f)
    if statut_f in statuts_ok:
        qs = qs.filter(statut=statut_f)
    if q_f:
        qs = qs.filter(
            Q(numero__icontains=q_f)
            | Q(source_depot__nom__icontains=q_f)
            | Q(source_pdv__nom__icontains=q_f)
            | Q(dest_depot__nom__icontains=q_f)
            | Q(dest_pdv__nom__icontains=q_f)
        )

    types_avec_perm = [
        (code, label) for code, label in TransfertStock.TYPE_CHOICES
        if code in _types_autorises(request.user)
    ]

    return render(request, 'stock/transferts/liste_transferts.html', {
        'transferts':     qs[:300],
        'actif':          'transferts',
        'types_avec_perm': types_avec_perm,
        'types_choix':    TransfertStock.TYPE_CHOICES,
        'statuts_choix':  TransfertStock.STATUTS,
        'filt_q':         q_f,
        'filt_type':      type_f,
        'filt_statut':    statut_f,
    })


# ─────────────────────────────────────────────
# Nouveau transfert
# ─────────────────────────────────────────────

@login_requis
def nouveau_transfert(request):
    if not _peut_au_moins_un(request.user):
        messages.error(request, 'Accès refusé.')
        return redirect('entreprise:dashboard')

    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)

    types_avec_perm = [
        (code, label) for code, label in TransfertStock.TYPE_CHOICES
        if code in _types_autorises(request.user)
    ]

    if entreprise:
        depots = Depot.objects.filter(branche__entreprise=entreprise, est_actif=True).select_related('branche')
        pdvs   = PointVente.objects.filter(branche__entreprise=entreprise, est_actif=True).select_related('branche')
    else:
        depots = Depot.objects.filter(est_actif=True).select_related('branche')
        pdvs   = PointVente.objects.filter(est_actif=True).select_related('branche')

    if request.method == 'POST':
        type_t    = request.POST.get('type_transfert', '').strip()
        src_dep   = request.POST.get('source_depot', '').strip()
        src_pdv   = request.POST.get('source_pdv', '').strip()
        dst_dep   = request.POST.get('dest_depot', '').strip()
        dst_pdv   = request.POST.get('dest_pdv', '').strip()
        motif     = request.POST.get('motif', '').strip()

        erreurs = []

        if type_t not in _types_autorises(request.user):
            erreurs.append('Type de transfert invalide ou non autorisé.')

        source_depot = dest_depot = source_pdv = dest_pdv = None

        if type_t == 'DEPOT_PDV':
            source_depot = depots.filter(pk=src_dep).first() if src_dep.isdigit() else None
            dest_pdv     = pdvs.filter(pk=dst_pdv).first()   if dst_pdv.isdigit() else None
            if not source_depot: erreurs.append('Dépôt source invalide.')
            if not dest_pdv:     erreurs.append('Point de vente destination invalide.')
            if source_depot and dest_pdv and source_depot == dest_pdv:
                erreurs.append('Source et destination identiques.')
        elif type_t == 'PDV_DEPOT':
            source_pdv   = pdvs.filter(pk=src_pdv).first()   if src_pdv.isdigit() else None
            dest_depot   = depots.filter(pk=dst_dep).first()  if dst_dep.isdigit() else None
            if not source_pdv:   erreurs.append('Point de vente source invalide.')
            if not dest_depot:   erreurs.append('Dépôt destination invalide.')
        elif type_t == 'DEPOT_DEPOT':
            source_depot = depots.filter(pk=src_dep).first()  if src_dep.isdigit() else None
            dest_depot   = depots.filter(pk=dst_dep).first()  if dst_dep.isdigit() else None
            if not source_depot: erreurs.append('Dépôt source invalide.')
            if not dest_depot:   erreurs.append('Dépôt destination invalide.')
            if source_depot and dest_depot and source_depot == dest_depot:
                erreurs.append('Les deux dépôts sont identiques.')
        elif type_t == 'PDV_PDV':
            source_pdv   = pdvs.filter(pk=src_pdv).first()   if src_pdv.isdigit() else None
            dest_pdv     = pdvs.filter(pk=dst_pdv).first()   if dst_pdv.isdigit() else None
            if not source_pdv:   erreurs.append('Point de vente source invalide.')
            if not dest_pdv:     erreurs.append('Point de vente destination invalide.')
            if source_pdv and dest_pdv and source_pdv == dest_pdv:
                erreurs.append('Les deux points de vente sont identiques.')

        if erreurs:
            for e in erreurs:
                messages.error(request, e)
        else:
            transfert = TransfertStock(
                type_transfert=type_t,
                source_depot=source_depot,
                source_pdv=source_pdv,
                dest_depot=dest_depot,
                dest_pdv=dest_pdv,
                motif=motif,
                statut='BROUILLON',
                effectue_par=request.user,
            )
            transfert.save()
            messages.success(request, f'Transfert {transfert.numero} créé.')
            return redirect('stock:detail-transfert', pk=transfert.pk)

    return render(request, 'stock/transferts/nouveau_transfert.html', {
        'actif':           'transferts',
        'types_avec_perm': types_avec_perm,
        'depots':          depots,
        'pdvs':            pdvs,
    })


# ─────────────────────────────────────────────
# AJAX : lots disponibles pour une source
# ─────────────────────────────────────────────

@login_requis
def api_produits_source(request):
    """Retourne la liste des produits distincts disponibles à la source."""
    depot_pk = request.GET.get('depot_pk', '').strip()
    pdv_pk   = request.GET.get('pdv_pk', '').strip()
    q        = (request.GET.get('q') or '').strip()

    qs = MouvementStock.objects.filter(quantite_active__gt=0).select_related('produit')
    if depot_pk.isdigit():
        qs = qs.filter(depot_id=int(depot_pk), pointvente__isnull=True)
    elif pdv_pk.isdigit():
        qs = qs.filter(pointvente_id=int(pdv_pk))
    else:
        return JsonResponse({'results': []})

    if q:
        qs = qs.filter(produit__nom__icontains=q)

    # Produits distincts avec la quantité totale disponible
    seen = {}
    for mv in qs.order_by('produit__nom'):
        pid = mv.produit_id
        if pid not in seen:
            seen[pid] = {'id': pid, 'nom': mv.produit.nom, 'total_dispo': float(mv.quantite_active)}
        else:
            seen[pid]['total_dispo'] += float(mv.quantite_active)

    results = [
        {'id': v['id'], 'nom': v['nom'], 'total_dispo': round(v['total_dispo'], 4)}
        for v in seen.values()
    ]
    return JsonResponse({'results': results[:80]})


@login_requis
def api_lots_source(request):
    """Retourne les lots disponibles pour un produit donné à la source."""
    depot_pk   = request.GET.get('depot_pk', '').strip()
    pdv_pk     = request.GET.get('pdv_pk', '').strip()
    produit_pk = request.GET.get('produit_pk', '').strip()

    qs = MouvementStock.objects.filter(quantite_active__gt=0).select_related('produit')
    if depot_pk.isdigit():
        qs = qs.filter(depot_id=int(depot_pk), pointvente__isnull=True)
    elif pdv_pk.isdigit():
        qs = qs.filter(pointvente_id=int(pdv_pk))
    else:
        return JsonResponse({'results': []})

    if produit_pk.isdigit():
        qs = qs.filter(produit_id=int(produit_pk))

    results = [
        {
            'id':         mv.pk,
            'lot':        mv.lot_batch or '—',
            'disponible': str(mv.quantite_active),
            'prix_pu':    str(mv.prix_unitaire),
            'expiration': mv.dateexpiration.strftime('%d/%m/%Y') if mv.dateexpiration else '',
        }
        for mv in qs.order_by('dateexpiration')[:50]
    ]
    return JsonResponse({'results': results})


# ─────────────────────────────────────────────
# Détail + ajout de lignes
# ─────────────────────────────────────────────

@login_requis
def detail_transfert(request, pk):
    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    transfert  = get_object_or_404(
        _scope_transferts(request.user, entreprise, admin)
        .prefetch_related('lignes__produit', 'lignes__mouvement_source'),
        pk=pk,
    )
    peut_editer = transfert.statut == 'BROUILLON' and _peut_au_moins_un(request.user)

    return render(request, 'stock/transferts/detail_transfert.html', {
        'transfert':   transfert,
        'actif':       'transferts',
        'peut_editer': peut_editer,
    })


# ─────────────────────────────────────────────
# Ajouter une ligne
# ─────────────────────────────────────────────

@login_requis
@require_POST
def ajouter_ligne_transfert(request, pk):
    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    transfert  = get_object_or_404(_scope_transferts(request.user, entreprise, admin), pk=pk)

    if transfert.statut != 'BROUILLON':
        messages.error(request, 'Impossible de modifier un transfert non-brouillon.')
        return redirect('stock:detail-transfert', pk=pk)

    mv_pk    = request.POST.get('mouvement_source', '').strip()
    qte_raw  = request.POST.get('quantite', '').strip()

    erreurs = []
    mv = None
    if mv_pk.isdigit():
        mv = MouvementStock.objects.filter(pk=int(mv_pk), quantite_active__gt=0).first()
    if not mv:
        erreurs.append('Lot invalide ou épuisé.')

    qte = None
    if qte_raw:
        try:
            qte = Decimal(qte_raw.replace(',', '.'))
            if qte <= 0:
                erreurs.append('La quantité doit être positive.')
        except Exception:
            erreurs.append('Quantité invalide.')
    else:
        erreurs.append('Quantité requise.')

    if mv and qte and qte > mv.quantite_active:
        erreurs.append(f'Quantité ({qte}) supérieure au disponible ({mv.quantite_active}).')

    if erreurs:
        for e in erreurs:
            messages.error(request, e)
    else:
        LigneTransfert.objects.create(
            transfert=transfert,
            mouvement_source=mv,
            produit=mv.produit,
            quantite=qte,
            prix_unitaire=mv.prix_unitaire,
        )
        messages.success(request, f'Ligne ajoutée : {mv.produit.nom} × {qte}.')

    return redirect('stock:detail-transfert', pk=pk)


# ─────────────────────────────────────────────
# Supprimer une ligne
# ─────────────────────────────────────────────

@login_requis
@require_POST
def supprimer_ligne_transfert(request, pk, ligne_pk):
    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    transfert  = get_object_or_404(_scope_transferts(request.user, entreprise, admin), pk=pk)

    if transfert.statut != 'BROUILLON':
        messages.error(request, 'Impossible de modifier un transfert non-brouillon.')
        return redirect('stock:detail-transfert', pk=pk)

    ligne = get_object_or_404(LigneTransfert, pk=ligne_pk, transfert=transfert)
    ligne.delete()
    messages.success(request, 'Ligne supprimée.')
    return redirect('stock:detail-transfert', pk=pk)


# ─────────────────────────────────────────────
# Valider le transfert
# ─────────────────────────────────────────────

@login_requis
@require_POST
def valider_transfert(request, pk):
    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    transfert  = get_object_or_404(_scope_transferts(request.user, entreprise, admin), pk=pk)

    perm = PERM_PAR_TYPE.get(transfert.type_transfert)
    if not utilisateur_peut_permission(request.user, perm):
        messages.error(request, 'Droits insuffisants pour valider ce type de transfert.')
        return redirect('stock:detail-transfert', pk=pk)

    if not transfert.lignes.exists():
        messages.error(request, 'Ajoutez au moins une ligne avant de valider.')
        return redirect('stock:detail-transfert', pk=pk)

    try:
        valider_transfert_stock(transfert, request.user)
        messages.success(request, f'Transfert {transfert.numero} validé — stock mis à jour.')
    except ValueError as e:
        messages.error(request, str(e))
    except Exception as e:
        messages.error(request, f'Erreur technique lors de la validation : {e}')

    return redirect('stock:detail-transfert', pk=pk)


# ─────────────────────────────────────────────
# Annuler
# ─────────────────────────────────────────────

@login_requis
@require_POST
def annuler_transfert(request, pk):
    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    transfert  = get_object_or_404(_scope_transferts(request.user, entreprise, admin), pk=pk)

    if transfert.statut != 'BROUILLON':
        messages.error(request, 'Seul un transfert en brouillon peut être annulé.')
        return redirect('stock:detail-transfert', pk=pk)

    transfert.statut = 'ANNULE'
    transfert.save(update_fields=['statut'])
    messages.warning(request, f'Transfert {transfert.numero} annulé.')
    return redirect('stock:liste-transferts')
