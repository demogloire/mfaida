"""Vues facturation — brouillon, lignes sur mouvements stock, validation avec déstockage."""

import json
from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from utilisateur.decorators import login_requis

from entreprise.models import Devise, PointVente
from stock.access import get_entreprise_utilisateur, utilisateur_est_admin, queryset_points_vente_visibles
from stock.services import (
    consommer_mouvements_facture,
    repartir_quantite_facture_sur_lots,
    verifier_quantites_lignes_facture,
)
from tiers.models import Client

from .forms import (
    AjoutLigneFactureForm,
    ClientRapideFactureForm,
    FactureBrouillonForm,
    label_client_facture,
    label_produit_facture,
    point_vente_nouvelle_facture_queryset,
    queryset_produits_facture_pv,
)
from .models import Facture, LigneFacture
from .pricing import montant_tva_sur_ht, taux_tva_actif


def _dispo_produits_pour_facture_brouillon(point_vente, facture, produit_ids):
    """
    Par produit : somme ``quantite_active`` des lots **sur ce point de vente uniquement**
    (dépôt source + ``pointvente_id`` = ce PV), moins les quantités déjà sur la facture **pour
    des lignes dont le lot est sur ce même périmètre**. Les lignes ou lots hors PDV ne sont pas
    mélangés au calcul (évite un disponible affiché incohérent avec le tableau des lignes).
    """
    ids = list(produit_ids)
    if not ids:
        return {}

    from stock.access import mouvements_disponibles_pour_point_vente

    if not point_vente or not point_vente.depot_source_id:
        z = Decimal('0')
        return {
            str(pk): {
                'stock_lots_total': z,
                'deja_sur_facture': z,
                'disponible_ajout': z,
            }
            for pk in ids
        }

    ds_id = point_vente.depot_source_id
    pv_pk = point_vente.pk

    brut_q = (
        mouvements_disponibles_pour_point_vente(point_vente)
        .filter(produit_id__in=ids)
        .values('produit_id')
        .annotate(total=Sum('quantite_active'))
    )
    brut = {str(r['produit_id']): r['total'] for r in brut_q}

    enc_q = (
        LigneFacture.objects.filter(facture=facture, produit_id__in=ids)
        .filter(
            mouvement_stock__depot_id=ds_id,
            mouvement_stock__pointvente_id=pv_pk,
        )
        .values('produit_id')
        .annotate(total=Sum('quantite'))
    )
    enc = {str(r['produit_id']): r['total'] for r in enc_q}

    out = {}
    for pk in ids:
        sid = str(pk)
        b = brut.get(sid)
        b = Decimal(str(b)) if b is not None else Decimal('0')
        e = enc.get(sid)
        e = Decimal(str(e)) if e is not None else Decimal('0')
        d = b - e
        if d < 0:
            d = Decimal('0')
        out[sid] = {
            'stock_lots_total': b,
            'deja_sur_facture': e,
            'disponible_ajout': d,
        }
    return out


def _peut_vendre_sur_pv(user, pv, admin):
    if admin or user.is_superuser:
        return True
    return user.a_acces_point_vente(pv.pk, 'peut_vendre')


def _peut_gerer_caisse_sur_pv(user, pv, admin):
    """Caissier : droit « Gérer la caisse » sur le point de vente."""
    if admin or user.is_superuser:
        return True
    return user.a_acces_point_vente(pv.pk, 'peut_gerer_caisse')


def _peut_consulter_facture_sur_pv(user, pv, admin):
    """Voir une facture : vendeur OU caisse sur ce PV."""
    if admin or user.is_superuser:
        return True
    return user.a_acces_point_vente(pv.pk, 'peut_vendre') or user.a_acces_point_vente(
        pv.pk, 'peut_gerer_caisse'
    )


def _devises_taux_json(entreprise):
    """Carte devise_id → str(taux) pour refléter le taux lu seule après changement de devise."""
    if entreprise:
        rows = Devise.objects.filter(entreprise=entreprise).values_list('pk', 'taux_echange')
    else:
        rows = Devise.objects.values_list('pk', 'taux_echange')
    return json.dumps({str(pk): str(taux) if taux is not None else '1.0' for pk, taux in rows})


