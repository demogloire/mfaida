"""Vues rapports — permissions, filtre branche/entreprise, export PDF."""

import calendar
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import (
    Count, DecimalField, ExpressionWrapper, F, Q, Sum, Value,
)
from django.db.models.functions import Coalesce, TruncMonth
from django.http import HttpResponseForbidden
from django.shortcuts import render
from django.utils import timezone

from achat.models import OrdreAchat
from caisse.models import SessionCaisse, TransactionCaisse
from depenses.models import Depense
from entreprise.models import Branche, Entreprise
from facturation.models import Facture, LigneFacture, RetourVente
from rh.models import AvanceSalaire, BulletinPaie, Employe, Presence
from stock.access import (
    get_entreprise_utilisateur,
    queryset_points_vente_visibles,
    utilisateur_est_admin,
)
from stock.models import MouvementStock, Stock
from utilisateur.acces_metier import utilisateur_peut_permission
from utilisateur.decorators import login_requis


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _check_perm(request, code):
    """Retourne None si autorisé, HttpResponseForbidden sinon."""
    if not utilisateur_peut_permission(request.user, code):
        return HttpResponseForbidden("Accès refusé — permission manquante : " + code)
    return None


def _scope(request):
    """
    Retourne (entreprise, admin, pdvs, branches_dispo, branche_choisie).
    Les admins peuvent filtrer par branche via GET ?branche_id=X.
    """
    entreprise  = get_entreprise_utilisateur(request.user)
    admin       = utilisateur_est_admin(request.user)
    pdvs_all    = queryset_points_vente_visibles(request.user, entreprise, admin)

    branches_dispo = []
    branche_choisie = None

    if admin and entreprise:
        branches_dispo = list(entreprise.branches.filter(est_actif=True).order_by('nom'))
        branche_id = request.GET.get('branche_id', '')
        if branche_id:
            try:
                branche_choisie = Branche.objects.get(pk=int(branche_id), entreprise=entreprise)
                pdvs_all = pdvs_all.filter(branche=branche_choisie)
            except (ValueError, Branche.DoesNotExist):
                pass
    elif not admin:
        branche = getattr(request.user, 'branche', None)
        if branche:
            branche_choisie = branche

    return entreprise, admin, pdvs_all, branches_dispo, branche_choisie


def _periode(request):
    today     = date.today()
    debut_str = request.GET.get('debut', '')
    fin_str   = request.GET.get('fin',   '')
    try:
        debut = date.fromisoformat(debut_str)
    except ValueError:
        debut = today.replace(day=1)
    try:
        fin = date.fromisoformat(fin_str)
    except ValueError:
        last_day = calendar.monthrange(today.year, today.month)[1]
        fin = today.replace(day=last_day)
    return debut, fin


def _is_pdf(request):
    return request.GET.get('format') == 'pdf'


def _ctx_commun(request, entreprise, admin, branches_dispo, branche_choisie):
    """Contexte partagé par tous les rapports (utilisé dans les templates)."""
    return {
        'branches_dispo':   branches_dispo,
        'branche_choisie':  branche_choisie,
        'est_admin':        admin,
        'entreprise':       entreprise,
        'can_export_pdf':   utilisateur_peut_permission(request.user, 'rapports_export_pdf'),
        'now':              timezone.now(),
    }


def _render(request, template_base, context):
    """Rend la version normale ou la version PDF selon le paramètre `format`."""
    if _is_pdf(request):
        template = template_base.replace('.html', '_pdf.html')
        return render(request, template, context)
    return render(request, template_base, context)


# ─────────────────────────────────────────────────────────────────────────────
# Hub
# ─────────────────────────────────────────────────────────────────────────────

