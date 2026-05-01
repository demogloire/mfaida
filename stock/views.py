from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

import openpyxl

from entreprise.models import Produit
from utilisateur.decorators import login_requis

from stock.access import (
    get_entreprise_utilisateur,
    queryset_depots_visibles,
    queryset_points_vente_visibles,
    utilisateur_est_admin,
    peut_modifier_stock_au_depot,
    peut_modifier_stock_au_point_vente,
)
from stock.export_tabular import excel_workbook_bytes, fichier_nom_safe_fragment, response_attachment_xlsx
from stock.forms import (
    AjustementStockForm,
    CorrectionInterneLigneForm,
    InventaireCreerForm,
    LigneInventaireAjoutForm,
    MiseAEcartStockForm,
    _Q_MOUV_VISIBLE_LISTE_STOCK,
)
from stock.inventaire_excel_import import importer_lignes_inventaire_excel
from stock.models import (
    BonAjustementStock,
    Inventaire,
    LigneInventaire,
    MouvementOrigine,
    MouvementStock,
    Stock,
    StockMiseAEcart,
)
from stock.services import (
    appliquer_ecarts_inventaire,
    enregistrer_correction_interne_ligne,
    enregistrer_mise_a_ecart_stock,
    retirer_mise_a_ecart_stock,
    enregistrer_ajustement_sur_ligne,
    theorique_produit_lieu,
)


def _exiger_entreprise(request, entreprise):
    """Stock strictement cantonné à l’entreprise du compte (branche ou société propriétaire)."""
    if entreprise:
        return None
    messages.error(request, 'Aucune entreprise associée à votre compte.')
    return redirect('entreprise:dashboard')


def _inventaire_scope_filter(entreprise, user, admin):
    if not entreprise:
        return Inventaire.objects.none()
    qs_base = Inventaire.objects.filter(
        Q(depot__branche__entreprise=entreprise) | Q(pointdevente__branche__entreprise=entreprise)
    )
    if admin or user.is_superuser:
        return qs_base
    dids = list(user.acces_depots.filter(peut_voir=True).values_list('depot_id', flat=True))
    pids = list(
        user.acces_points_vente.filter(peut_voir=True).values_list('point_vente_id', flat=True)
    )
    return qs_base.filter(Q(depot_id__in=dids) | Q(pointdevente_id__in=pids))


def _liste_stocks_context(request, lieu, row_limit=2000):
    """
    Lignes de stock utilisables (quantite_active > 0) et constats inventaire :
    lignes Inventaire avec la quantité physique en « Reçu » et actif à 0 (traçabilité).
    Détail réception / lots par dépôt ou PDV.
    """
    entreprise = get_entreprise_utilisateur(request.user)
    admin = utilisateur_est_admin(request.user)
    redir = _exiger_entreprise(request, entreprise)
    if redir:
        return redir

    q = (request.GET.get('q') or '').strip()

    depots = queryset_depots_visibles(request.user, entreprise, admin)
    pvs = queryset_points_vente_visibles(request.user, entreprise, admin)

    qs = MouvementStock.objects.select_related(
        'produit',
        'depot',
        'pointvente',
        'location',
        'effectue_par',
        'ligneordreachat__ordre_achat',
        'inventaire',
    ).filter(produit__entreprise=entreprise).filter(_Q_MOUV_VISIBLE_LISTE_STOCK)

    if lieu == 'depot':
        depot_pk = request.GET.get('depot')
        qs = qs.filter(depot__in=depots, pointvente__isnull=True)
        if depot_pk:
            qs = qs.filter(depot_id=depot_pk)
        filter_depots = depots
        filter_pvs = None
        filt_pk = depot_pk or ''
        filt_field = 'depot'
    else:
        pv_pk = request.GET.get('point_vente')
        qs = qs.filter(pointvente__in=pvs)
        if pv_pk:
            qs = qs.filter(pointvente_id=pv_pk)
        filter_depots = None
        filter_pvs = pvs
        filt_pk = pv_pk or ''
        filt_field = 'point_vente'

    if q:
        qs = qs.filter(
            Q(produit__nom__icontains=q)
            | Q(produit__sku__icontains=q)
            | Q(produit__code_barre__icontains=q)
        )

    product_totals = {
        row['produit_id']: row['tot'] or Decimal('0')
        for row in qs.values('produit_id').annotate(tot=Sum('quantite_active'))
    }

    qs = qs.order_by('depot__nom', 'pointvente__nom', 'produit__nom', '-date_creation', '-pk')

    lignes = []
    slice_q = qs[:row_limit] if row_limit is not None else qs
    for m in slice_q:
        alerte = m.produit.stock_alerte or Decimal('0')
        total_p = product_totals.get(m.produit_id, Decimal('0'))
        lignes.append(
            {
                'mouvement': m,
                'sous_seuil': total_p < alerte,
            }
        )

    actif_dep = 'stock_gestion_depot' if lieu == 'depot' else 'stock_gestion_pdv'
    return entreprise, {
        'lignes': lignes,
        'depots': filter_depots,
        'points_vente': filter_pvs,
        'filt_pk': filt_pk,
        'filt_field': filt_field,
        'lieu': lieu,
        'q': q,
        'actif': actif_dep,
        'entreprise': entreprise,
    }


