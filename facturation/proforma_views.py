"""Vues Facture Proforma — création, révision manager, approbation, conversion en brouillon."""

from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from entreprise.models import Devise, Produit
from stock.access import get_entreprise_utilisateur, utilisateur_est_admin
from tiers.models import Client
from utilisateur.acces_metier import utilisateur_peut_permission
from utilisateur.decorators import login_requis

from .forms import (
    DecisionProformaForm,
    LigneProformaForm,
    ProformaEnteteForm,
    label_client_facture,
    label_produit_facture,
)
from .models import Facture, FactureProforma, LigneFacture, LigneProforma
from .pricing import montant_tva_sur_ht


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _peut_approuver(user):
    return utilisateur_peut_permission(user, 'approuver_facture_proforma')


def _scope_proformas(user, entreprise, admin):
    """
    Queryset de base des proformas visibles.
    - Admin / approuveur → toutes les proformas de l'entreprise.
    - Utilisateur normal → uniquement les proformas de SA branche.
    """
    qs = FactureProforma.objects.select_related(
        'branche', 'client', 'devise', 'vendeur', 'approuve_par'
    ).order_by('-date_emission')

    if admin or _peut_approuver(user):
        if entreprise:
            return qs.filter(branche__entreprise=entreprise)
        return qs

    if not entreprise:
        return FactureProforma.objects.none()

    branche = getattr(user, 'branche', None)
    if not branche:
        return FactureProforma.objects.none()

    return qs.filter(branche=branche)


def _charger_proforma(request, pk):
    """Charge une proforma en vérifiant les droits de consultation."""
    entreprise = get_entreprise_utilisateur(request.user)
    admin = utilisateur_est_admin(request.user)

    qs = _scope_proformas(request.user, entreprise, admin).select_related(
        'branche__entreprise', 'client', 'devise', 'vendeur', 'approuve_par'
    )
    pf = get_object_or_404(qs, pk=pk)
    return pf, entreprise, admin


# ─────────────────────────────────────────────
# Autocomplete produits
# ─────────────────────────────────────────────

@login_requis
def produits_autocomplete_proforma(request, pk):
    """
    JSON Select2 — produits actifs de l'entreprise de la proforma.
    Le pk de la proforma est obligatoire pour dériver l'entreprise exacte,
    même pour les admins qui n'ont pas de branche directe.
    """
    pf, entreprise, admin = _charger_proforma(request, pk)
    entreprise_proforma = pf.branche.entreprise

    q = (request.GET.get('q') or '').strip()
    if len(q) < 2:
        return JsonResponse({'results': []})

    qs = Produit.objects.filter(
        est_actif=True,
        entreprise=entreprise_proforma,
    ).filter(
        Q(nom__icontains=q) | Q(sku__icontains=q) | Q(code_barre__icontains=q)
    ).order_by('nom')[:30]

    return JsonResponse({
        'results': [
            {'id': p.pk, 'text': label_produit_facture(p), 'prix_ht': str(p.prix_vente_ht)}
            for p in qs
        ]
    })


@login_requis
def clients_autocomplete_proforma(request):
    """JSON Select2 — clients actifs de l'entreprise pour proforma."""
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

    return JsonResponse({
        'results': [{'id': c.pk, 'text': label_client_facture(c)} for c in qs]
    })


# ─────────────────────────────────────────────
# Liste
# ─────────────────────────────────────────────

