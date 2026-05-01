"""Vues facturation — brouillon, lignes sur mouvements stock, validation avec déstockage."""

from decimal import Decimal

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from utilisateur.decorators import login_requis

from entreprise.models import Devise
from stock.access import get_entreprise_utilisateur, utilisateur_est_admin
from stock.services import consommer_mouvements_facture

from .forms import AjoutLigneFactureForm, FactureBrouillonForm
from .models import Facture, LigneFacture


def _peut_vendre_sur_pv(user, pv, admin):
    if admin or user.is_superuser:
        return True
    return user.a_acces_point_vente(pv.pk, 'peut_vendre')


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
    return qs.filter(point_vente__branche__entreprise=entreprise)


def _charger_facture(request, pk):
    entreprise = get_entreprise_utilisateur(request.user)
    admin = utilisateur_est_admin(request.user)
    fact = get_object_or_404(
        _liste_factures_scope(request.user, entreprise, admin).select_related('point_vente'),
        pk=pk,
    )
    if not _peut_vendre_sur_pv(request.user, fact.point_vente, admin):
        return None, redirect('facturation:liste-factures')
    return fact, None


@login_requis
def liste_factures(request):
    entreprise = get_entreprise_utilisateur(request.user)
    admin = utilisateur_est_admin(request.user)
    qs = _liste_factures_scope(request.user, entreprise, admin)[:500]
    return render(
        request,
        'facturation/liste_factures.html',
        {'factures': qs, 'actif': 'vente_factures'},
    )


@login_requis
def nouvelle_facture(request):
    entreprise = get_entreprise_utilisateur(request.user)
    admin = utilisateur_est_admin(request.user)
    if not entreprise and not admin:
        messages.error(request, 'Aucune entreprise associée.')
        return redirect('entreprise:dashboard')

    if request.method == 'POST':
        form = FactureBrouillonForm(request.POST, entreprise=entreprise)
        if form.is_valid():
            pv = form.cleaned_data['point_vente']
            if not _peut_vendre_sur_pv(request.user, pv, admin):
                messages.error(request, 'Vous ne pouvez pas vendre sur ce point de vente.')
                return render(
                    request,
                    'facturation/facture_nouvelle.html',
                    {'form': form, 'actif': 'vente_factures'},
                )
            f = form.save(commit=False)
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
        form = FactureBrouillonForm(entreprise=entreprise)
        if entreprise:
            dev = Devise.objects.filter(entreprise=entreprise, est_principale=True).first()
            if dev:
                form.fields['devise'].initial = dev.pk
                form.fields['taux_echange_appliqué'].initial = dev.taux_echange

    return render(
        request,
        'facturation/facture_nouvelle.html',
        {'form': form, 'actif': 'vente_factures'},
    )


@login_requis
def detail_facture(request, pk):
    fact, redir = _charger_facture(request, pk)
    if redir:
        return redir

    ligne_form = AjoutLigneFactureForm(point_vente=fact.point_vente)
    lignes = fact.lignes.select_related('mouvement_stock', 'produit').order_by('pk')

    return render(
        request,
        'facturation/detail_facture.html',
        {
            'facture': fact,
            'lignes': lignes,
            'ligne_form': ligne_form,
            'actif': 'vente_factures',
        },
    )


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
        mv = form.cleaned_data['mouvement_stock']
        q = form.cleaned_data['quantite']
        if mv.quantite_active < q:
            messages.error(request, 'Quantité supérieure au disponible sur ce mouvement.')
            return redirect('facturation:detail-facture', pk=pk)
        pu = form.cleaned_data.get('prix_unitaire_ht')
        if pu is None:
            pu = mv.produit.prix_vente_ht
        pu = Decimal(str(pu))
        ht = pu * Decimal(str(q))
        taux = Decimal(str(mv.produit.tva_taux))
        tva = (ht * taux / Decimal('100')).quantize(Decimal('0.01'))
        LigneFacture.objects.create(
            facture=fact,
            mouvement_stock=mv,
            produit_id=mv.produit_id,
            quantite=q,
            prix_unitaire_ht=pu,
            tva_montant=tva,
            remise=Decimal('0'),
        )
        fact.recalcul_totaux()
        fact.save(update_fields=['total_ht', 'total_tva', 'total_ttc', 'reste_a_payer'])
        messages.success(request, 'Ligne ajoutée.')
    else:
        messages.error(request, 'Ligne invalide.')
    return redirect('facturation:detail-facture', pk=pk)


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
def valider_facture(request, pk):
    from django.db import transaction
    from datetime import date
    from finance.posting import poster_cout_stock_vente

    fact, redir = _charger_facture(request, pk)
    if redir:
        return redir
    if fact.statut != 'BROUILLON':
        messages.warning(request, 'Cette facture n’est pas un brouillon.')
        return redirect('facturation:detail-facture', pk=pk)
    if not fact.lignes.exists():
        messages.error(request, 'Ajoutez au moins une ligne.')
        return redirect('facturation:detail-facture', pk=pk)

    ent = fact.point_vente.branche.entreprise
    try:
        with transaction.atomic():
            montant_cos = consommer_mouvements_facture(fact, request.user)
            fact.statut = 'VALIDEE'
            fact.montant_paye = fact.total_ttc
            fact.reste_a_payer = Decimal('0')
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
        messages.success(request, 'Facture validée et stock mis à jour.')
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect('facturation:detail-facture', pk=pk)