def _liste_stocks_synthese_context(request, lieu):
    """Quantités agrégées par produit + à l'écart + disponible (physique − écart)."""
    entreprise = get_entreprise_utilisateur(request.user)
    admin = utilisateur_est_admin(request.user)
    redir = _exiger_entreprise(request, entreprise)
    if redir:
        return redir

    q = (request.GET.get('q') or '').strip()
    depots = queryset_depots_visibles(request.user, entreprise, admin)
    pvs = queryset_points_vente_visibles(request.user, entreprise, admin)

    base = Stock.objects.filter(produit__entreprise=entreprise)

    if lieu == 'depot':
        depot_pk = request.GET.get('depot')
        base = base.filter(depot__in=depots, pointdevente__isnull=True)
        if depot_pk:
            base = base.filter(depot_id=depot_pk)
        filter_depots = depots
        filter_pvs = None
        filt_pk = depot_pk or ''
        filt_field = 'depot'
    else:
        pv_pk = request.GET.get('point_vente')
        base = base.filter(pointdevente__in=pvs)
        if pv_pk:
            base = base.filter(pointdevente_id=pv_pk)
        filter_depots = None
        filter_pvs = pvs
        filt_pk = pv_pk or ''
        filt_field = 'point_vente'

    if q:
        base = base.filter(
            Q(produit__nom__icontains=q)
            | Q(produit__sku__icontains=q)
            | Q(produit__code_barre__icontains=q)
        )

    agr = base.values('produit_id').annotate(physique=Sum('quantite_reelle'))
    prod_ids = [a['produit_id'] for a in agr if a['produit_id']]

    ec_base = StockMiseAEcart.objects.filter(
        produit__entreprise=entreprise,
        actif=True,
    )
    if prod_ids:
        ec_base = ec_base.filter(produit_id__in=prod_ids)

    if lieu == 'depot':
        ec_base = ec_base.filter(depot__in=depots, pointdevente__isnull=True)
        if request.GET.get('depot'):
            ec_base = ec_base.filter(depot_id=request.GET.get('depot'))
    else:
        ec_base = ec_base.filter(pointdevente__in=pvs)
        if request.GET.get('point_vente'):
            ec_base = ec_base.filter(pointdevente_id=request.GET.get('point_vente'))

    ec_map = {
        row['produit_id']: row['t'] or Decimal('0')
        for row in ec_base.values('produit_id').annotate(t=Sum('quantite'))
    }

    mouv = MouvementStock.objects.filter(
        produit__entreprise=entreprise,
        quantite_active__gt=0,
    )
    if lieu == 'depot':
        mouv = mouv.filter(depot__in=depots, pointvente__isnull=True)
        if depot_pk:
            mouv = mouv.filter(depot_id=depot_pk)
    else:
        mouv = mouv.filter(pointvente__in=pvs)
        if pv_pk:
            mouv = mouv.filter(pointvente_id=pv_pk)
    if q:
        mouv = mouv.filter(
            Q(produit__nom__icontains=q)
            | Q(produit__sku__icontains=q)
            | Q(produit__code_barre__icontains=q)
        )

    mouv_agr = mouv.values('produit_id').annotate(
        qty_lots=Sum('quantite_active'),
        val_lots=Sum(
            ExpressionWrapper(
                F('quantite_active') * F('prix_unitaire'),
                output_field=DecimalField(max_digits=24, decimal_places=6),
            )
        ),
    )
    pu_map = {}
    for row in mouv_agr:
        qty_l = row['qty_lots'] or Decimal('0')
        if qty_l > 0:
            pu_map[row['produit_id']] = (row['val_lots'] or Decimal('0')) / qty_l

    produits_bulk = Produit.objects.in_bulk(prod_ids)
    lignes = []
    total_valeur_ecart = Decimal('0')
    total_valeur_disponible = Decimal('0')
    for a in agr:
        pid = a['produit_id']
        p = produits_bulk.get(pid)
        if not p:
            continue
        phy = a['physique'] or Decimal('0')
        ec = ec_map.get(pid, Decimal('0'))
        if phy <= 0 and ec <= 0:
            continue
        disp = phy - ec
        pu = pu_map.get(pid)
        if pu is None:
            pu = p.prix_achat_ht or Decimal('0')
        valeur_ecart = ec * pu
        valeur_disponible = disp * pu
        total_valeur_ecart += valeur_ecart
        total_valeur_disponible += valeur_disponible
        alerte = p.stock_alerte or Decimal('0')
        lignes.append(
            {
                'produit': p,
                'physique': phy,
                'a_ecart': ec,
                'disponible': disp,
                'prix_unitaire_ref': pu,
                'valeur_ecart': valeur_ecart,
                'valeur_disponible': valeur_disponible,
                'sous_seuil': bool(alerte > 0 and disp < alerte),
            }
        )

    lignes.sort(key=lambda r: r['produit'].nom.lower())

    actif = 'stock_synthese_depot' if lieu == 'depot' else 'stock_synthese_pdv'
    return entreprise, {
        'lignes_synthese': lignes,
        'total_valeur_ecart': total_valeur_ecart,
        'total_valeur_disponible': total_valeur_disponible,
        'depots': filter_depots,
        'points_vente': filter_pvs,
        'filt_pk': filt_pk,
        'filt_field': filt_field,
        'lieu': lieu,
        'q': q,
        'actif': actif,
        'entreprise': entreprise,
    }


def _mise_a_ecart_queryset(request, lieu):
    """Périmètre + queryset `StockMiseAEcart` ; dernier tuple = redirect si pas d’entreprise."""
    entreprise = get_entreprise_utilisateur(request.user)
    admin = utilisateur_est_admin(request.user)
    redir = _exiger_entreprise(request, entreprise)
    if redir:
        return None, None, None, None, '', '', '', redir

    depots = queryset_depots_visibles(request.user, entreprise, admin)
    pvs = queryset_points_vente_visibles(request.user, entreprise, admin)

    filt_depot = request.GET.get('depot', '')
    filt_pv = request.GET.get('point_vente', '')
    filt_q = (request.GET.get('q') or '').strip()

    mises_qs = StockMiseAEcart.objects.select_related(
        'produit', 'depot', 'pointdevente', 'cree_par', 'mouvement_stock'
    ).filter(produit__entreprise=entreprise, actif=True)

    if lieu == 'depot':
        mises_qs = mises_qs.filter(depot__in=depots, pointdevente__isnull=True)
        if filt_depot:
            mises_qs = mises_qs.filter(depot_id=filt_depot)
    else:
        mises_qs = mises_qs.filter(pointdevente__in=pvs)
        if filt_pv:
            mises_qs = mises_qs.filter(pointdevente_id=filt_pv)

    if filt_q:
        mises_qs = mises_qs.filter(
            Q(produit__nom__icontains=filt_q)
            | Q(produit__sku__icontains=filt_q)
            | Q(motif__icontains=filt_q)
        )

    return entreprise, mises_qs, depots, pvs, filt_depot, filt_pv, filt_q, None