def _liste_factures_scope(user, entreprise, admin):
    qs = Facture.objects.select_related(
        'point_vente', 'client', 'devise', 'vendeur'
    ).order_by('-date_facture')
    if admin:
        if entreprise:
            return qs.filter(point_vente__branche__entreprise=entreprise)
        return qs
    if not entreprise:
        return Facture.objects.none()
    pv_ids = list(
        user.acces_points_vente.filter(peut_voir=True).values_list('point_vente_id', flat=True)
    )
    if not pv_ids:
        return Facture.objects.none()
    return qs.filter(
        point_vente__branche__entreprise=entreprise,
        point_vente_id__in=pv_ids,
    )


def _charger_facture(request, pk):
    entreprise = get_entreprise_utilisateur(request.user)
    admin = utilisateur_est_admin(request.user)
    fact = get_object_or_404(
        _liste_factures_scope(request.user, entreprise, admin).select_related(
            'point_vente',
            'point_vente__branche',
            'point_vente__branche__entreprise',
            'client',
            'devise',
            'vendeur',
        ),
        pk=pk,
    )
    if not _peut_consulter_facture_sur_pv(request.user, fact.point_vente, admin):
        return None, redirect('facturation:liste-factures')
    return fact, None


@login_requis
def liste_factures(request):
    entreprise = get_entreprise_utilisateur(request.user)
    admin = utilisateur_est_admin(request.user)
    qs = _liste_factures_scope(request.user, entreprise, admin)

    if admin and entreprise:
        points_vente = PointVente.objects.filter(
            branche__entreprise=entreprise, est_actif=True
        ).order_by('nom')
    elif admin:
        points_vente = PointVente.objects.filter(est_actif=True).order_by(
            'branche_id', 'nom'
        )
    else:
        points_vente = queryset_points_vente_visibles(request.user, entreprise, admin)

    statuts_ok = {c[0] for c in Facture.STATUTS_FACTURE}
    modes_ok = {c[0] for c in Facture.MODES_PAIEMENT}
    statut_f = (request.GET.get('statut') or '').strip()
    mode_f = (request.GET.get('mode_paiement') or '').strip()
    pv_raw = (request.GET.get('point_vente') or '').strip()
    q_f = (request.GET.get('q') or '').strip()
    date_de_raw = (request.GET.get('date_de') or '').strip()
    date_a_raw = (request.GET.get('date_a') or '').strip()

    d_de = parse_date(date_de_raw) if date_de_raw else None
    d_a = parse_date(date_a_raw) if date_a_raw else None
    if d_de and d_a and d_de > d_a:
        d_de, d_a = d_a, d_de

    filt_date_de = d_de.isoformat() if d_de else ''
    filt_date_a = d_a.isoformat() if d_a else ''

    if statut_f in statuts_ok:
        qs = qs.filter(statut=statut_f)
    if mode_f in modes_ok:
        qs = qs.filter(mode_paiement=mode_f)
    filt_pv = ''
    if pv_raw.isdigit():
        pv_id = int(pv_raw)
        if points_vente.filter(pk=pv_id).exists():
            qs = qs.filter(point_vente_id=pv_id)
            filt_pv = str(pv_id)
    if q_f:
        qs = qs.filter(
            Q(numero_facture__icontains=q_f)
            | Q(client__nom__icontains=q_f)
            | Q(client__code_client__icontains=q_f)
        )
    if d_de:
        qs = qs.filter(date_facture__date__gte=d_de)
    if d_a:
        qs = qs.filter(date_facture__date__lte=d_a)

    return render(
        request,
        'facturation/liste_factures.html',
        {
            'factures': qs[:500],
            'actif': 'vente_factures',
            'points_vente': points_vente,
            'filt_statut': statut_f if statut_f in statuts_ok else '',
            'filt_mode': mode_f if mode_f in modes_ok else '',
            'filt_pv': filt_pv,
            'filt_q': q_f,
            'filt_date_de': filt_date_de,
            'filt_date_a': filt_date_a,
            'statuts_choix': Facture.STATUTS_FACTURE,
            'modes_paiement_choix': Facture.MODES_PAIEMENT,
        },
    )