@login_requis
def hub_rapports(request):
    denied = _check_perm(request, 'acces_module_rapports')
    if denied:
        return denied
    user = request.user
    return render(request, 'rapports/hub.html', {
        'can_ventes':  utilisateur_peut_permission(user, 'rapports_ventes'),
        'can_stock':   utilisateur_peut_permission(user, 'rapports_stock'),
        'can_rh':      utilisateur_peut_permission(user, 'rapports_rh'),
        'can_finance': utilisateur_peut_permission(user, 'rapports_finance'),
        'can_tiers':   utilisateur_peut_permission(user, 'rapports_tiers'),
        'can_achats':  utilisateur_peut_permission(user, 'rapports_achats'),
    })


# ─────────────────────────────────────────────────────────────────────────────
# Ventes & Facturation
# ─────────────────────────────────────────────────────────────────────────────

@login_requis
def rapport_ventes(request):
    denied = _check_perm(request, 'rapports_ventes')
    if denied:
        return denied
    entreprise, admin, pdvs, branches_dispo, branche_choisie = _scope(request)
    debut, fin = _periode(request)

    qs = Facture.objects.filter(
        point_vente__in=pdvs, statut='VALIDEE',
        date_facture__date__range=(debut, fin),
    )
    synthese = qs.aggregate(
        total_ht    = Coalesce(Sum('total_ht'),     Value(0), output_field=DecimalField()),
        total_tva   = Coalesce(Sum('total_tva'),    Value(0), output_field=DecimalField()),
        total_ttc   = Coalesce(Sum('total_ttc'),    Value(0), output_field=DecimalField()),
        total_paye  = Coalesce(Sum('montant_paye'), Value(0), output_field=DecimalField()),
        total_du    = Coalesce(Sum('reste_a_payer'),Value(0), output_field=DecimalField()),
        nb_factures = Count('id'),
    )
    mensuel = (
        qs.annotate(mois=TruncMonth('date_facture'))
          .values('mois')
          .annotate(
              ca   = Coalesce(Sum('total_ttc'),     Value(0), output_field=DecimalField()),
              paye = Coalesce(Sum('montant_paye'),  Value(0), output_field=DecimalField()),
              nb   = Count('id'),
          ).order_by('mois')
    )
    par_pdv = (
        qs.values('point_vente__nom')
          .annotate(ca=Coalesce(Sum('total_ttc'), Value(0), output_field=DecimalField()), nb=Count('id'))
          .order_by('-ca')
    )

    ctx = {
        'debut': debut, 'fin': fin,
        'synthese': synthese, 'mensuel': mensuel, 'par_pdv': par_pdv,
        **_ctx_commun(request, entreprise, admin, branches_dispo, branche_choisie),
    }
    return _render(request, 'rapports/ventes/ca.html', ctx)