def _traiter_mise_a_ecart(request, lieu):
    entreprise, mises_qs, depots, pvs, filt_depot, filt_pv, filt_q, redir = (
        _mise_a_ecart_queryset(request, lieu)
    )
    if redir:
        return redir
    admin = utilisateur_est_admin(request.user)

    if request.method == 'POST':
        form = MiseAEcartStockForm(
            request.POST,
            user=request.user,
            entreprise=entreprise,
            admin=admin,
            lieu=lieu,
        )
        if form.is_valid():
            try:
                mv = form.cleaned_data['mouvement_stock']
                enregistrer_mise_a_ecart_stock(
                    request.user,
                    entreprise=entreprise,
                    mouvement_stock_id=mv.pk,
                    quantite=form.cleaned_data['quantite'],
                    motif=form.cleaned_data['motif'],
                )
                messages.success(request, 'Quantité mise à l’écart sur la ligne (actif −, +écarter).')
                return redirect(
                    'stock:mise-a-ecart-pdv'
                    if lieu == 'pv'
                    else 'stock:mise-a-ecart-depot'
                )
            except ValueError as exc:
                messages.error(request, str(exc))
    else:
        form = MiseAEcartStockForm(
            user=request.user, entreprise=entreprise, admin=admin, lieu=lieu
        )

    tpl = 'stock/mise_ecart_pdv.html' if lieu == 'pv' else 'stock/mise_ecart_depot.html'
    actif_nav = (
        'stock_mise_ecart_pdv'
        if lieu == 'pv'
        else 'stock_mise_ecart_depot'
    )
    data = {
        'form': form,
        'mises': list(mises_qs.order_by('-date_creation')[:500]),
        'depots': depots if lieu == 'depot' else None,
        'points_vente': pvs if lieu == 'pv' else None,
        'filt_pk_depot': filt_depot if lieu == 'depot' else '',
        'filt_pk_pv': filt_pv if lieu == 'pv' else '',
        'filt_field': 'depot' if lieu == 'depot' else 'point_vente',
        'lieu': lieu,
        'entreprise': entreprise,
        'actif': actif_nav,
        'q': filt_q,
    }

    def _perms_mise(mi):
        if mi.pointdevente_id:
            return peut_modifier_stock_au_point_vente(
                request.user, mi.pointdevente, admin
            )
        return peut_modifier_stock_au_depot(request.user, mi.depot, admin)

    data['peut_retirer_ids'] = {mi.pk for mi in data['mises'] if _perms_mise(mi)}

    picker_name = (
        'stock:mise-ecart-lignes-picker-depot' if lieu == 'depot' else 'stock:mise-ecart-lignes-picker-pdv'
    )
    data.update(
        {
            'picker_url': reverse(picker_name),
            'filtre_param': 'depot' if lieu == 'depot' else 'point_vente',
        }
    )

    return render(request, tpl, data)


def _liste_mouvements_context(request, lieu, mouvements_limit=500):
    entreprise = get_entreprise_utilisateur(request.user)
    admin = utilisateur_est_admin(request.user)
    redir = _exiger_entreprise(request, entreprise)
    if redir:
        return redir

    depots = queryset_depots_visibles(request.user, entreprise, admin)
    depot_ids = list(depots.values_list('pk', flat=True))
    pvs = queryset_points_vente_visibles(request.user, entreprise, admin)
    pv_ids = list(pvs.values_list('pk', flat=True))

    origine = request.GET.get('origine', '')
    qs = MouvementStock.objects.select_related(
        'produit', 'depot', 'pointvente', 'effectue_par'
    ).filter(produit__entreprise=entreprise)

    if lieu == 'depot':
        qs = qs.filter(depot_id__in=depot_ids, pointvente__isnull=True)
        actif = 'stock_mouvements_depot'
    else:
        qs = qs.filter(pointvente_id__in=pv_ids)
        actif = 'stock_mouvements_pdv'

    if origine:
        qs = qs.filter(origine=origine)

    qs = qs.order_by('-date_creation')
    if mouvements_limit is not None:
        qs = qs[:mouvements_limit]

    return entreprise, {
        'mouvements': qs,
        'origine': origine,
        'origines': MouvementOrigine.choices,
        'lieu': lieu,
        'actif': actif,
    }


@login_requis
def hub_stock(request):
    entreprise = get_entreprise_utilisateur(request.user)
    redir = _exiger_entreprise(request, entreprise)
    if redir:
        return redir
    admin = utilisateur_est_admin(request.user)
    depots_ct = queryset_depots_visibles(request.user, entreprise, admin).count()
    pv_ct = queryset_points_vente_visibles(request.user, entreprise, admin).count()
    return render(
        request,
        'stock/hub.html',
        {'entreprise': entreprise, 'depots_ct': depots_ct, 'pv_ct': pv_ct},
    )


def _unwrap_or_render(request, ctx, template):
    if not isinstance(ctx, tuple):
        return ctx
    _ent, data = ctx
    return render(request, template, data)


@login_requis
def liste_stocks_depot(request):
    return _unwrap_or_render(
        request,
        _liste_stocks_context(request, 'depot'),
        'stock/liste_stocks_depot.html',
    )


@login_requis
def liste_stocks_pdv(request):
    return _unwrap_or_render(
        request,
        _liste_stocks_context(request, 'pv'),
        'stock/liste_stocks_pdv.html',
    )


@login_requis
def liste_stocks_depot_synthese(request):
    return _unwrap_or_render(
        request,
        _liste_stocks_synthese_context(request, 'depot'),
        'stock/liste_stocks_depot_synthese.html',
    )


@login_requis
def liste_stocks_pdv_synthese(request):
    return _unwrap_or_render(
        request,
        _liste_stocks_synthese_context(request, 'pv'),
        'stock/liste_stocks_pdv_synthese.html',
    )


@login_requis
def mise_a_ecart_depot(request):
    return _traiter_mise_a_ecart(request, 'depot')


@login_requis
def mise_a_ecart_pdv(request):
    return _traiter_mise_a_ecart(request, 'pv')


@login_requis
def mise_ecart_lignes_picker_depot(request):
    return _rendu_fragment_lignes_ajuster(request, 'depot')


@login_requis
def mise_ecart_lignes_picker_pdv(request):
    return _rendu_fragment_lignes_ajuster(request, 'pv')


@login_requis
@require_POST
def mise_a_ecart_retirer(request, pk):
    entreprise = get_entreprise_utilisateur(request.user)
    redir = _exiger_entreprise(request, entreprise)
    if redir:
        return redir
    referer = request.META.get('HTTP_REFERER') or reverse('stock:hub-stock')
    try:
        retirer_mise_a_ecart_stock(request.user, pk, entreprise)
    except StockMiseAEcart.DoesNotExist:
        messages.error(request, 'Mise introuvable ou déjà retirée.')
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(
            request,
            'Mise à l’écart annulée : la ligne a retrouvé sa quantité active (écarter −).',
        )
    return redirect(referer)


@login_requis
def liste_mouvements_depot(request):
    return _unwrap_or_render(
        request,
        _liste_mouvements_context(request, 'depot'),
        'stock/liste_mouvements.html',
    )


@login_requis
def liste_mouvements_pdv(request):
    return _unwrap_or_render(
        request,
        _liste_mouvements_context(request, 'pv'),
        'stock/liste_mouvements.html',
    )


@login_requis
def detail_produit_stock(request, pk):
    ctx = _detail_produit_stock_context(request, pk, mouvements_limit=120)
    if not isinstance(ctx, dict):
        return ctx
    ctx['actif'] = 'stock_gestion_depot'
    return render(
        request,
        'stock/detail_produit.html',
        ctx,
    )