@login_requis
def nouvelle_facture(request):
    entreprise = get_entreprise_utilisateur(request.user)
    admin = utilisateur_est_admin(request.user)
    if not entreprise and not admin:
        messages.error(request, 'Aucune entreprise associée.')
        return redirect('entreprise:dashboard')

    page_ctx = {
        'actif': 'vente_factures',
        'devises_taux_json': _devises_taux_json(entreprise),
    }

    if request.method == 'POST':
        form = FactureBrouillonForm(
            request.POST, entreprise=entreprise, user=request.user, admin=admin
        )
        if form.is_valid():
            pv = form.cleaned_data['point_vente']
            if not _peut_vendre_sur_pv(request.user, pv, admin):
                messages.error(request, 'Vous ne pouvez pas vendre sur ce point de vente.')
                return render(
                    request,
                    'facturation/facture_nouvelle.html',
                    {**page_ctx, 'form': form},
                )
            f = form.save(commit=False)
            f.client_id = form.cleaned_data['client_selection']
            f.vendeur = request.user
            f.statut = 'BROUILLON'
            f.total_ht = Decimal('0')
            f.total_tva = Decimal('0')
            f.total_ttc = Decimal('0')
            f.montant_paye = Decimal('0')
            f.reste_a_payer = Decimal('0')
            f.save()
            messages.success(request, 'Facture brouillon créée.')
            return redirect('facturation:detail-facture', pk=f.pk)
    else:
        form = FactureBrouillonForm(entreprise=entreprise, user=request.user, admin=admin)
        if entreprise and not admin:
            from stock.access import queryset_points_vente_pour_vente

            if not queryset_points_vente_pour_vente(request.user, entreprise, admin).exists():
                messages.warning(
                    request,
                    "Aucun point de vente autorisé pour enregistrer une vente. "
                    'Demandez les accès ou le droit « Vendre » sur votre PDV.',
                )
        if entreprise:
            dev = Devise.objects.filter(entreprise=entreprise, est_principale=True).first()
            if dev:
                form.fields['devise'].initial = dev.pk
                form.fields['taux_echange_appliqué'].initial = dev.taux_echange

    return render(
        request,
        'facturation/facture_nouvelle.html',
        {**page_ctx, 'form': form},
    )


@login_requis
@require_POST
def creer_client_rapide_facture(request):
    """Crée un client minimal rattaché à la branche du PV choisi ; réponse JSON pour Select2."""
    entreprise = get_entreprise_utilisateur(request.user)
    admin = utilisateur_est_admin(request.user)
    if not entreprise and not admin:
        return JsonResponse(
            {'ok': False, 'errors': {'__all__': ['Aucune entreprise associée.']}},
            status=403,
        )

    form_c = ClientRapideFactureForm(request.POST)
    if not form_c.is_valid():
        return JsonResponse({'ok': False, 'errors': form_c.errors}, status=400)

    pv_pk = form_c.cleaned_data['point_vente_id']
    pv = (
        point_vente_nouvelle_facture_queryset(entreprise, request.user, admin)
        .filter(pk=pv_pk)
        .select_related('branche', 'branche__entreprise')
        .first()
    )
    if not pv:
        return JsonResponse(
            {'ok': False, 'errors': {'point_vente_id': ['Point de vente invalide.']}},
            status=400,
        )

    if not _peut_vendre_sur_pv(request.user, pv, admin):
        return JsonResponse(
            {
                'ok': False,
                'errors': {'__all__': ['Droits insuffisants pour vendre sur ce point de vente.']},
            },
            status=403,
        )

    nom = form_c.cleaned_data['nom']
    tel = form_c.cleaned_data['telephone']

    email = (form_c.cleaned_data.get('email') or '').strip()
    passager = bool(form_c.cleaned_data.get('est_client_passager'))

    try:
        with transaction.atomic():
            c = Client(
                branche=pv.branche,
                nom=nom,
                type_client='DETAIL',
                telephone=tel,
                email=email,
                est_client_passager=passager,
            )
            c.save()
    except Exception as exc:
        return JsonResponse(
            {'ok': False, 'errors': {'__all__': [str(exc)]}},
            status=400,
        )

    return JsonResponse(
        {
            'ok': True,
            'id': c.pk,
            'text': label_client_facture(c),
        }
    )