@login_requis
def rapport_benefice(request):
    denied = _check_perm(request, 'rapports_ventes')
    if denied:
        return denied
    entreprise, admin, pdvs, branches_dispo, branche_choisie = _scope(request)
    debut, fin = _periode(request)

    lignes = LigneFacture.objects.filter(
        facture__point_vente__in=pdvs, facture__statut='VALIDEE',
        facture__date_facture__date__range=(debut, fin),
    ).select_related('mouvement_stock', 'facture__point_vente')

    ca_total = cout_total = Decimal('0')
    for l in lignes:
        ca_total   += Decimal(str(l.quantite)) * Decimal(str(l.prix_unitaire_ht)) - Decimal(str(l.remise or 0))
        cout_total += Decimal(str(l.quantite)) * Decimal(str(l.mouvement_stock.prix_unitaire or 0))

    benefice_brut = ca_total - cout_total
    marge_brute   = (benefice_brut / ca_total * 100) if ca_total else Decimal('0')

    depenses_total = Depense.objects.filter(
        point_vente__in=pdvs, statut='VALIDEE',
        date_depense__date__range=(debut, fin),
    ).aggregate(t=Coalesce(Sum('montant'), Value(0), output_field=DecimalField()))['t']

    # Masse salariale payée sur branches visibles
    branches_ids = pdvs.values_list('branche_id', flat=True).distinct()
    bulletins_masse = BulletinPaie.objects.filter(
        employe__branche_id__in=branches_ids,
        statut='PAYE',
        date_paiement__date__range=(debut, fin),
    ).aggregate(t=Coalesce(Sum('salaire_net'), Value(0), output_field=DecimalField()))['t']

    benefice_net = benefice_brut - depenses_total - bulletins_masse
    marge_nette  = (benefice_net / ca_total * 100) if ca_total else Decimal('0')

    # Détail par PDV
    pdv_map = {}
    for l in lignes:
        pk   = l.facture.point_vente_id
        name = l.facture.point_vente.nom
        ca_l = Decimal(str(l.quantite)) * Decimal(str(l.prix_unitaire_ht)) - Decimal(str(l.remise or 0))
        cou  = Decimal(str(l.quantite)) * Decimal(str(l.mouvement_stock.prix_unitaire or 0))
        if pk not in pdv_map:
            pdv_map[pk] = {'nom': name, 'ca': Decimal('0'), 'cout': Decimal('0')}
        pdv_map[pk]['ca']   += ca_l
        pdv_map[pk]['cout'] += cou
    par_pdv = []
    for d in pdv_map.values():
        if d['ca'] or d['cout']:
            brut = d['ca'] - d['cout']
            par_pdv.append({**d, 'brut': brut,
                            'marge': (brut / d['ca'] * 100) if d['ca'] else Decimal('0')})
    par_pdv.sort(key=lambda x: x['brut'], reverse=True)

    ctx = {
        'debut': debut, 'fin': fin,
        'ca_total': ca_total, 'cout_total': cout_total,
        'benefice_brut': benefice_brut, 'marge_brute': marge_brute,
        'depenses_total': depenses_total, 'bulletins': bulletins_masse,
        'benefice_net': benefice_net, 'marge_nette': marge_nette,
        'par_pdv': par_pdv,
        **_ctx_commun(request, entreprise, admin, branches_dispo, branche_choisie),
    }
    return _render(request, 'rapports/ventes/benefice.html', ctx)


@login_requis
def rapport_produits_vendus(request):
    denied = _check_perm(request, 'rapports_ventes')
    if denied:
        return denied
    entreprise, admin, pdvs, branches_dispo, branche_choisie = _scope(request)
    debut, fin = _periode(request)

    lignes = (
        LigneFacture.objects.filter(
            facture__point_vente__in=pdvs, facture__statut='VALIDEE',
            facture__date_facture__date__range=(debut, fin),
        )
        .values('produit__nom', 'produit__sous_categorie__nom')
        .annotate(
            qte_vendue = Sum('quantite'),
            ca_ht      = Coalesce(Sum(
                ExpressionWrapper(F('quantite') * F('prix_unitaire_ht') - F('remise'),
                                  output_field=DecimalField())
            ), Value(0), output_field=DecimalField()),
        ).order_by('-ca_ht')
    )
    ctx = {
        'debut': debut, 'fin': fin, 'lignes': lignes,
        **_ctx_commun(request, entreprise, admin, branches_dispo, branche_choisie),
    }
    return _render(request, 'rapports/ventes/produits.html', ctx)


@login_requis
def rapport_creances(request):
    denied = _check_perm(request, 'rapports_ventes')
    if denied:
        return denied
    entreprise, admin, pdvs, branches_dispo, branche_choisie = _scope(request)

    qs = Facture.objects.filter(
        point_vente__in=pdvs, statut='VALIDEE', reste_a_payer__gt=0,
    ).select_related('client', 'point_vente').order_by('date_facture')

    today = date.today()
    tranches = {'0_30': [], '31_60': [], '61_90': [], 'plus_90': []}
    for f in qs:
        age = (today - f.date_facture.date()).days
        if age <= 30:
            tranches['0_30'].append(f)
        elif age <= 60:
            tranches['31_60'].append(f)
        elif age <= 90:
            tranches['61_90'].append(f)
        else:
            tranches['plus_90'].append(f)

    ctx = {
        'qs': qs, 'tranches': tranches,
        'total_du': sum(f.reste_a_payer for f in qs), 'today': today,
        **_ctx_commun(request, entreprise, admin, branches_dispo, branche_choisie),
    }
    return _render(request, 'rapports/ventes/creances.html', ctx)