def _detail_produit_stock_context(request, pk, mouvements_limit=120):
    entreprise = get_entreprise_utilisateur(request.user)
    admin = utilisateur_est_admin(request.user)
    redir = _exiger_entreprise(request, entreprise)
    if redir:
        return redir

    produit = get_object_or_404(Produit, pk=pk, entreprise=entreprise)

    depots = queryset_depots_visibles(request.user, entreprise, admin)
    depot_ids = list(depots.values_list('pk', flat=True))
    pvs = queryset_points_vente_visibles(request.user, entreprise, admin)

    niveaux_depot = list(
        Stock.objects.select_related('depot')
        .filter(produit=produit, depot_id__in=depot_ids, pointdevente__isnull=True)
        .order_by('depot__nom')
    )
    niveaux_pdv = list(
        Stock.objects.select_related('depot', 'pointdevente')
        .filter(produit=produit, pointdevente__in=pvs)
        .order_by('pointdevente__nom')
    )

    mouv_depot_qs = MouvementStock.objects.select_related('depot', 'location').filter(
        produit=produit, depot_id__in=depot_ids, pointvente__isnull=True
    ).order_by('-date_creation')
    mouv_pdv_qs = MouvementStock.objects.select_related(
        'depot', 'pointvente', 'location'
    ).filter(produit=produit, pointvente__in=pvs).order_by('-date_creation')
    if mouvements_limit is not None:
        mouv_depot_qs = mouv_depot_qs[:mouvements_limit]
        mouv_pdv_qs = mouv_pdv_qs[:mouvements_limit]

    return {
        'produit': produit,
        'niveaux_depot': niveaux_depot,
        'niveaux_pdv': niveaux_pdv,
        'mouvements_depot': list(mouv_depot_qs),
        'mouvements_pdv': list(mouv_pdv_qs),
        'entreprise': entreprise,
    }


def _rendu_fragment_lignes_ajuster(request, lieu):
    """Fragment HTML (lignes <tr>) pour le modal choix MouvementStock."""
    entreprise = get_entreprise_utilisateur(request.user)
    admin = utilisateur_est_admin(request.user)
    redir = _exiger_entreprise(request, entreprise)
    if redir:
        return redir

    depots = queryset_depots_visibles(request.user, entreprise, admin)
    pvs = queryset_points_vente_visibles(request.user, entreprise, admin)

    lignes_qs = MouvementStock.objects.select_related(
        'produit', 'depot', 'pointvente', 'location'
    ).filter(produit__entreprise=entreprise, quantite_active__gt=0)

    erreur = None

    if lieu == 'depot':
        depot_id = request.GET.get('depot')
        if not depot_id:
            erreur = 'Choisissez d’abord un dépôt dans le formulaire.'
        else:
            if not depots.filter(pk=depot_id).exists():
                erreur = 'Vous ne pouvez pas consulter ce dépôt.'
            else:
                lignes_qs = lignes_qs.filter(depot_id=depot_id, pointvente__isnull=True)
    else:
        pv_id = request.GET.get('point_vente')
        if not pv_id:
            erreur = 'Choisissez d’abord un point de vente.'
        else:
            pv = pvs.filter(pk=pv_id, depot_source_id__isnull=False).first()
            if not pv:
                erreur = 'Point de vente inaccessible ou sans dépôt source.'
            else:
                lignes_qs = lignes_qs.filter(pointvente_id=pv.pk, depot_id=pv.depot_source_id)

    lignes = []
    if not erreur:
        lignes = list(lignes_qs.order_by('-date_creation', '-pk')[:600])

    return render(
        request,
        'stock/partials/ajuster_lignes_picker_rows.html',
        {'lignes': lignes, 'erreur': erreur},
    )


@login_requis
def ajuster_lignes_picker_depot(request):
    return _rendu_fragment_lignes_ajuster(request, 'depot')


@login_requis
def ajuster_lignes_picker_pdv(request):
    return _rendu_fragment_lignes_ajuster(request, 'pv')


def _resoudre_bon_actif_adjustement(request, entreprise, lieu, depots_qs, pvs_qs):
    raw = (request.GET.get('bon') or request.POST.get('bon_ajustement_id') or '').strip()
    if not raw:
        return None, []
    bon = BonAjustementStock.objects.filter(pk=raw, entreprise=entreprise).first()
    if not bon:
        return None, []
    if lieu == 'depot':
        if bon.pointvente_id is not None:
            return None, []
        if not depots_qs.filter(pk=bon.depot_id).exists():
            return None, []
    else:
        if bon.pointvente_id is None:
            return None, []
        if not pvs_qs.filter(pk=bon.pointvente_id, depot_source_id__isnull=False).exists():
            return None, []
    lignes = list(
        bon.lignes.select_related('mouvement_stock__produit').order_by('date_creation')
    )
    return bon, lignes