@login_requis
def clients_autocomplete(request):
    """JSON pour Select2 : clients actifs (nom, code, téléphone), même périmètre que la facturation."""
    entreprise = get_entreprise_utilisateur(request.user)
    admin = utilisateur_est_admin(request.user)
    q = (request.GET.get('q') or '').strip()
    if len(q) < 2:
        return JsonResponse({'results': []})

    if not entreprise and not admin and not request.user.is_superuser:
        return JsonResponse({'results': []})

    qs = Client.objects.filter(est_actif=True)
    if entreprise:
        qs = qs.filter(entreprise=entreprise)
    qs = qs.filter(
        Q(nom__icontains=q) | Q(code_client__icontains=q) | Q(telephone__icontains=q)
    ).order_by('nom')[:30]

    return JsonResponse(
        {
            'results': [
                {'id': c.pk, 'text': label_client_facture(c)}
                for c in qs
            ]
        }
    )


@login_requis
def produits_autocomplete_facture(request, pk):
    """JSON Select2 — produits en stock sur le PDV de la facture (nom, SKU, code-barres)."""
    fact, redir = _charger_facture(request, pk)
    if redir:
        return JsonResponse({'results': []})
    if fact.statut != 'BROUILLON':
        return JsonResponse({'results': []})

    q = (request.GET.get('q') or '').strip()
    if len(q) < 2:
        return JsonResponse({'results': []})

    base = queryset_produits_facture_pv(fact.point_vente)
    qs = base.filter(
        Q(nom__icontains=q) | Q(sku__icontains=q) | Q(code_barre__icontains=q)
    ).order_by('nom')[:30]

    return JsonResponse(
        {
            'results': [
                {'id': p.pk, 'text': label_produit_facture(p)}
                for p in qs
            ]
        }
    )


@login_requis
def detail_facture(request, pk):
    fact, redir = _charger_facture(request, pk)
    if redir:
        return redir

    ligne_form = AjoutLigneFactureForm(point_vente=fact.point_vente)
    lignes = fact.lignes.select_related('mouvement_stock', 'produit').order_by('pk')
    admin = utilisateur_est_admin(request.user)
    lignes_hors_perimetre_pdv = False
    pv = fact.point_vente
    if (
        fact.statut == 'BROUILLON'
        and pv
        and pv.depot_source_id
        and lignes
    ):
        lignes_hors_perimetre_pdv = lignes.exclude(
            mouvement_stock__depot_id=pv.depot_source_id,
            mouvement_stock__pointvente_id=pv.pk,
        ).exists()
    pqs = queryset_produits_facture_pv(fact.point_vente)
    pids = list(pqs.values_list('pk', flat=True))
    dispo_map = _dispo_produits_pour_facture_brouillon(fact.point_vente, fact, pids)
    produits_catalogue = {}
    for p in pqs:
        sid = str(p.pk)
        meta = dispo_map.get(sid, {})
        slt = meta.get('stock_lots_total', Decimal('0'))
        ds = meta.get('deja_sur_facture', Decimal('0'))
        dj = meta.get('disponible_ajout', Decimal('0'))
        produits_catalogue[sid] = {
            'prix_ht': str(p.prix_vente_ht),
            'methode': p.methode_gestion,
            'methode_label': p.get_methode_gestion_display(),
            'stock_lots_total': str(slt),
            'deja_sur_facture': str(ds),
            'disponible_ajout': str(dj),
            'unite': p.unite_mesure,
            'taux_tva': str(p.tva_taux),
            'tva_applicable': taux_tva_actif(p.tva_taux),
        }

    from .models import PaiementFacture
    from django.db.models import Sum as _Sum
    paiements = fact.paiements.select_related('effectue_par').order_by('-date_paiement')

    # Solde réel calculé depuis les paiements enregistrés (fiable même pour
    # les factures validées avec l'ancien code qui forçait reste_a_payer = 0)
    total_paiements = paiements.aggregate(t=_Sum('montant'))['t'] or Decimal('0')
    reste_reel = max(Decimal('0'), fact.total_ttc - total_paiements)

    # Synchroniser reste_a_payer / montant_paye si l'ancien code les avait mal fixés
    if fact.statut == 'VALIDEE' and fact.mode_paiement == 'CREDIT':
        expected_paye = total_paiements
        expected_reste = reste_reel
        if fact.montant_paye != expected_paye or fact.reste_a_payer != expected_reste:
            fact.montant_paye  = expected_paye
            fact.reste_a_payer = expected_reste
            fact.save(update_fields=['montant_paye', 'reste_a_payer'])

    return render(
        request,
        'facturation/detail_facture.html',
        {
            'facture': fact,
            'lignes': lignes,
            'ligne_form': ligne_form,
            'actif': 'vente_factures',
            'peut_encaisser': _peut_gerer_caisse_sur_pv(request.user, fact.point_vente, admin),
            'produits_catalogue': produits_catalogue,
            'lignes_hors_perimetre_pdv': lignes_hors_perimetre_pdv,
            'paiements': paiements,
            'modes_paiement': PaiementFacture.MODES_PAIEMENT,
            'reste_reel': reste_reel,
        },
    )