@login_requis
def liste_proformas(request):
    entreprise = get_entreprise_utilisateur(request.user)
    admin = utilisateur_est_admin(request.user)
    peut_approuver = _peut_approuver(request.user)

    qs = _scope_proformas(request.user, entreprise, admin)

    statuts_ok = {c[0] for c in FactureProforma.STATUTS_PROFORMA}
    statut_f = (request.GET.get('statut') or '').strip()
    q_f = (request.GET.get('q') or '').strip()
    date_de_raw = (request.GET.get('date_de') or '').strip()
    date_a_raw = (request.GET.get('date_a') or '').strip()

    d_de = parse_date(date_de_raw) if date_de_raw else None
    d_a = parse_date(date_a_raw) if date_a_raw else None
    if d_de and d_a and d_de > d_a:
        d_de, d_a = d_a, d_de

    if statut_f in statuts_ok:
        qs = qs.filter(statut=statut_f)
    if q_f:
        qs = qs.filter(
            Q(numero_proforma__icontains=q_f)
            | Q(client__nom__icontains=q_f)
            | Q(client__code_client__icontains=q_f)
        )
    if d_de:
        qs = qs.filter(date_emission__date__gte=d_de)
    if d_a:
        qs = qs.filter(date_emission__date__lte=d_a)

    return render(request, 'facturation/proforma/liste_proformas.html', {
        'proformas': qs[:500],
        'actif': 'vente_proformas',
        'filt_statut': statut_f if statut_f in statuts_ok else '',
        'filt_q': q_f,
        'filt_date_de': d_de.isoformat() if d_de else '',
        'filt_date_a': d_a.isoformat() if d_a else '',
        'statuts_choix': FactureProforma.STATUTS_PROFORMA,
        'peut_approuver': peut_approuver,
    })


# ─────────────────────────────────────────────
# Création
# ─────────────────────────────────────────────

@login_requis
def nouvelle_proforma(request):
    entreprise = get_entreprise_utilisateur(request.user)
    admin = utilisateur_est_admin(request.user)
    peut_approuver = _peut_approuver(request.user)
    acces_eleve = admin or peut_approuver

    if not entreprise and not acces_eleve:
        messages.error(request, 'Aucune entreprise associée.')
        return redirect('entreprise:dashboard')

    # Branche forcée pour les utilisateurs sans accès élevé
    branche_forcee = None
    if not acces_eleve:
        branche_forcee = getattr(request.user, 'branche', None)
        if not branche_forcee:
            messages.error(request, 'Votre compte n\'est rattaché à aucune branche. Contactez un administrateur.')
            return redirect('facturation:liste-proformas')

    ctx = {'actif': 'vente_proformas', 'branche_forcee': branche_forcee}

    if request.method == 'POST':
        form = ProformaEnteteForm(
            request.POST,
            entreprise=entreprise,
            user=request.user,
            admin=acces_eleve,
            branche_forcee=branche_forcee,
        )
        if form.is_valid():
            pf = form.save(commit=False)
            pf.client_id = form.cleaned_data['client_selection']
            pf.vendeur = request.user
            pf.statut = 'BROUILLON'
            pf.total_ht = Decimal('0')
            pf.total_tva = Decimal('0')
            pf.total_ttc = Decimal('0')
            pf.save()
            messages.success(request, f'Proforma {pf.numero_proforma} créée.')
            return redirect('facturation:detail-proforma', pk=pf.pk)
    else:
        form = ProformaEnteteForm(
            entreprise=entreprise,
            user=request.user,
            admin=acces_eleve,
            branche_forcee=branche_forcee,
        )
        if entreprise:
            dev = Devise.objects.filter(entreprise=entreprise, est_principale=True).first()
            if dev:
                form.fields['devise'].initial = dev.pk
        if branche_forcee:
            form.fields['branche'].initial = branche_forcee.pk

    return render(request, 'facturation/proforma/nouvelle_proforma.html', {**ctx, 'form': form})


# ─────────────────────────────────────────────
# Détail
# ─────────────────────────────────────────────