def _traiter_ajustement(request, lieu):
    entreprise = get_entreprise_utilisateur(request.user)
    admin = utilisateur_est_admin(request.user)
    redir = _exiger_entreprise(request, entreprise)
    if redir:
        return redir

    depots = queryset_depots_visibles(request.user, entreprise, admin)
    pvs = queryset_points_vente_visibles(request.user, entreprise, admin).filter(
        depot_source__isnull=False
    )
    bon_actif, lignes_bon = _resoudre_bon_actif_adjustement(request, entreprise, lieu, depots, pvs)

    picker_name = (
        'stock:ajuster-lignes-picker-depot' if lieu == 'depot' else 'stock:ajuster-lignes-picker-pdv'
    )
    liste_mouv_name = 'stock:liste-mouvements-pdv' if lieu == 'pv' else 'stock:liste-mouvements-depot'
    self_url = reverse('stock:ajuster-stock-pdv' if lieu == 'pv' else 'stock:ajuster-stock-depot')

    if request.method == 'POST':
        form = AjustementStockForm(
            request.POST,
            user=request.user,
            entreprise=entreprise,
            admin=admin,
            lieu=lieu,
            bon_actif=bon_actif,
        )
        if form.is_valid():
            try:
                cd = form.cleaned_data
                with transaction.atomic():
                    bon = cd.get('bon')
                    if bon is None:
                        num = (cd.get('reference_piece') or '').strip()[:80]
                        if lieu == 'depot':
                            bon = BonAjustementStock(
                                entreprise=entreprise,
                                depot=cd['depot_effet'],
                                pointvente=None,
                                numero=num,
                                cree_par=request.user,
                            )
                        else:
                            bon = BonAjustementStock(
                                entreprise=entreprise,
                                depot=cd['depot_effet'],
                                pointvente=cd['point_vente'],
                                numero=num,
                                cree_par=request.user,
                            )
                        bon.save()
                    else:
                        bon = BonAjustementStock.objects.select_for_update().get(pk=bon.pk)

                    mv_in = cd['mouvement_stock']
                    pu = cd.get('prix_unitaire_ht')
                    mv, pu_effectif, ligne_trace = enregistrer_ajustement_sur_ligne(
                        utilisateur=request.user,
                        mouvement_stock_id=mv_in.pk,
                        sens=cd['sens'],
                        quantite=cd['quantite'],
                        motif=cd['motif'],
                        reference_piece='',
                        prix_unitaire=pu,
                        bon=bon,
                    )

                from finance.posting import poster_variation_pure_ohada
                from datetime import date

                pu_montant = Decimal(str(pu)) if pu is not None else Decimal(str(pu_effectif))
                montant = Decimal(str(cd['quantite'])) * pu_montant
                if montant > 0:
                    aug = cd['sens'] == 1
                    ref50 = (
                        f"{bon.numero}-L{ligne_trace.pk}"[:50]
                        if ligne_trace is not None
                        else f"AJ-{mv.pk}"[:50]
                    )
                    try:
                        poster_variation_pure_ohada(
                            entreprise,
                            montant,
                            aug,
                            ref50,
                            date.today(),
                            f"Ajustement {bon.numero} — ligne stock #{mv.pk}",
                            request.user,
                        )
                    except Exception as exc:
                        messages.warning(request, f'Comptabilité non enregistrée : {exc}')
                messages.success(
                    request,
                    f'Ligne ajoutée au bon {bon.numero} (mouvement stock #{mv.pk} — {mv.produit.nom}). '
                    'Vous pouvez enregistrer d’autres lignes ou terminer.',
                )
                return redirect(f'{self_url}?bon={bon.pk}')
            except ValueError as exc:
                messages.error(request, str(exc))
    else:
        initial = {}
        if bon_actif:
            initial['bon_ajustement_id'] = bon_actif.pk
            if lieu == 'depot':
                initial['depot'] = bon_actif.depot_id
            else:
                initial['point_vente'] = bon_actif.pointvente_id
        form = AjustementStockForm(
            user=request.user,
            entreprise=entreprise,
            admin=admin,
            lieu=lieu,
            initial=initial,
            bon_actif=bon_actif,
        )

    return render(
        request,
        'stock/ajuster_stock.html',
        {
            'form': form,
            'entreprise': entreprise,
            'actif': 'stock_ajustement_depot' if lieu == 'depot' else 'stock_ajustement_pdv',
            'lieu': lieu,
            'picker_url': reverse(picker_name),
            'filtre_param': 'depot' if lieu == 'depot' else 'point_vente',
            'titre': 'Ajustement — dépôt' if lieu == 'depot' else 'Ajustement — point de vente',
            'sous_titre': (
                'Un numéro d’ajustement regroupe plusieurs lignes (tracé). Ensuite choix du lot '
                '(quantité active), entrée ou sortie — '
                f'{entreprise.nom}'
            ),
            'lien_niveaux': (
                reverse('stock:liste-stock-depot')
                if lieu == 'depot'
                else reverse('stock:liste-stock-pdv')
            ),
            'label_lien_niveaux': 'Voir les niveaux (dépôt)' if lieu == 'depot' else 'Voir les niveaux PDV',
            'lien_bas': reverse('stock:ajuster-stock-pdv' if lieu == 'depot' else 'stock:ajuster-stock-depot'),
            'label_lien_bas': (
                'Passer à l’ajustement PDV' if lieu == 'depot' else 'Passer à l’ajustement dépôt'
            ),
            'bon_courant': bon_actif,
            'lignes_bon': lignes_bon,
            'lien_mouvements': reverse(liste_mouv_name),
            'url_ajuster_courante': self_url,
            'lien_liste_bons': (
                reverse('stock:liste-bons-ajustement-depot')
                if lieu == 'depot'
                else reverse('stock:liste-bons-ajustement-pdv')
            ),
        },
    )


@login_requis
def ajuster_stock_depot(request):
    return _traiter_ajustement(request, 'depot')


@login_requis
def ajuster_stock_pdv(request):
    return _traiter_ajustement(request, 'pv')


def _rendu_fragment_lignes_correction_interne(request, lieu):
    """Fragment modal : lignes comme la liste stock (actif ou constat inventaire)."""
    entreprise = get_entreprise_utilisateur(request.user)
    admin = utilisateur_est_admin(request.user)
    redir = _exiger_entreprise(request, entreprise)
    if redir:
        return redir

    depots = queryset_depots_visibles(request.user, entreprise, admin)
    pvs = queryset_points_vente_visibles(request.user, entreprise, admin)

    lignes_qs = MouvementStock.objects.select_related(
        'produit',
        'depot',
        'pointvente',
        'location',
    ).filter(produit__entreprise=entreprise).filter(_Q_MOUV_VISIBLE_LISTE_STOCK)

    erreur = None

    if lieu == 'depot':
        depot_id = request.GET.get('depot')
        if not depot_id:
            erreur = 'Choisissez d’abord un dépôt.'
        elif not depots.filter(pk=depot_id).exists():
            erreur = 'Ce dépôt n’est pas accessible.'
        else:
            lignes_qs = lignes_qs.filter(depot_id=depot_id, pointvente__isnull=True)
    else:
        pv_id = request.GET.get('point_vente')
        if not pv_id:
            erreur = 'Choisissez d’abord un point de vente.'
        else:
            pv = pvs.filter(pk=pv_id, depot_source_id__isnull=False).first()
            if not pv:
                erreur = 'Point de vente inaccessible ou sans dépôt source.'
            else:
                lignes_qs = lignes_qs.filter(pointvente_id=pv.pk, depot_id=pv.depot_source_id)

    lignes = []
    if not erreur:
        lignes = list(lignes_qs.order_by('-date_creation', '-pk')[:600])

    return render(
        request,
        'stock/partials/correction_interne_lignes_picker_rows.html',
        {'lignes': lignes, 'erreur': erreur},
    )