@login_requis
def rapport_retours_vente(request):
    denied = _check_perm(request, 'rapports_ventes')
    if denied:
        return denied
    entreprise, admin, pdvs, branches_dispo, branche_choisie = _scope(request)
    debut, fin = _periode(request)

    qs = RetourVente.objects.filter(
        point_vente__in=pdvs,
        date_retour__date__range=(debut, fin),
    ).select_related('facture_origine__client', 'point_vente').order_by('-date_retour')

    ctx = {
        'debut': debut, 'fin': fin, 'qs': qs,
        'total_retourne': qs.aggregate(
            t=Coalesce(Sum('total_ttc'), Value(0), output_field=DecimalField()))['t'],
        **_ctx_commun(request, entreprise, admin, branches_dispo, branche_choisie),
    }
    return _render(request, 'rapports/ventes/retours.html', ctx)


# ─────────────────────────────────────────────────────────────────────────────
# Achats
# ─────────────────────────────────────────────────────────────────────────────

@login_requis
def rapport_achats(request):
    denied = _check_perm(request, 'rapports_achats')
    if denied:
        return denied
    entreprise, admin, pdvs, branches_dispo, branche_choisie = _scope(request)
    debut, fin = _periode(request)

    qs_all = OrdreAchat.objects.filter(entreprise=entreprise) if entreprise else OrdreAchat.objects.none()
    if branche_choisie:
        qs_all = qs_all.filter(
            Q(depot_destination__branche=branche_choisie) |
            Q(pointdevente_destination__branche=branche_choisie)
        )

    qs_periode = qs_all.filter(date_commande__date__range=(debut, fin)).exclude(statut='ANNULE')

    ctx = {
        'debut': debut, 'fin': fin,
        'par_fournisseur': qs_periode.values('fournisseur__nom_societe').annotate(
            nb=Count('id'),
            total_ttc=Coalesce(Sum('total_ttc'), Value(0), output_field=DecimalField()),
        ).order_by('-total_ttc'),
        'en_cours': qs_all.filter(statut__in=['ENVOYE', 'RECU_PARTIEL']).select_related('fournisseur').order_by('date_livraison_prevue'),
        'synthese': qs_periode.aggregate(
            nb_total=Count('id'),
            total_ttc=Coalesce(Sum('total_ttc'), Value(0), output_field=DecimalField()),
        ),
        **_ctx_commun(request, entreprise, admin, branches_dispo, branche_choisie),
    }
    return _render(request, 'rapports/achats/index.html', ctx)


# ─────────────────────────────────────────────────────────────────────────────
# Stock
# ─────────────────────────────────────────────────────────────────────────────

@login_requis
def rapport_inventaire(request):
    denied = _check_perm(request, 'rapports_stock')
    if denied:
        return denied
    entreprise, admin, pdvs, branches_dispo, branche_choisie = _scope(request)
    pdv_id = request.GET.get('pdv', '')

    qs = Stock.objects.filter(pointdevente__in=pdvs).select_related('produit__categorie', 'pointdevente')
    if pdv_id:
        qs = qs.filter(pointdevente_id=pdv_id)

    items = []
    valeur_totale = Decimal('0')
    for s in qs.order_by('produit__nom'):
        mv = MouvementStock.objects.filter(produit=s.produit, pointvente=s.pointdevente).order_by('-id').first()
        cout_u = mv.prix_unitaire if mv else Decimal('0')
        valeur = s.quantite_reelle * cout_u
        valeur_totale += valeur
        items.append({'produit': s.produit.nom, 'categorie': s.produit.sous_categorie.nom if s.produit.sous_categorie else '—',
                      'pdv': s.pointdevente.nom if s.pointdevente else '—',
                      'qte': s.quantite_reelle, 'cout_u': cout_u, 'valeur': valeur})

    ctx = {
        'items': items, 'valeur_totale': valeur_totale,
        'pdvs_list': list(pdvs.values('id', 'nom')), 'pdv_filtre': pdv_id,
        **_ctx_commun(request, entreprise, admin, branches_dispo, branche_choisie),
    }
    return _render(request, 'rapports/stock/inventaire.html', ctx)