def _context_impression_facture(facture: Facture):
    """Données communes imprimantes ticket / A4."""
    lignes = facture.lignes.select_related(
        'produit',
        'mouvement_stock',
        'mouvement_stock__depot',
        'mouvement_stock__pointvente',
        'mouvement_stock__location',
    ).order_by('pk')
    ent = facture.point_vente.branche.entreprise
    return {
        'facture': facture,
        'lignes':  lignes,
        'entreprise': ent,
    }


@login_requis
def imprimer_facture_ticket(request, pk):
    """Vue HTML optimisée ticket caisse (~80 mm de large à l’impression)."""
    fact, redir = _charger_facture(request, pk)
    if redir:
        return redir
    return render(request, 'facturation/imprimer_facture_ticket.html', _context_impression_facture(fact))


@login_requis
def imprimer_facture_ticket_detail(request, pk):
    """Ticket détaillé : lot, dates, marque, emplacement, vendeur complet."""
    fact, redir = _charger_facture(request, pk)
    if redir:
        return redir
    return render(request, 'facturation/imprimer_facture_ticket_detail.html', _context_impression_facture(fact))


@login_requis
def imprimer_facture_a4(request, pk):
    """Vue HTML mise en page A4 pour bulletin de vente / facture."""
    fact, redir = _charger_facture(request, pk)
    if redir:
        return redir
    return render(request, 'facturation/imprimer_facture_a4.html', _context_impression_facture(fact))


@login_requis
@require_POST
def ajouter_ligne_facture(request, pk):
    fact, redir = _charger_facture(request, pk)
    if redir:
        return redir
    if fact.statut != 'BROUILLON':
        messages.error(request, 'Facture figée.')
        return redirect('facturation:detail-facture', pk=pk)

    form = AjoutLigneFactureForm(request.POST, point_vente=fact.point_vente)
    if form.is_valid():
        produit = form.cleaned_data['produit']
        q_tot = form.cleaned_data['quantite']
        meta = _dispo_produits_pour_facture_brouillon(
            fact.point_vente, fact, [produit.pk]
        ).get(str(produit.pk))
        if meta is None:
            meta = {
                'stock_lots_total': Decimal('0'),
                'deja_sur_facture': Decimal('0'),
                'disponible_ajout': Decimal('0'),
            }
        dispo = meta['disponible_ajout']
        if q_tot > dispo:
            messages.error(
                request,
                f'Quantité supérieure au stock disponible pour ce produit sur ce point de vente. '
                f'Disponible pour ajout : {dispo} {produit.unite_mesure}. '
                f'(Stock actif sur les lots du PDV : {meta["stock_lots_total"]}, '
                f'dont {meta["deja_sur_facture"]} déjà sur cette facture via des lignes de ce PDV.)',
            )
            return redirect('facturation:detail-facture', pk=pk)
        pu = Decimal(str(produit.prix_vente_ht))
        try:
            with transaction.atomic():
                chunks = repartir_quantite_facture_sur_lots(fact.point_vente, produit, q_tot)
                n = 0
                for mv, q_tranche in chunks:
                    ht = pu * Decimal(str(q_tranche))
                    tva = montant_tva_sur_ht(ht, produit.tva_taux)
                    LigneFacture.objects.create(
                        facture=fact,
                        mouvement_stock=mv,
                        produit_id=produit.pk,
                        quantite=q_tranche,
                        prix_unitaire_ht=pu,
                        tva_montant=tva,
                        remise=Decimal('0'),
                    )
                    n += 1
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect('facturation:detail-facture', pk=pk)
        fact.recalcul_totaux()
        fact.save(update_fields=['total_ht', 'total_tva', 'total_ttc', 'reste_a_payer'])
        messages.success(
            request,
            f'{n} ligne(s) ajoutée(s) — répartition sur les lots selon {produit.get_methode_gestion_display()} '
            f'({produit.methode_gestion}).',
        )
    else:
        messages.error(request, 'Ligne invalide.')
    return redirect('facturation:detail-facture', pk=pk)