def _traiter_correction_interne_stock(request, lieu):
    entreprise = get_entreprise_utilisateur(request.user)
    redir = _exiger_entreprise(request, entreprise)
    if redir:
        return redir
    admin = utilisateur_est_admin(request.user)

    if request.method == 'POST':
        form = CorrectionInterneLigneForm(
            request.POST,
            user=request.user,
            entreprise=entreprise,
            admin=admin,
            lieu=lieu,
        )
        if form.is_valid():
            try:
                cd = form.cleaned_data
                mv = cd['mouvement_stock']
                enregistrer_correction_interne_ligne(
                    request.user,
                    entreprise=entreprise,
                    mouvement_stock_id=mv.pk,
                    lot_batch=cd.get('lot_batch') or '',
                    dateproduction=cd.get('dateproduction'),
                    dateexpiration=cd.get('dateexpiration'),
                    location=cd.get('location'),
                    location_code=cd.get('location_code') or '',
                    marque=cd.get('marque') or '',
                    conditionnement=cd.get('conditionnement') or '',
                    motif=cd.get('motif') or '',
                )
                messages.success(
                    request,
                    f'Correction interne enregistrée (ligne #{mv.pk}, {mv.produit.libelle_ligne_achat}).',
                )
                url = reverse(
                    'stock:correction-interne-pdv'
                    if lieu == 'pv'
                    else 'stock:correction-interne-depot'
                )
                return redirect(url)
            except ValueError as exc:
                messages.error(request, str(exc))
    else:
        form = CorrectionInterneLigneForm(
            user=request.user, entreprise=entreprise, admin=admin, lieu=lieu
        )

    depots = queryset_depots_visibles(request.user, entreprise, admin)
    pvs = queryset_points_vente_visibles(request.user, entreprise, admin)
    picker_name = (
        'stock:correction-interne-lignes-picker-depot'
        if lieu == 'depot'
        else 'stock:correction-interne-lignes-picker-pdv'
    )
    self_rev = (
        'stock:correction-interne-depot'
        if lieu == 'depot'
        else 'stock:correction-interne-pdv'
    )
    autres_rev = (
        'stock:correction-interne-pdv'
        if lieu == 'depot'
        else 'stock:correction-interne-depot'
    )

    data = {
        'form': form,
        'lieu': lieu,
        'entreprise': entreprise,
        'picker_url': reverse(picker_name),
        'filtre_param': 'depot' if lieu == 'depot' else 'point_vente',
        'depots': depots if lieu == 'depot' else None,
        'points_vente': pvs if lieu == 'pv' else None,
        'actif': (
            'stock_correction_interne_depot'
            if lieu == 'depot'
            else 'stock_correction_interne_pdv'
        ),
        'titre_page': (
            'Correction interne des lignes — dépôt'
            if lieu == 'depot'
            else 'Correction interne des lignes — point de vente'
        ),
        'self_url': reverse(self_rev),
        'lien_autre_lieu_url': reverse(autres_rev),
        'lien_autre_lieu_label': ('Passer au PDV' if lieu == 'depot' else 'Passer au dépôt'),
        'liste_stock_url': reverse(
            'stock:liste-stock-depot' if lieu == 'depot' else 'stock:liste-stock-pdv'
        ),
    }
    return render(request, 'stock/correction_interne_stock.html', data)


@login_requis
def correction_interne_depot(request):
    return _traiter_correction_interne_stock(request, 'depot')


@login_requis
def correction_interne_pdv(request):
    return _traiter_correction_interne_stock(request, 'pv')


@login_requis
def correction_lignes_picker_depot(request):
    return _rendu_fragment_lignes_correction_interne(request, 'depot')


@login_requis
def correction_lignes_picker_pdv(request):
    return _rendu_fragment_lignes_correction_interne(request, 'pv')


@login_requis
def liste_bons_ajustement_depot(request):
    entreprise = get_entreprise_utilisateur(request.user)
    admin = utilisateur_est_admin(request.user)
    redir = _exiger_entreprise(request, entreprise)
    if redir:
        return redir
    depots = queryset_depots_visibles(request.user, entreprise, admin)
    qs = (
        BonAjustementStock.objects.filter(
            entreprise=entreprise,
            pointvente__isnull=True,
            depot__in=depots,
        )
        .annotate(nl=Count('lignes'))
        .select_related('depot', 'cree_par')
        .order_by('-date_creation')[:600]
    )
    return render(
        request,
        'stock/liste_bons_ajustement.html',
        {
            'entreprise': entreprise,
            'liste_scope': 'depot',
            'bons': list(qs),
            'actif': 'bons_ajustement_depot',
        },
    )


@login_requis
def liste_bons_ajustement_pdv(request):
    entreprise = get_entreprise_utilisateur(request.user)
    admin = utilisateur_est_admin(request.user)
    redir = _exiger_entreprise(request, entreprise)
    if redir:
        return redir
    pvs = queryset_points_vente_visibles(request.user, entreprise, admin).filter(depot_source__isnull=False)
    qs = (
        BonAjustementStock.objects.filter(entreprise=entreprise, pointvente__in=pvs)
        .annotate(nl=Count('lignes'))
        .select_related('pointvente', 'depot', 'cree_par')
        .order_by('-date_creation')[:600]
    )
    return render(
        request,
        'stock/liste_bons_ajustement.html',
        {
            'entreprise': entreprise,
            'liste_scope': 'pv',
            'bons': list(qs),
            'actif': 'bons_ajustement_pdv',
        },
    )


@login_requis
def detail_bon_ajustement(request, pk):
    entreprise = get_entreprise_utilisateur(request.user)
    admin = utilisateur_est_admin(request.user)
    redir = _exiger_entreprise(request, entreprise)
    if redir:
        return redir
    depots = queryset_depots_visibles(request.user, entreprise, admin)
    pvs = queryset_points_vente_visibles(request.user, entreprise, admin).filter(depot_source__isnull=False)
    bon = get_object_or_404(
        BonAjustementStock.objects.select_related('entreprise', 'depot', 'pointvente', 'cree_par'),
        pk=pk,
        entreprise=entreprise,
    )
    if bon.pointvente_id:
        if not pvs.filter(pk=bon.pointvente_id).exists():
            raise Http404
        liste_retour_url = reverse('stock:liste-bons-ajustement-pdv')
        ajouter_url = f"{reverse('stock:ajuster-stock-pdv')}?bon={bon.pk}"
        peut_ajouter = peut_modifier_stock_au_point_vente(request.user, bon.pointvente, admin)
        actif_nav = 'bons_ajustement_pdv'
    else:
        if not depots.filter(pk=bon.depot_id).exists():
            raise Http404
        liste_retour_url = reverse('stock:liste-bons-ajustement-depot')
        ajouter_url = f"{reverse('stock:ajuster-stock-depot')}?bon={bon.pk}"
        peut_ajouter = peut_modifier_stock_au_depot(request.user, bon.depot, admin)
        actif_nav = 'bons_ajustement_depot'
    lignes = list(
        bon.lignes.select_related('mouvement_stock__produit').order_by('date_creation')
    )
    return render(
        request,
        'stock/detail_bon_ajustement.html',
        {
            'bon': bon,
            'lignes': lignes,
            'liste_retour_url': liste_retour_url,
            'ajouter_url': ajouter_url,
            'peut_ajouter': peut_ajouter,
            'entreprise': entreprise,
            'actif': actif_nav,
        },
    )