@login_requis
def rapport_mouvements_stock(request):
    denied = _check_perm(request, 'rapports_stock')
    if denied:
        return denied
    entreprise, admin, pdvs, branches_dispo, branche_choisie = _scope(request)
    debut, fin = _periode(request)

    qs = MouvementStock.objects.filter(pointvente__in=pdvs).select_related('produit', 'pointvente').order_by('-id')[:500]

    ctx = {
        'debut': debut, 'fin': fin, 'qs': qs,
        **_ctx_commun(request, entreprise, admin, branches_dispo, branche_choisie),
    }
    return _render(request, 'rapports/stock/mouvements.html', ctx)


@login_requis
def rapport_ruptures(request):
    denied = _check_perm(request, 'rapports_stock')
    if denied:
        return denied
    entreprise, admin, pdvs, branches_dispo, branche_choisie = _scope(request)

    qs = Stock.objects.filter(pointdevente__in=pdvs).select_related('produit__sous_categorie', 'pointdevente').order_by('quantite_reelle')
    critique = [s for s in qs if s.quantite_reelle <= 0]
    faible   = [s for s in qs if 0 < s.quantite_reelle <= (s.produit.stock_alerte or 0)]

    ctx = {
        'critique': critique, 'faible': faible,
        **_ctx_commun(request, entreprise, admin, branches_dispo, branche_choisie),
    }
    return _render(request, 'rapports/stock/ruptures.html', ctx)


@login_requis
def rapport_expirations(request):
    denied = _check_perm(request, 'rapports_stock')
    if denied:
        return denied
    entreprise, admin, pdvs, branches_dispo, branche_choisie = _scope(request)
    jours  = int(request.GET.get('jours', 30))
    limite = date.today() + timedelta(days=jours)

    qs = MouvementStock.objects.filter(
        pointvente__in=pdvs,
        dateexpiration__isnull=False, dateexpiration__lte=limite,
        quantite_active__gt=0,
    ).select_related('produit', 'pointvente').order_by('dateexpiration')

    ctx = {
        'qs': qs, 'jours': jours, 'limite': limite,
        **_ctx_commun(request, entreprise, admin, branches_dispo, branche_choisie),
    }
    return _render(request, 'rapports/stock/expirations.html', ctx)


# ─────────────────────────────────────────────────────────────────────────────
# RH
# ─────────────────────────────────────────────────────────────────────────────

def _scope_employes_rh(request, entreprise, admin, branche_choisie):
    qs = Employe.objects.filter(est_actif=True)
    if admin:
        if branche_choisie:
            qs = qs.filter(branche=branche_choisie)
        elif entreprise:
            qs = qs.filter(branche__entreprise=entreprise)
        else:
            qs = Employe.objects.none()
    else:
        branche = getattr(request.user, 'branche', None)
        qs = qs.filter(branche=branche) if branche else Employe.objects.none()
    return qs