@login_requis
def detail_proforma(request, pk):
    pf, entreprise, admin = _charger_proforma(request, pk)
    peut_approuver = _peut_approuver(request.user)
    peut_editer = pf.statut == 'BROUILLON' and (admin or pf.vendeur_id == request.user.pk)

    entreprise_proforma = pf.branche.entreprise
    ligne_form = LigneProformaForm(entreprise=entreprise_proforma) if peut_editer else None
    decision_form = DecisionProformaForm() if peut_approuver and pf.statut == 'EN_ATTENTE' else None

    lignes = pf.lignes.select_related('produit').order_by('pk')

    return render(request, 'facturation/proforma/detail_proforma.html', {
        'proforma': pf,
        'lignes': lignes,
        'ligne_form': ligne_form,
        'decision_form': decision_form,
        'actif': 'vente_proformas',
        'peut_approuver': peut_approuver,
        'peut_editer': peut_editer,
    })


# ─────────────────────────────────────────────
# Gestion des lignes
# ─────────────────────────────────────────────

@login_requis
@require_POST
def ajouter_ligne_proforma(request, pk):
    pf, entreprise, admin = _charger_proforma(request, pk)

    if pf.statut != 'BROUILLON':
        messages.error(request, 'Seule une proforma en brouillon peut être modifiée.')
        return redirect('facturation:detail-proforma', pk=pk)

    if not (admin or pf.vendeur_id == request.user.pk):
        messages.error(request, 'Action non autorisée.')
        return redirect('facturation:detail-proforma', pk=pk)

    entreprise_proforma = pf.branche.entreprise
    form = LigneProformaForm(request.POST, entreprise=entreprise_proforma)
    if form.is_valid():
        produit = form.cleaned_data['produit']
        quantite = form.cleaned_data['quantite']
        pu = form.cleaned_data['prix_unitaire_ht']
        remise = form.cleaned_data['remise']
        ht = pu * quantite - remise
        tva = montant_tva_sur_ht(ht, produit.tva_taux)

        LigneProforma.objects.create(
            proforma=pf,
            produit=produit,
            quantite=quantite,
            prix_unitaire_ht=pu,
            tva_montant=tva,
            remise=remise,
        )
        pf.recalcul_totaux()
        pf.save(update_fields=['total_ht', 'total_tva', 'total_ttc'])
        messages.success(request, f'Ligne « {produit.nom} » ajoutée.')
    else:
        messages.error(request, 'Données de ligne invalides.')

    return redirect('facturation:detail-proforma', pk=pk)


@login_requis
@require_POST
def supprimer_ligne_proforma(request, pk, ligne_pk):
    pf, entreprise, admin = _charger_proforma(request, pk)

    if pf.statut != 'BROUILLON':
        messages.error(request, 'Proforma figée.')
        return redirect('facturation:detail-proforma', pk=pk)

    if not (admin or pf.vendeur_id == request.user.pk):
        messages.error(request, 'Action non autorisée.')
        return redirect('facturation:detail-proforma', pk=pk)

    ligne = get_object_or_404(LigneProforma, pk=ligne_pk, proforma=pf)
    ligne.delete()
    pf.recalcul_totaux()
    pf.save(update_fields=['total_ht', 'total_tva', 'total_ttc'])
    messages.success(request, 'Ligne supprimée.')
    return redirect('facturation:detail-proforma', pk=pk)


# ─────────────────────────────────────────────
# Approbation / rejet
# ─────────────────────────────────────────────

@login_requis
@require_POST
def approuver_proforma(request, pk):
    if not _peut_approuver(request.user):
        messages.error(request, 'Droits insuffisants pour approuver une proforma.')
        return redirect('facturation:detail-proforma', pk=pk)

    pf, entreprise, admin = _charger_proforma(request, pk)

    if pf.statut != 'EN_ATTENTE':
        messages.warning(request, 'Seule une proforma soumise (en attente) peut être approuvée.')
        return redirect('facturation:detail-proforma', pk=pk)

    if not pf.lignes.exists():
        messages.error(request, 'Impossible d\'approuver une proforma sans lignes.')
        return redirect('facturation:detail-proforma', pk=pk)

    form = DecisionProformaForm(request.POST)
    if form.is_valid():
        pf.statut = 'ACCEPTEE'
        pf.approuve_par = request.user
        pf.date_approbation = timezone.now()
        pf.commentaire_manager = form.cleaned_data.get('commentaire_manager') or ''
        pf.save(update_fields=['statut', 'approuve_par', 'date_approbation', 'commentaire_manager'])
        messages.success(request, f'Proforma {pf.numero_proforma} approuvée.')
    else:
        messages.error(request, 'Erreur lors de la validation du formulaire.')

    return redirect('facturation:detail-proforma', pk=pk)