@login_requis
@require_POST
def supprimer_facture(request, pk):
    """Suppression définitive — uniquement si statut BROUILLON et si vendeur ou admin."""
    fact, redir = _charger_facture(request, pk)
    if redir:
        return redir

    admin = utilisateur_est_admin(request.user)

    if fact.statut != 'BROUILLON':
        messages.error(request, 'Seule une facture en brouillon peut être supprimée.')
        return redirect('facturation:detail-facture', pk=pk)

    if not admin and fact.vendeur_id != request.user.pk:
        messages.error(request, 'Vous ne pouvez supprimer que vos propres brouillons.')
        return redirect('facturation:detail-facture', pk=pk)

    numero = fact.numero_facture
    fact.delete()
    messages.success(request, f'Brouillon {numero} supprimé.')
    return redirect('facturation:liste-factures')


@login_requis
@require_POST
def supprimer_ligne_facture(request, pk, ligne_pk):
    fact, redir = _charger_facture(request, pk)
    if redir:
        return redir
    if fact.statut != 'BROUILLON':
        messages.error(request, 'Facture figée.')
        return redirect('facturation:detail-facture', pk=pk)
    ligne = get_object_or_404(LigneFacture, pk=ligne_pk, facture=fact)
    ligne.delete()
    fact.recalcul_totaux()
    fact.save(update_fields=['total_ht', 'total_tva', 'total_ttc', 'reste_a_payer'])
    messages.success(request, 'Ligne supprimée.')
    return redirect('facturation:detail-facture', pk=pk)


@login_requis
@require_POST
def terminer_facture_caisse(request, pk):
    """Brouillon → file d’attente caisse (pas de déstockage, pas de paiement enregistré)."""
    fact, redir = _charger_facture(request, pk)
    if redir:
        return redir
    admin = utilisateur_est_admin(request.user)

    if fact.statut != 'BROUILLON':
        messages.warning(request, 'Seule une facture brouillon peut être envoyée à la caisse.')
        return redirect('facturation:detail-facture', pk=pk)
    if not fact.lignes.exists():
        messages.error(request, 'Ajoutez au moins une ligne avant de terminer.')
        return redirect('facturation:detail-facture', pk=pk)
    if not _peut_vendre_sur_pv(request.user, fact.point_vente, admin):
        messages.error(request, 'Action non autorisée sur ce point de vente.')
        return redirect('facturation:detail-facture', pk=pk)

    incoherences = verifier_quantites_lignes_facture(fact)
    if incoherences:
        messages.error(
            request,
            'Impossible d’envoyer à la caisse : stock disponible insuffisant sur au moins une ligne. '
            + ' '.join(incoherences),
        )
        return redirect('facturation:detail-facture', pk=pk)

    fact.recalcul_totaux()
    fact.statut = 'EN_CAISSE'
    fact.save(update_fields=['statut', 'total_ht', 'total_tva', 'total_ttc', 'reste_a_payer'])
    messages.success(request, 'Facture terminée — transmise à la caisse pour encaissement.')
    return redirect('facturation:detail-facture', pk=pk)