@login_requis
def rapport_presences_rh(request):
    denied = _check_perm(request, 'rapports_rh')
    if denied:
        return denied
    entreprise, admin, pdvs, branches_dispo, branche_choisie = _scope(request)
    today = date.today()
    mois  = int(request.GET.get('mois',  today.month))
    annee = int(request.GET.get('annee', today.year))

    employes = _scope_employes_rh(request, entreprise, admin, branche_choisie)
    _, nb_j = calendar.monthrange(annee, mois)
    debut_m, fin_m = date(annee, mois, 1), date(annee, mois, nb_j)

    presences_qs = Presence.objects.filter(employe__in=employes, date__range=(debut_m, fin_m))
    stats = []
    for emp in employes:
        p = presences_qs.filter(employe=emp)
        stats.append({'employe': emp,
                      'present': p.filter(statut='PRESENT').count(),
                      'retard':  p.filter(statut='RETARD').count(),
                      'absent':  p.filter(statut='ABSENT').count(),
                      'conge':   p.filter(statut='CONGE').count(),
                      'total':   p.count()})

    ctx = {
        'stats': stats,
        'synthese': presences_qs.aggregate(
            nb_present=Count('id', filter=Q(statut='PRESENT')),
            nb_absent =Count('id', filter=Q(statut='ABSENT')),
            nb_retard =Count('id', filter=Q(statut='RETARD')),
            nb_conge  =Count('id', filter=Q(statut='CONGE')),
        ),
        'mois': mois, 'annee': annee,
        'mois_liste': [{'num': i, 'nom': calendar.month_name[i]} for i in range(1, 13)],
        'annees': range(today.year - 2, today.year + 1),
        **_ctx_commun(request, entreprise, admin, branches_dispo, branche_choisie),
    }
    return _render(request, 'rapports/rh/presences.html', ctx)


@login_requis
def rapport_masse_salariale(request):
    denied = _check_perm(request, 'rapports_rh')
    if denied:
        return denied
    entreprise, admin, pdvs, branches_dispo, branche_choisie = _scope(request)
    debut, fin = _periode(request)

    employes = _scope_employes_rh(request, entreprise, admin, branche_choisie)
    bulletins_all = list(BulletinPaie.objects.filter(employe__in=employes).select_related('employe__branche', 'devise'))
    bulletins_periode = [b for b in bulletins_all if debut <= date(b.periode_annee, b.periode_mois, 1) <= fin]

    total_brut     = sum(b.salaire_brut for b in bulletins_periode)
    total_net      = sum(b.salaire_net  for b in bulletins_periode)
    total_retenues = sum(b.retenues + b.retenues_avances for b in bulletins_periode)

    mensuel = {}
    for b in bulletins_periode:
        key = (b.periode_annee, b.periode_mois)
        if key not in mensuel:
            mensuel[key] = {'brut': Decimal('0'), 'net': Decimal('0'), 'nb': 0}
        mensuel[key]['brut'] += b.salaire_brut
        mensuel[key]['net']  += b.salaire_net
        mensuel[key]['nb']   += 1

    ctx = {
        'debut': debut, 'fin': fin,
        'bulletins': bulletins_periode,
        'total_brut': total_brut, 'total_net': total_net, 'total_retenues': total_retenues,
        'bulletins_payes': len([b for b in bulletins_periode if b.statut == 'PAYE']),
        'mensuel': sorted(mensuel.items()),
        **_ctx_commun(request, entreprise, admin, branches_dispo, branche_choisie),
    }
    return _render(request, 'rapports/rh/masse_salariale.html', ctx)