@login_requis
@require_POST
def rejeter_proforma(request, pk):
    if not _peut_approuver(request.user):
        messages.error(request, 'Droits insuffisants pour rejeter une proforma.')
        return redirect('facturation:detail-proforma', pk=pk)

    pf, entreprise, admin = _charger_proforma(request, pk)

    if pf.statut != 'EN_ATTENTE':
        messages.warning(request, 'Seule une proforma en attente peut être rejetée.')
        return redirect('facturation:detail-proforma', pk=pk)

    form = DecisionProformaForm(request.POST)
    if form.is_valid():
        pf.statut = 'ANNULEE'
        pf.approuve_par = request.user
        pf.date_approbation = timezone.now()
        pf.commentaire_manager = form.cleaned_data.get('commentaire_manager') or ''
        pf.save(update_fields=['statut', 'approuve_par', 'date_approbation', 'commentaire_manager'])
        messages.warning(request, f'Proforma {pf.numero_proforma} rejetée.')
    else:
        messages.error(request, 'Erreur lors de la validation du formulaire.')

    return redirect('facturation:detail-proforma', pk=pk)


# ─────────────────────────────────────────────
# Conversion en facture brouillon
# ─────────────────────────────────────────────

@login_requis
@require_POST
def convertir_en_brouillon(request, pk):
    pf, entreprise, admin = _charger_proforma(request, pk)

    if pf.statut != 'ACCEPTEE':
        messages.error(request, 'Seule une proforma approuvée peut être convertie en facture.')
        return redirect('facturation:detail-proforma', pk=pk)

    if pf.facture_definitive_id:
        messages.warning(request, 'Cette proforma a déjà été convertie.')
        return redirect('facturation:detail-facture', pk=pf.facture_definitive_id)

    lignes = list(pf.lignes.select_related('produit').order_by('pk'))
    if not lignes:
        messages.error(request, 'Impossible de convertir une proforma sans lignes.')
        return redirect('facturation:detail-proforma', pk=pk)

    # On cherche un point de vente de la branche pour la facture
    pv = pf.branche.points_vente.filter(est_actif=True).first()
    if not pv:
        messages.error(
            request,
            'Aucun point de vente actif sur cette branche. '
            'Associez un PDV à la branche avant de convertir.',
        )
        return redirect('facturation:detail-proforma', pk=pk)

    devise = pf.devise

    try:
        with transaction.atomic():
            facture = Facture(
                point_vente=pv,
                vendeur=request.user,
                client=pf.client,
                devise=devise,
                taux_echange_appliqué=devise.taux_echange,
                mode_paiement='CASH',
                statut='BROUILLON',
                total_ht=Decimal('0'),
                total_tva=Decimal('0'),
                total_ttc=Decimal('0'),
                montant_paye=Decimal('0'),
                reste_a_payer=Decimal('0'),
            )
            facture.save()

            # Les lignes de la proforma sont copiées SANS consommation de stock.
            # La consommation de stock aura lieu lors de la validation de la facture.
            from stock.services import repartir_quantite_facture_sur_lots
            from .pricing import taux_tva_actif

            for ligne in lignes:
                produit = ligne.produit
                pu = ligne.prix_unitaire_ht
                q_tot = ligne.quantite

                try:
                    chunks = repartir_quantite_facture_sur_lots(pv, produit, q_tot)
                except ValueError:
                    # Pas assez de stock : on crée quand même mais on avertit
                    chunks = []
                    messages.warning(
                        request,
                        f'Stock insuffisant pour « {produit.nom} » sur ce PDV. '
                        f'La ligne est omise — vérifiez le stock avant de valider la facture.',
                    )

                for mv, q_tranche in chunks:
                    ht = pu * Decimal(str(q_tranche))
                    tva = montant_tva_sur_ht(ht, produit.tva_taux) if taux_tva_actif(produit.tva_taux) else Decimal('0')
                    LigneFacture.objects.create(
                        facture=facture,
                        mouvement_stock=mv,
                        produit=produit,
                        quantite=q_tranche,
                        prix_unitaire_ht=pu,
                        tva_montant=tva,
                        remise=Decimal('0'),
                    )

            facture.recalcul_totaux()
            facture.save(update_fields=['total_ht', 'total_tva', 'total_ttc', 'reste_a_payer'])

            pf.facture_definitive = facture
            pf.save(update_fields=['facture_definitive'])

    except Exception as exc:
        messages.error(request, f'Erreur lors de la conversion : {exc}')
        return redirect('facturation:detail-proforma', pk=pk)

    messages.success(
        request,
        f'Proforma {pf.numero_proforma} convertie en facture brouillon {facture.numero_facture}.',
    )
    return redirect('facturation:detail-facture', pk=facture.pk)