@login_requis
@require_POST
def valider_facture(request, pk):
    from datetime import date

    from finance.posting import poster_cout_stock_vente

    fact, redir = _charger_facture(request, pk)
    if redir:
        return redir

    admin = utilisateur_est_admin(request.user)

    if fact.statut == 'VALIDEE':
        messages.warning(request, 'Cette facture est déjà validée.')
        return redirect('facturation:detail-facture', pk=pk)

    encaisser_ok = _peut_gerer_caisse_sur_pv(request.user, fact.point_vente, admin)

    if fact.statut == 'BROUILLON':
        if not encaisser_ok:
            messages.error(
                request,
                'Seuls les utilisateurs avec le droit « Gérer la caisse » sur ce point de vente peuvent '
                'encaisser directement depuis un brouillon. Utilisez « Terminer » pour envoyer la facture à la caisse.',
            )
            return redirect('facturation:detail-facture', pk=pk)
    elif fact.statut == 'EN_CAISSE':
        if not encaisser_ok:
            messages.error(request, 'Seule la caisse peut encaisser cette facture.')
            return redirect('facturation:detail-facture', pk=pk)
    else:
        messages.warning(request, 'Cette facture ne peut pas être encaissée dans cet état.')
        return redirect('facturation:detail-facture', pk=pk)

    if not fact.lignes.exists():
        messages.error(request, 'Aucune ligne sur cette facture.')
        return redirect('facturation:detail-facture', pk=pk)

    incoherences = verifier_quantites_lignes_facture(fact)
    if incoherences:
        messages.error(
            request,
            'Validation impossible tant que la quantité disponible sur chaque lot n’est pas '
            'au moins égale à la quantité facturée. '
            + ' '.join(incoherences),
        )
        return redirect('facturation:detail-facture', pk=pk)

    # ── Calcul du montant payé selon mode et saisie ──────────────────────────
    mode = fact.mode_paiement
    if mode == 'CREDIT':
        # Vente à crédit : aucun encaissement immédiat, dette intégrale
        montant_paye_new = Decimal('0')
        reste_new = fact.total_ttc
    else:
        montant_recu_raw = request.POST.get('montant_recu', '').strip().replace(',', '.')
        if montant_recu_raw:
            try:
                montant_recu = Decimal(montant_recu_raw)
                if montant_recu < 0:
                    raise ValueError('Montant reçu négatif.')
                montant_paye_new = min(montant_recu, fact.total_ttc)
                reste_new = fact.total_ttc - montant_paye_new
            except Exception:
                messages.error(request, 'Montant reçu invalide.')
                return redirect('facturation:detail-facture', pk=pk)
        else:
            # Aucun montant saisi → paiement intégral supposé
            montant_paye_new = fact.total_ttc
            reste_new = Decimal('0')

    ent = fact.point_vente.branche.entreprise
    try:
        with transaction.atomic():
            montant_cos = consommer_mouvements_facture(fact, request.user)
            fact.statut = 'VALIDEE'
            fact.montant_paye = montant_paye_new
            fact.reste_a_payer = reste_new
            fact.save(update_fields=['statut', 'montant_paye', 'reste_a_payer'])
            try:
                poster_cout_stock_vente(
                    ent,
                    montant_cos,
                    fact.numero_facture,
                    date.today(),
                    f"Coût stock — {fact.numero_facture}",
                    request.user,
                )
            except Exception as exc:
                messages.warning(request, f'Comptabilité coût stock : {exc}')
        # Transaction caisse uniquement si encaissement réel
        if montant_paye_new > 0:
            try:
                from caisse.services import enregistrer_encaissement_facture
                enregistrer_encaissement_facture(fact, request.user)
            except Exception:
                pass
        # Message contextuel
        sym = fact.devise.symbole
        if mode == 'CREDIT':
            messages.success(
                request,
                f'Facture validée à crédit — dette de {reste_new} {sym} enregistrée pour {fact.client.nom}.'
            )
        elif reste_new > 0:
            messages.success(
                request,
                f'Facture partiellement payée ({montant_paye_new} {sym} reçus). '
                f'Reste à payer : {reste_new} {sym}.'
            )
        else:
            messages.success(request, 'Facture encaissée, validée et stock mis à jour.')
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect('facturation:detail-facture', pk=pk)


