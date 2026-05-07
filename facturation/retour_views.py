"""Vues Ventes Retournées — workflow avec approbation manager."""

from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from entreprise.models import Devise, PointVente
from stock.access import get_entreprise_utilisateur, utilisateur_est_admin
from stock.models import MouvementOrigine
from stock.services import reintegrer_mouvements_retour
from utilisateur.acces_metier import utilisateur_peut_permission
from utilisateur.decorators import login_requis

from .models import Facture, LigneFacture, LigneRetour, RetourVente


# ─────────────────────────────────────────────
# Helpers permission
# ─────────────────────────────────────────────

def _peut_approuver(user):
    """Manager / assistant manager : peut approuver ou rejeter un retour."""
    return utilisateur_peut_permission(user, 'approuver_facture_proforma')


def _scope_retours(user, entreprise, admin):
    qs = RetourVente.objects.select_related(
        'facture_origine', 'client', 'point_vente', 'devise', 'vendeur',
        'approuve_par',
    ).order_by('-date_retour')
    if admin:
        return qs.filter(point_vente__branche__entreprise=entreprise) if entreprise else qs
    branche = getattr(user, 'branche', None)
    if not branche:
        return RetourVente.objects.none()
    return qs.filter(point_vente__branche=branche)


# ─────────────────────────────────────────────
# Liste
# ─────────────────────────────────────────────

@login_requis
def liste_retours(request):
    if not utilisateur_peut_permission(request.user, 'acces_ventes_retournees'):
        messages.error(request, 'Accès refusé.')
        return redirect('entreprise:dashboard')

    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    qs         = _scope_retours(request.user, entreprise, admin)

    q_f      = (request.GET.get('q') or '').strip()
    statut_f = (request.GET.get('statut') or '').strip()
    statuts_ok = {c[0] for c in RetourVente.STATUTS}

    if statut_f in statuts_ok:
        qs = qs.filter(statut=statut_f)
    if q_f:
        qs = qs.filter(
            Q(numero_retour__icontains=q_f)
            | Q(facture_origine__numero_facture__icontains=q_f)
            | Q(client__nom__icontains=q_f)
        )

    return render(request, 'facturation/retours/liste_retours.html', {
        'retours':        qs[:300],
        'actif':          'retours',
        'peut_approuver': _peut_approuver(request.user),
        'statuts_choix':  RetourVente.STATUTS,
        'filt_statut':    statut_f if statut_f in statuts_ok else '',
        'filt_q':         q_f,
    })


# ─────────────────────────────────────────────
# Sélection facture
# ─────────────────────────────────────────────

@login_requis
def nouveau_retour(request):
    if not utilisateur_peut_permission(request.user, 'acces_ventes_retournees'):
        messages.error(request, 'Accès refusé.')
        return redirect('entreprise:dashboard')

    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    branche    = getattr(request.user, 'branche', None)

    q = (request.GET.get('q') or '').strip()
    factures_qs = Facture.objects.filter(statut='VALIDEE').order_by('-date_facture')
    if entreprise:
        factures_qs = factures_qs.filter(point_vente__branche__entreprise=entreprise)
    if not admin and branche:
        factures_qs = factures_qs.filter(point_vente__branche=branche)
    if q:
        factures_qs = factures_qs.filter(
            Q(numero_facture__icontains=q) | Q(client__nom__icontains=q)
        )
    else:
        factures_qs = factures_qs.none()

    return render(request, 'facturation/retours/nouveau_retour.html', {
        'actif':    'retours',
        'factures': factures_qs[:50],
        'q':        q,
    })


# ─────────────────────────────────────────────
# Formulaire de saisie des lignes retournées
# ─────────────────────────────────────────────