# ─────────────────────────────────────────────
# Suppression (brouillon uniquement)
# ─────────────────────────────────────────────

@login_requis
@require_POST
def supprimer_proforma(request, pk):
    """Suppression définitive — uniquement si statut BROUILLON, accessible à tous les ayants-droit."""
    pf, entreprise, admin = _charger_proforma(request, pk)

    if pf.statut != 'BROUILLON':
        messages.error(request, 'Seule une proforma en brouillon peut être supprimée.')
        return redirect('facturation:detail-proforma', pk=pk)

    numero = pf.numero_proforma
    pf.delete()
    messages.success(request, f'Proforma {numero} supprimée.')
    return redirect('facturation:liste-proformas')


# ─────────────────────────────────────────────
# Soumission au manager
# ─────────────────────────────────────────────

@login_requis
@require_POST
def soumettre_proforma(request, pk):
    """BROUILLON → EN_ATTENTE : le vendeur soumet la proforma pour approbation."""
    pf, entreprise, admin = _charger_proforma(request, pk)

    if not (admin or pf.vendeur_id == request.user.pk):
        messages.error(request, 'Action non autorisée.')
        return redirect('facturation:detail-proforma', pk=pk)

    if pf.statut != 'BROUILLON':
        messages.warning(request, 'Seule une proforma en brouillon peut être soumise.')
        return redirect('facturation:detail-proforma', pk=pk)

    if not pf.lignes.exists():
        messages.error(request, 'Ajoutez au moins une ligne avant de soumettre.')
        return redirect('facturation:detail-proforma', pk=pk)

    pf.statut = 'EN_ATTENTE'
    pf.soumis_le = timezone.now()
    pf.save(update_fields=['statut', 'soumis_le'])
    messages.success(request, f'Proforma {pf.numero_proforma} soumise au manager pour approbation.')
    return redirect('facturation:detail-proforma', pk=pk)


# ─────────────────────────────────────────────
# Impression (managers uniquement)
# ─────────────────────────────────────────────

@login_requis
def imprimer_proforma(request, pk):
    """Impression réservée aux managers (approuver_facture_proforma) et admins."""
    pf, entreprise, admin = _charger_proforma(request, pk)

    if not admin and not _peut_approuver(request.user):
        messages.error(request, 'L\'impression de la proforma est réservée aux managers.')
        return redirect('facturation:detail-proforma', pk=pk)

    lignes = pf.lignes.select_related('produit').order_by('pk')
    ent = pf.branche.entreprise
    return render(request, 'facturation/proforma/imprimer_proforma.html', {
        'proforma': pf,
        'lignes': lignes,
        'entreprise': ent,
    })