@login_requis
def rapport_avances_rh(request):
    denied = _check_perm(request, 'rapports_rh')
    if denied:
        return denied
    entreprise, admin, pdvs, branches_dispo, branche_choisie = _scope(request)
    debut, fin = _periode(request)

    employes = _scope_employes_rh(request, entreprise, admin, branche_choisie)
    qs = AvanceSalaire.objects.filter(employe__in=employes, date_demande__date__range=(debut, fin)).select_related('employe', 'devise').order_by('-date_demande')

    total_decaisse  = qs.filter(statut__in=['DECAISSEE', 'REMBOURSEE']).aggregate(t=Coalesce(Sum('montant'), Value(0), output_field=DecimalField()))['t']
    total_rembourse = qs.filter(statut='REMBOURSEE').aggregate(t=Coalesce(Sum('montant'), Value(0), output_field=DecimalField()))['t']

    ctx = {
        'debut': debut, 'fin': fin, 'qs': qs,
        'synthese': qs.aggregate(
            total_demande  = Coalesce(Sum('montant'), Value(0), output_field=DecimalField()),
            nb_approuvees  = Count('id', filter=Q(statut='APPROUVEE')),
            nb_decaissees  = Count('id', filter=Q(statut='DECAISSEE')),
            nb_remboursees = Count('id', filter=Q(statut='REMBOURSEE')),
        ),
        'total_decaisse': total_decaisse,
        'total_rembourse': total_rembourse,
        'solde_restant': total_decaisse - total_rembourse,
        **_ctx_commun(request, entreprise, admin, branches_dispo, branche_choisie),
    }
    return _render(request, 'rapports/rh/avances.html', ctx)


# ─────────────────────────────────────────────────────────────────────────────
# Caisse
# ─────────────────────────────────────────────────────────────────────────────

@login_requis
def rapport_caisse(request):
    denied = _check_perm(request, 'rapports_finance')
    if denied:
        return denied
    entreprise, admin, pdvs, branches_dispo, branche_choisie = _scope(request)
    debut, fin = _periode(request)

    sessions = SessionCaisse.objects.filter(
        point_vente__in=pdvs, date_ouverture__date__range=(debut, fin),
    ).select_related('point_vente', 'ouvert_par').order_by('-date_ouverture')

    txns = TransactionCaisse.objects.filter(
        session__point_vente__in=pdvs, date_transaction__date__range=(debut, fin),
    )
    synthese = txns.aggregate(
        total_encaissements = Coalesce(Sum('montant', filter=Q(type_transaction='ENCAISSEMENT')), Value(0), output_field=DecimalField()),
        total_decaissements = Coalesce(Sum('montant', filter=Q(type_transaction='DECAISSEMENT')), Value(0), output_field=DecimalField()),
        total_depots        = Coalesce(Sum('montant', filter=Q(type_transaction='DEPOT')),        Value(0), output_field=DecimalField()),
        total_retraits      = Coalesce(Sum('montant', filter=Q(type_transaction='RETRAIT')),      Value(0), output_field=DecimalField()),
    )
    par_mode = txns.filter(type_transaction='ENCAISSEMENT').values('mode_paiement').annotate(
        total=Coalesce(Sum('montant'), Value(0), output_field=DecimalField())
    ).order_by('-total')

    ctx = {
        'debut': debut, 'fin': fin,
        'sessions': sessions, 'synthese': synthese, 'par_mode': par_mode,
        'nb_sessions': sessions.count(),
        **_ctx_commun(request, entreprise, admin, branches_dispo, branche_choisie),
    }
    return _render(request, 'rapports/caisse/index.html', ctx)


# ─────────────────────────────────────────────────────────────────────────────
# Dépenses
# ─────────────────────────────────────────────────────────────────────────────