@login_requis
def detail_retour_init(request, facture_pk):
    if not utilisateur_peut_permission(request.user, 'acces_ventes_retournees'):
        messages.error(request, 'Accès refusé.')
        return redirect('entreprise:dashboard')

    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    branche    = getattr(request.user, 'branche', None)

    f_qs = Facture.objects.filter(pk=facture_pk, statut='VALIDEE')
    if entreprise:
        f_qs = f_qs.filter(point_vente__branche__entreprise=entreprise)
    if not admin and branche:
        f_qs = f_qs.filter(point_vente__branche=branche)
    facture = get_object_or_404(f_qs)

    lignes = facture.lignes.select_related('mouvement_stock', 'produit').all()

    lignes_data = []
    for lig in lignes:
        mv = lig.mouvement_stock
        deja_retourne = sum(
            lr.quantite_retournee
            for lr in lig.lignes_retour.filter(
                retour__statut__in=['BROUILLON', 'EN_ATTENTE', 'APPROUVE']
            )
        )
        disponible = float((mv.quantite_affectee if mv else 0) - deja_retourne)
        lignes_data.append({
            'ligne':      lig,
            'disponible': max(disponible, 0),
        })

    devise_principale = None
    if entreprise:
        devise_principale = Devise.objects.filter(entreprise=entreprise, est_principale=True).first()

    if request.method == 'POST':
        motif     = request.POST.get('motif', '').strip()
        pv_pk     = request.POST.get('point_vente', '').strip()
        devise_pk = request.POST.get('devise', '').strip()

        erreurs = []
        pv = None
        if pv_pk.isdigit():
            pv_qs = PointVente.objects.filter(pk=int(pv_pk), est_actif=True)
            if entreprise:
                pv_qs = pv_qs.filter(branche__entreprise=entreprise)
            pv = pv_qs.first()
        if not pv:
            erreurs.append('Point de vente invalide.')

        devise = None
        if devise_pk.isdigit():
            dev_qs = Devise.objects.filter(pk=int(devise_pk))
            if entreprise:
                dev_qs = dev_qs.filter(entreprise=entreprise)
            devise = dev_qs.first()
        if not devise:
            erreurs.append('Devise invalide.')

        lignes_a_retourner = []
        for ld in lignes_data:
            lig = ld['ligne']
            val = request.POST.get(f'qte_{lig.pk}', '').strip()
            if not val:
                continue
            try:
                qte = Decimal(val.replace(',', '.'))
            except Exception:
                erreurs.append(f'Quantité invalide pour {lig.produit.nom}.')
                continue
            if qte <= 0:
                continue
            if qte > Decimal(str(ld['disponible'])):
                erreurs.append(
                    f'{lig.produit.nom} : quantité ({qte}) > disponible ({ld["disponible"]}).'
                )
                continue
            lignes_a_retourner.append((lig, qte))

        if not lignes_a_retourner:
            erreurs.append('Sélectionnez au moins une ligne à retourner.')

        if erreurs:
            for e in erreurs:
                messages.error(request, e)
        else:
            with transaction.atomic():
                retour = RetourVente(
                    facture_origine=facture,
                    point_vente=pv,
                    vendeur=request.user,
                    client=facture.client,
                    devise=devise,
                    taux_echange=devise.taux_echange,
                    motif=motif,
                    statut='BROUILLON',
                )
                retour.save()
                for lig, qte in lignes_a_retourner:
                    tva_unitaire = (
                        Decimal(str(lig.tva_montant or 0)) / Decimal(str(lig.quantite))
                        if lig.quantite else Decimal('0')
                    )
                    LigneRetour.objects.create(
                        retour=retour,
                        ligne_facture_origine=lig,
                        mouvement_stock=lig.mouvement_stock,
                        produit=lig.produit,
                        quantite_retournee=qte,
                        prix_unitaire_ht=lig.prix_unitaire_ht,
                        tva_montant=tva_unitaire * qte,
                    )
                retour.recalcul_totaux()
                retour.save(update_fields=['total_ht', 'total_tva', 'total_ttc'])
            messages.success(request, f'Retour {retour.numero_retour} créé en brouillon.')
            return redirect('facturation:detail-retour', pk=retour.pk)

    pvs     = PointVente.objects.filter(branche__entreprise=entreprise, est_actif=True) if entreprise else PointVente.objects.filter(est_actif=True)
    devises = Devise.objects.filter(entreprise=entreprise) if entreprise else Devise.objects.all()

    return render(request, 'facturation/retours/detail_retour_init.html', {
        'facture':           facture,
        'lignes_data':       lignes_data,
        'actif':             'retours',
        'points_vente':      pvs,
        'devises':           devises,
        'devise_principale': devise_principale,
    })


# ─────────────────────────────────────────────
# Détail retour
# ─────────────────────────────────────────────

@login_requis
def detail_retour(request, pk):
    if not utilisateur_peut_permission(request.user, 'acces_ventes_retournees'):
        messages.error(request, 'Accès refusé.')
        return redirect('entreprise:dashboard')

    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    retour = get_object_or_404(
        _scope_retours(request.user, entreprise, admin).prefetch_related('lignes__produit'),
        pk=pk,
    )
    depense_liee = None
    if retour.statut == 'APPROUVE':
        try:
            depense_liee = retour.depense_liee
        except Exception:
            pass

    return render(request, 'facturation/retours/detail_retour.html', {
        'retour':         retour,
        'depense_liee':   depense_liee,
        'actif':          'retours',
        'peut_approuver': _peut_approuver(request.user),
    })


# ─────────────────────────────────────────────
# Étape 1 — Vendeur soumet au manager
# ─────────────────────────────────────────────