def _traiter_inventaire_creer(request, lieu):
    entreprise = get_entreprise_utilisateur(request.user)
    admin = utilisateur_est_admin(request.user)
    redir = _exiger_entreprise(request, entreprise)
    if redir:
        return redir

    if request.method == 'POST':
        form = InventaireCreerForm(
            request.POST,
            user=request.user,
            entreprise=entreprise,
            admin=admin,
            lieu=lieu,
        )
        if form.is_valid():
            inv = form.save(commit=False)
            depot = form.cleaned_data.get('depot')
            pv = form.cleaned_data.get('pointdevente')
            if depot:
                if not peut_modifier_stock_au_depot(request.user, depot, admin):
                    messages.error(request, 'Droits insuffisants sur ce dépôt.')
                    tpl = (
                        'stock/inventaire_form_depot.html'
                        if lieu == 'depot'
                        else 'stock/inventaire_form_pdv.html'
                    )
                    return render(
                        request,
                        tpl,
                        {
                            'form': form,
                            'entreprise': entreprise,
                            'lieu': lieu,
                            'actif': (
                                'stock_inventaire_depot'
                                if lieu == 'depot'
                                else 'stock_inventaire_pdv'
                            ),
                        },
                    )
            elif pv:
                if not peut_modifier_stock_au_point_vente(request.user, pv, admin):
                    messages.error(request, 'Droits insuffisants sur ce point de vente.')
                    tpl = (
                        'stock/inventaire_form_depot.html'
                        if lieu == 'depot'
                        else 'stock/inventaire_form_pdv.html'
                    )
                    return render(
                        request,
                        tpl,
                        {
                            'form': form,
                            'entreprise': entreprise,
                            'lieu': lieu,
                            'actif': (
                                'stock_inventaire_depot'
                                if lieu == 'depot'
                                else 'stock_inventaire_pdv'
                            ),
                        },
                    )
            inv.save()
            messages.success(request, 'Campagne créée.')
            return redirect('stock:detail-inventaire', pk=inv.pk)
    else:
        form = InventaireCreerForm(
            user=request.user, entreprise=entreprise, admin=admin, lieu=lieu
        )

    tpl = (
        'stock/inventaire_form_depot.html'
        if lieu == 'depot'
        else 'stock/inventaire_form_pdv.html'
    )
    actif = (
        'stock_inventaire_depot' if lieu == 'depot' else 'stock_inventaire_pdv'
    )
    return render(
        request,
        tpl,
        {'form': form, 'entreprise': entreprise, 'lieu': lieu, 'actif': actif},
    )


@login_requis
def creer_inventaire_depot(request):
    return _traiter_inventaire_creer(request, 'depot')


@login_requis
def creer_inventaire_pdv(request):
    return _traiter_inventaire_creer(request, 'pv')


@login_requis
def liste_inventaires(request):
    entreprise = get_entreprise_utilisateur(request.user)
    admin = utilisateur_est_admin(request.user)
    redir = _exiger_entreprise(request, entreprise)
    if redir:
        return redir

    filt = request.GET.get('lieu', '')
    qs = (
        _inventaire_scope_filter(entreprise, request.user, admin)
        .select_related('depot', 'pointdevente', 'valide_par')
        .prefetch_related('lignes')
        .order_by('-date_inventaire', '-pk')
    )
    if filt == 'depot':
        qs = qs.filter(depot__isnull=False, pointdevente__isnull=True)
    elif filt == 'pv':
        qs = qs.filter(pointdevente__isnull=False)

    return render(
        request,
        'stock/inventaires_liste.html',
        {
            'inventaires': qs,
            'filt_lieu': filt,
            'actif': 'stock_inventaire',
            'entreprise': entreprise,
        },
    )


def _charger_inventaire(request, pk):
    entreprise = get_entreprise_utilisateur(request.user)
    admin = utilisateur_est_admin(request.user)
    if not entreprise:
        return None, redirect('entreprise:dashboard')
    qs = _inventaire_scope_filter(entreprise, request.user, admin)
    inv = get_object_or_404(
        qs.select_related('depot', 'pointdevente'), pk=pk
    )
    return inv, None


@login_requis
def detail_inventaire(request, pk):
    inv, redir = _charger_inventaire(request, pk)
    if redir:
        return redir

    entreprise = get_entreprise_utilisateur(request.user)
    admin = utilisateur_est_admin(request.user)
    lignes_form = LigneInventaireAjoutForm(entreprise=entreprise)

    if inv.pointdevente_id:
        depot_cible = inv.pointdevente.depot_source
        pv_stock = inv.pointdevente
    else:
        depot_cible = inv.depot
        pv_stock = None

    enriched = []
    for li in inv.lignes.select_related('produit').order_by('produit__nom'):
        th = theorique_produit_lieu(li.produit_id, depot_cible, pv_stock)
        enriched.append({'ligne': li, 'theorique_actuel': th})

    peut = False
    if not inv.cloture:
        if inv.pointdevente_id:
            peut = peut_modifier_stock_au_point_vente(request.user, inv.pointdevente, admin)
        else:
            peut = peut_modifier_stock_au_depot(request.user, depot_cible, admin)

    actif_inv = (
        'stock_inventaire_pdv' if inv.pointdevente_id else 'stock_inventaire_depot'
    )

    return render(
        request,
        'stock/inventaire_detail.html',
        {
            'inventaire': inv,
            'ligne_form': lignes_form,
            'lignes': enriched,
            'actif': actif_inv,
            'entreprise': entreprise,
            'admin': admin,
            'peut_cloturer': peut,
        },
    )