@login_requis
def rapport_depenses(request):
    denied = _check_perm(request, 'rapports_finance')
    if denied:
        return denied
    entreprise, admin, pdvs, branches_dispo, branche_choisie = _scope(request)
    debut, fin = _periode(request)

    qs = Depense.objects.filter(
        point_vente__in=pdvs, statut='VALIDEE',
        date_depense__date__range=(debut, fin),
    ).select_related('point_vente', 'categorie')

    ctx = {
        'debut': debut, 'fin': fin,
        'total': qs.aggregate(t=Coalesce(Sum('montant'), Value(0), output_field=DecimalField()))['t'],
        'par_type':       qs.values('type_depense').annotate(total=Coalesce(Sum('montant'), Value(0), output_field=DecimalField()), nb=Count('id')).order_by('-total'),
        'par_categorie':  qs.filter(categorie__isnull=False).values('categorie__nom', 'categorie__couleur').annotate(total=Coalesce(Sum('montant'), Value(0), output_field=DecimalField()), nb=Count('id')).order_by('-total'),
        'par_pdv':        qs.values('point_vente__nom').annotate(total=Coalesce(Sum('montant'), Value(0), output_field=DecimalField()), nb=Count('id')).order_by('-total'),
        'mensuel':        qs.annotate(mois=TruncMonth('date_depense')).values('mois').annotate(total=Coalesce(Sum('montant'), Value(0), output_field=DecimalField())).order_by('mois'),
        'detail':         qs.order_by('-date_depense')[:200],
        **_ctx_commun(request, entreprise, admin, branches_dispo, branche_choisie),
    }
    return _render(request, 'rapports/depenses/index.html', ctx)


# ─────────────────────────────────────────────────────────────────────────────
# Tiers
# ─────────────────────────────────────────────────────────────────────────────

@login_requis
def rapport_clients(request):
    denied = _check_perm(request, 'rapports_tiers')
    if denied:
        return denied
    entreprise, admin, pdvs, branches_dispo, branche_choisie = _scope(request)
    debut, fin = _periode(request)

    qs = Facture.objects.filter(point_vente__in=pdvs, statut='VALIDEE', date_facture__date__range=(debut, fin))
    par_client = qs.values('client__nom', 'client__id', 'client__telephone').annotate(
        ca=Coalesce(Sum('total_ttc'), Value(0), output_field=DecimalField()),
        paye=Coalesce(Sum('montant_paye'), Value(0), output_field=DecimalField()),
        du=Coalesce(Sum('reste_a_payer'), Value(0), output_field=DecimalField()),
        nb_fact=Count('id'),
    ).order_by('-ca')[:50]

    ctx = {
        'debut': debut, 'fin': fin,
        'par_client': par_client,
        'synthese': qs.aggregate(
            nb_clients=Count('client', distinct=True),
            ca_total=Coalesce(Sum('total_ttc'), Value(0), output_field=DecimalField()),
            paye_total=Coalesce(Sum('montant_paye'), Value(0), output_field=DecimalField()),
            du_total=Coalesce(Sum('reste_a_payer'), Value(0), output_field=DecimalField()),
        ),
        **_ctx_commun(request, entreprise, admin, branches_dispo, branche_choisie),
    }
    return _render(request, 'rapports/tiers/clients.html', ctx)


@login_requis
def rapport_vieillissement(request):
    denied = _check_perm(request, 'rapports_tiers')
    if denied:
        return denied
    entreprise, admin, pdvs, branches_dispo, branche_choisie = _scope(request)

    qs = Facture.objects.filter(point_vente__in=pdvs, statut='VALIDEE', reste_a_payer__gt=0).select_related('client').order_by('-reste_a_payer')

    today = date.today()
    t0_30 = t31_60 = t61_90 = tplus90 = Decimal('0')
    rows = []
    for f in qs:
        age = (today - f.date_facture.date()).days
        if   age <= 30:  t0_30   += f.reste_a_payer; tranche = '0–30 j'
        elif age <= 60:  t31_60  += f.reste_a_payer; tranche = '31–60 j'
        elif age <= 90:  t61_90  += f.reste_a_payer; tranche = '61–90 j'
        else:            tplus90 += f.reste_a_payer; tranche = '+90 j'
        rows.append({'facture': f, 'age': age, 'tranche': tranche})

    ctx = {
        'rows': rows, 'today': today,
        't0_30': t0_30, 't31_60': t31_60, 't61_90': t61_90, 'tplus90': tplus90,
        'total_du': t0_30 + t31_60 + t61_90 + tplus90,
        **_ctx_commun(request, entreprise, admin, branches_dispo, branche_choisie),
    }
    return _render(request, 'rapports/tiers/vieillissement.html', ctx)