# ─────────────────────────────────────────────
# Paiement d'une facture à crédit / partielle
# ─────────────────────────────────────────────

@login_requis
@require_POST
def enregistrer_paiement_facture(request, pk):
    from .models import PaiementFacture

    fact, redir = _charger_facture(request, pk)
    if redir:
        return redir

    if fact.statut != 'VALIDEE':
        messages.error(request, 'Seule une facture validée peut recevoir un paiement.')
        return redirect('facturation:detail-facture', pk=pk)

    # Solde réel basé sur les paiements déjà enregistrés (fiable même si
    # reste_a_payer a été mal initialisé par l'ancien code de validation)
    from django.db.models import Sum as _Sum
    total_paiements = fact.paiements.aggregate(t=_Sum('montant'))['t'] or Decimal('0')
    reste_reel = max(Decimal('0'), fact.total_ttc - total_paiements)

    if reste_reel <= 0:
        messages.warning(request, 'Cette facture est déjà entièrement réglée.')
        return redirect('facturation:detail-facture', pk=pk)

    # Lecture des champs POST
    montant_raw   = request.POST.get('montant', '').strip().replace(',', '.')
    mode          = request.POST.get('mode_paiement', 'CASH').strip()
    notes         = request.POST.get('notes', '').strip()

    modes_valides = [m[0] for m in PaiementFacture.MODES_PAIEMENT]
    if mode not in modes_valides:
        mode = 'CASH'

    try:
        montant = Decimal(montant_raw)
        if montant <= 0:
            raise ValueError('Le montant doit être positif.')
        if montant > reste_reel:
            raise ValueError(
                f'Le montant saisi ({montant}) dépasse le reste à payer ({reste_reel}).'
            )
    except (ValueError, Exception) as exc:
        messages.error(request, str(exc) if str(exc) else 'Montant invalide.')
        return redirect('facturation:detail-facture', pk=pk)

    from django.db import transaction as db_transaction
    try:
        with db_transaction.atomic():
            paiement = PaiementFacture.objects.create(
                facture       = fact,
                montant       = montant,
                mode_paiement = mode,
                effectue_par  = request.user,
                notes         = notes,
            )
            # Recalcul depuis la source de vérité (somme des paiements)
            nouveau_total_paye = total_paiements + montant
            nouveau_reste      = max(Decimal('0'), fact.total_ttc - nouveau_total_paye)
            fact.montant_paye  = nouveau_total_paye
            fact.reste_a_payer = nouveau_reste
            fact.save(update_fields=['montant_paye', 'reste_a_payer'])

        # Encaissement caisse
        try:
            from caisse.services import enregistrer_encaissement_paiement
            enregistrer_encaissement_paiement(paiement, fact, request.user)
        except Exception:
            pass

        sym = fact.devise.symbole
        if fact.reste_a_payer <= 0:
            messages.success(
                request,
                f'Paiement {paiement.numero} enregistré ({montant} {sym}). Facture entièrement réglée.'
            )
        else:
            messages.success(
                request,
                f'Paiement {paiement.numero} enregistré ({montant} {sym}). '
                f'Reste à payer : {fact.reste_a_payer} {sym}.'
            )
    except Exception as exc:
        messages.error(request, f'Erreur lors de l\'enregistrement : {exc}')

    return redirect('facturation:detail-facture', pk=pk)


@login_requis
def imprimer_recu_paiement(request, paiement_pk):
    from .models import PaiementFacture
    from stock.access import get_entreprise_utilisateur

    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    paiement   = get_object_or_404(
        PaiementFacture.objects.select_related(
            'facture', 'facture__client', 'facture__point_vente',
            'facture__devise', 'effectue_par',
        ),
        pk=paiement_pk,
    )
    fact = paiement.facture
    # Vérification périmètre
    _, redir = _charger_facture(request, fact.pk)
    if redir:
        return redir
    return render(request, 'facturation/recu_paiement.html', {
        'paiement':   paiement,
        'facture':    fact,
        'entreprise': entreprise,
    })