@login_requis
@require_POST
def inventaire_ajouter_ligne(request, pk):
    inv, redir = _charger_inventaire(request, pk)
    if redir:
        return redir
    if inv.cloture:
        messages.error(request, 'Inventaire clôturé.')
        return redirect('stock:detail-inventaire', pk=pk)

    entreprise = get_entreprise_utilisateur(request.user)
    form = LigneInventaireAjoutForm(request.POST, entreprise=entreprise)

    if inv.pointdevente_id:
        depot_cible = inv.pointdevente.depot_source
        pv_stock = inv.pointdevente
    else:
        depot_cible = inv.depot
        pv_stock = None

    if form.is_valid():
        prod = form.cleaned_data['produit']
        th = theorique_produit_lieu(prod.pk, depot_cible, pv_stock)
        LigneInventaire.objects.update_or_create(
            inventaire=inv,
            produit=prod,
            defaults={
                'quantite_theorique': th,
                'quantite_physique': form.cleaned_data['quantite_physique'],
            },
        )
        messages.success(request, 'Ligne enregistrée.')
    else:
        messages.error(request, 'Vérifiez la ligne.')

    return redirect('stock:detail-inventaire', pk=pk)


def _inventaire_lieu_stock(inv):
    """(depot_cible, pointvente_stock | None) pour théoriques / lignes."""
    if inv.pointdevente_id:
        return inv.pointdevente.depot_source, inv.pointdevente
    return inv.depot, None


def _peut_modifier_inventaire_ouvert(inv, request, admin) -> bool:
    if inv.cloture:
        return False
    if inv.pointdevente_id:
        return peut_modifier_stock_au_point_vente(request.user, inv.pointdevente, admin)
    return peut_modifier_stock_au_depot(request.user, inv.depot, admin)


@login_requis
def inventaire_modele_import_excel(request, pk):
    inv, redir = _charger_inventaire(request, pk)
    if redir:
        return redir
    hdr = ['SKU', 'Code-barres', 'Qté physique']
    rows = [
        ['SKU-EXEMPLE', '', 0],
        ['', '3760000000012', 12],
    ]
    buf = excel_workbook_bytes(
        [('Lignes inventaire', hdr, rows)],
    )
    nom = fichier_nom_safe_fragment(f'{inv.lot or "inv"}_modele_import')
    return response_attachment_xlsx(buf, f'{nom}.xlsx')


@login_requis
@require_POST
def inventaire_import_excel_lignes(request, pk):
    inv, redir = _charger_inventaire(request, pk)
    if redir:
        return redir
    entreprise = get_entreprise_utilisateur(request.user)
    admin = utilisateur_est_admin(request.user)
    if not _peut_modifier_inventaire_ouvert(inv, request, admin):
        messages.error(request, 'Vous ne pouvez pas modifier cet inventaire.')
        return redirect('stock:detail-inventaire', pk=pk)

    depot_cible, pv_stock = _inventaire_lieu_stock(inv)
    fichier = request.FILES.get('fichier')
    if not fichier:
        messages.error(request, 'Choisissez un fichier Excel (.xlsx).')
        return redirect('stock:detail-inventaire', pk=pk)
    if fichier.size > 6 * 1024 * 1024:
        messages.error(request, 'Fichier trop volumineux (max. 6 Mo).')
        return redirect('stock:detail-inventaire', pk=pk)
    name_l = (fichier.name or '').lower()
    if not name_l.endswith(('.xlsx', '.xlsm')):
        messages.error(request, 'Format requis : fichier Excel .xlsx.')
        return redirect('stock:detail-inventaire', pk=pk)

    try:
        wb = openpyxl.load_workbook(fichier, data_only=True)
        ws = wb.active
        res = importer_lignes_inventaire_excel(
            ws,
            entreprise_id=entreprise.pk,
            inventaire=inv,
            depot_cible=depot_cible,
            pv_stock=pv_stock,
        )
    except Exception as exc:
        messages.error(request, f'Lecture du fichier impossible : {exc}')
        return redirect('stock:detail-inventaire', pk=pk)

    if res.applied:
        messages.success(
            request,
            f'{res.applied} produit(s) : ligne(s) enregistrée(s) ou mise(s) à jour.',
        )
    elif not res.errors:
        messages.warning(request, 'Aucune ligne enregistrée.')

    for msg in res.errors[:35]:
        messages.warning(request, msg)
    if len(res.errors) > 35:
        messages.warning(
            request,
            f'… et {len(res.errors) - 35} autre(s) avertissement(s).',
        )
    if not res.applied and res.errors:
        messages.error(
            request,
            'Aucune ligne enregistrée : vérifiez les en-têtes (SKU ou code-barres, Qté physique) et les références produit.',
        )

    return redirect('stock:detail-inventaire', pk=pk)


@login_requis
@require_POST
def inventaire_supprimer_ligne(request, pk, ligne_pk):
    inv, redir = _charger_inventaire(request, pk)
    if redir:
        return redir
    if inv.cloture:
        messages.error(request, 'Inventaire clôturé.')
        return redirect('stock:detail-inventaire', pk=pk)

    ligne = get_object_or_404(LigneInventaire, pk=ligne_pk, inventaire_id=pk)
    ligne.delete()
    messages.success(request, 'Ligne supprimée.')
    return redirect('stock:detail-inventaire', pk=pk)


@login_requis
@require_POST
def inventaire_cloturer(request, pk):
    inv, redir = _charger_inventaire(request, pk)
    if redir:
        return redir

    admin = utilisateur_est_admin(request.user)
    depot_cible = inv.depot or (
        inv.pointdevente.depot_source if inv.pointdevente else None
    )

    ok = False
    if inv.pointdevente_id:
        ok = peut_modifier_stock_au_point_vente(request.user, inv.pointdevente, admin)
    else:
        ok = peut_modifier_stock_au_depot(request.user, depot_cible, admin)
    if not ok:
        messages.error(request, 'Clôture refusée (droits).')
        return redirect('stock:detail-inventaire', pk=pk)

    if not inv.lignes.exists():
        messages.error(request, 'Ajoutez au moins une ligne avant clôture.')
        return redirect('stock:detail-inventaire', pk=pk)

    try:
        aug, dim = appliquer_ecarts_inventaire(inv, request.user)
        from finance.posting import poster_variation_pure_ohada
        from datetime import date

        ref = (inv.lot or '')[:40] or f'INV-{inv.pk}'
        ent_compta = depot_cible.branche.entreprise
        try:
            if aug > 0:
                poster_variation_pure_ohada(
                    ent_compta,
                    aug,
                    True,
                    ref[:50],
                    inv.date_inventaire,
                    f"Inventaire {ref} (+)",
                    request.user,
                )
            if dim > 0:
                poster_variation_pure_ohada(
                    ent_compta,
                    dim,
                    False,
                    ref[:50],
                    inv.date_inventaire,
                    f"Inventaire {ref} (−)",
                    request.user,
                )
        except Exception as exc:
            messages.warning(request, f'Comptabilité : {exc}')
        messages.success(request, 'Inventaire clôturé et stock mis à jour.')
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect('stock:detail-inventaire', pk=pk)