@login_requis
@require_POST
def soumettre_retour(request, pk):
    if not utilisateur_peut_permission(request.user, 'acces_ventes_retournees'):
        messages.error(request, 'Accès refusé.')
        return redirect('facturation:liste-retours')

    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    retour     = get_object_or_404(_scope_retours(request.user, entreprise, admin), pk=pk)

    if retour.statut != 'BROUILLON':
        messages.warning(request, 'Ce retour ne peut pas être soumis dans son état actuel.')
        return redirect('facturation:detail-retour', pk=pk)

    if not retour.lignes.exists():
        messages.error(request, 'Ajoutez au moins une ligne avant de soumettre.')
        return redirect('facturation:detail-retour', pk=pk)

    retour.statut    = 'EN_ATTENTE'
    retour.soumis_le = timezone.now()
    retour.save(update_fields=['statut', 'soumis_le'])
    messages.success(request, f'Retour {retour.numero_retour} soumis au manager pour approbation.')
    return redirect('facturation:detail-retour', pk=pk)


# ─────────────────────────────────────────────
# Étape 2 — Manager approuve → stock + dépense
# ─────────────────────────────────────────────

@login_requis
@require_POST
def approuver_retour(request, pk):
    if not _peut_approuver(request.user):
        messages.error(request, 'Droits insuffisants pour approuver un retour.')
        return redirect('facturation:detail-retour', pk=pk)

    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    retour     = get_object_or_404(_scope_retours(request.user, entreprise, admin), pk=pk)

    if retour.statut != 'EN_ATTENTE':
        messages.warning(request, 'Seul un retour en attente peut être approuvé.')
        return redirect('facturation:detail-retour', pk=pk)

    commentaire = request.POST.get('commentaire_manager', '').strip()

    with transaction.atomic():
        # Réintégration du stock
        reintegrer_mouvements_retour(retour, request.user)

        # Approbation
        retour.statut              = 'APPROUVE'
        retour.approuve_par        = request.user
        retour.date_approbation    = timezone.now()
        retour.commentaire_manager = commentaire
        retour.save(update_fields=[
            'statut', 'approuve_par', 'date_approbation', 'commentaire_manager'
        ])

        # Création de la dépense en brouillon (caisse doit la valider)
        from depenses.models import Depense
        dep = Depense(
            point_vente=retour.point_vente,
            type_depense='RETOUR_CLIENT',
            montant=retour.total_ttc,
            devise=retour.devise,
            taux_echange=retour.taux_echange,
            motif=(
                f'Remboursement client — retour {retour.numero_retour} '
                f'(facture {retour.facture_origine.numero_facture}). '
                f'Client : {retour.client.nom}.'
            ),
            retour_vente=retour,
            statut='BROUILLON',
            enregistre_par=request.user,
        )
        dep.save()

    # Transaction caisse automatique si session ouverte
    try:
        from caisse.services import enregistrer_decaissement_retour
        enregistrer_decaissement_retour(retour, dep, request.user)
    except Exception:
        pass

    messages.success(
        request,
        f'Retour {retour.numero_retour} approuvé. Stock réintégré. '
        f'Dépense {dep.numero_depense} créée en brouillon — à valider par la caisse.',
    )
    return redirect('facturation:detail-retour', pk=pk)


# ─────────────────────────────────────────────
# Étape 2b — Manager rejette
# ─────────────────────────────────────────────

@login_requis
@require_POST
def rejeter_retour(request, pk):
    if not _peut_approuver(request.user):
        messages.error(request, 'Droits insuffisants pour rejeter un retour.')
        return redirect('facturation:detail-retour', pk=pk)

    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    retour     = get_object_or_404(_scope_retours(request.user, entreprise, admin), pk=pk)

    if retour.statut != 'EN_ATTENTE':
        messages.warning(request, 'Seul un retour en attente peut être rejeté.')
        return redirect('facturation:detail-retour', pk=pk)

    commentaire = request.POST.get('commentaire_manager', '').strip()
    retour.statut              = 'REJETE'
    retour.approuve_par        = request.user
    retour.date_approbation    = timezone.now()
    retour.commentaire_manager = commentaire
    retour.save(update_fields=[
        'statut', 'approuve_par', 'date_approbation', 'commentaire_manager'
    ])
    messages.warning(request, f'Retour {retour.numero_retour} rejeté.')
    return redirect('facturation:detail-retour', pk=pk)


# ─────────────────────────────────────────────
# Annulation (brouillon uniquement)
# ─────────────────────────────────────────────

@login_requis
@require_POST
def annuler_retour(request, pk):
    if not utilisateur_peut_permission(request.user, 'acces_ventes_retournees'):
        messages.error(request, 'Accès refusé.')
        return redirect('facturation:liste-retours')

    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    retour     = get_object_or_404(_scope_retours(request.user, entreprise, admin), pk=pk)

    if retour.statut not in ('BROUILLON', 'REJETE'):
        messages.warning(request, 'Seul un retour en brouillon ou rejeté peut être annulé.')
        return redirect('facturation:detail-retour', pk=pk)

    retour.statut = 'ANNULE'
    retour.save(update_fields=['statut'])
    messages.warning(request, f'Retour {retour.numero_retour} annulé.')
    return redirect('facturation:liste-retours')
