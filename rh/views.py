"""Vues module RH — hub, employés, départements, contrats, avances, congés, présences."""

import calendar
from decimal import Decimal

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from entreprise.models import Branche, Devise, PointVente
from stock.access import get_entreprise_utilisateur, utilisateur_est_admin
from utilisateur.acces_metier import utilisateur_peut_permission
from utilisateur.decorators import login_requis

from .models import AvanceSalaire, BulletinPaie, Conge, Contrat, Departement, Employe, LigneBulletin, Presence
from .services import generer_bulletin, recalculer_totaux


# ─────────────────────────────────────────────
# Hub
# ─────────────────────────────────────────────

@login_requis
def hub_rh(request):
    entreprise = get_entreprise_utilisateur(request.user)
    admin = utilisateur_est_admin(request.user)

    qs_avances = AvanceSalaire.objects.all()
    qs_employes = Employe.objects.all()
    if admin:
        if entreprise:
            qs_avances = qs_avances.filter(employe__branche__entreprise=entreprise)
            qs_employes = qs_employes.filter(branche__entreprise=entreprise)
    else:
        branche = getattr(request.user, 'branche', None)
        if branche:
            qs_avances = qs_avances.filter(employe__branche=branche)
            qs_employes = qs_employes.filter(branche=branche)
        else:
            qs_avances = AvanceSalaire.objects.none()
            qs_employes = Employe.objects.none()

    nb_conges_en_attente     = Conge.objects.filter(employe__in=qs_employes, statut='DEMANDE').count()
    nb_bulletins_a_valider   = BulletinPaie.objects.filter(employe__in=qs_employes, statut='BROUILLON').count()

    return render(request, 'rh/hub.html', {
        'nb_avances_en_attente':  qs_avances.filter(statut='DEMANDE').count(),
        'nb_employes_actifs':     qs_employes.filter(est_actif=True).count(),
        'nb_conges_en_attente':   nb_conges_en_attente,
        'nb_bulletins_a_valider': nb_bulletins_a_valider,
    })


# ─────────────────────────────────────────────
# Helpers partagés
# ─────────────────────────────────────────────

def _peut_approuver(user):
    return utilisateur_peut_permission(user, 'acces_module_rh')


def _scope_employes(user, entreprise, admin):
    qs = Employe.objects.select_related('branche__entreprise')
    if admin:
        if entreprise:
            return qs.filter(branche__entreprise=entreprise)
        return qs
    if not entreprise:
        return Employe.objects.none()
    branche = getattr(user, 'branche', None)
    if not branche:
        return Employe.objects.none()
    return qs.filter(branche=branche)


def _scope_departements(user, entreprise, admin):
    qs = Departement.objects.select_related('branche', 'responsable')
    if admin:
        if entreprise:
            return qs.filter(branche__entreprise=entreprise)
        return qs
    if not entreprise:
        return Departement.objects.none()
    branche = getattr(user, 'branche', None)
    if not branche:
        return Departement.objects.none()
    return qs.filter(branche=branche)


def _scope_avances(user, entreprise, admin):
    qs = AvanceSalaire.objects.select_related(
        'employe', 'devise', 'point_vente',
        'demande_par', 'approuve_par', 'decaisse_par',
    ).order_by('-date_demande')

    if admin:
        if entreprise:
            return qs.filter(employe__branche__entreprise=entreprise)
        return qs

    if not entreprise:
        return AvanceSalaire.objects.none()

    branche = getattr(user, 'branche', None)
    if not branche:
        return AvanceSalaire.objects.none()
    return qs.filter(employe__branche=branche)


# ─────────────────────────────────────────────
# Employés — Liste
# ─────────────────────────────────────────────

@login_requis
def liste_employes(request):
    entreprise = get_entreprise_utilisateur(request.user)
    admin = utilisateur_est_admin(request.user)
    qs = _scope_employes(request.user, entreprise, admin)

    statut = request.GET.get('statut', 'actif')
    if statut == 'actif':
        qs = qs.filter(est_actif=True)
    elif statut == 'inactif':
        qs = qs.filter(est_actif=False)

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(nom__icontains=q) | Q(prenom__icontains=q) | Q(matricule__icontains=q))

    return render(request, 'rh/employes/liste.html', {
        'employes': qs.prefetch_related('contrats__departement').order_by('nom', 'prenom'),
        'q': q,
        'filtre_statut': statut,
    })


# ─────────────────────────────────────────────
# Employés — Détail
# ─────────────────────────────────────────────

@login_requis
def detail_employe(request, pk):
    employe = get_object_or_404(
        Employe.objects.select_related('branche__entreprise', 'user_compte'),
        pk=pk,
    )
    contrats = employe.contrats.select_related('departement', 'devise').order_by('-date_debut')
    contrat_actuel = contrats.filter(est_actuel=True).first()
    avances = employe.avances_salaire.select_related('devise', 'point_vente').order_by('-date_demande')[:10]
    conges  = employe.conges.order_by('-date_demande')[:10]
    return render(request, 'rh/employes/detail.html', {
        'employe':        employe,
        'contrats':       contrats,
        'contrat_actuel': contrat_actuel,
        'avances':        avances,
        'conges':         conges,
    })


# ─────────────────────────────────────────────
# Employés — Création / Modification
# ─────────────────────────────────────────────

@login_requis
def creer_employe(request):
    entreprise = get_entreprise_utilisateur(request.user)
    admin = utilisateur_est_admin(request.user)

    if admin and entreprise:
        branches = Branche.objects.filter(entreprise=entreprise, est_actif=True)
    elif not admin:
        branche = getattr(request.user, 'branche', None)
        branches = Branche.objects.filter(pk=branche.pk) if branche else Branche.objects.none()
    else:
        branches = Branche.objects.none()

    if request.method == 'POST':
        erreurs = _valider_employe(request.POST)
        if erreurs:
            for e in erreurs:
                messages.error(request, e)
        else:
            branche_id = request.POST.get('branche')
            if not admin:
                branche = getattr(request.user, 'branche', None)
                branche_id = branche.pk if branche else None

            employe = Employe(
                branche_id=branche_id,
                matricule=request.POST['matricule'].strip(),
                nom=request.POST['nom'].strip().upper(),
                postnom=request.POST.get('postnom', '').strip().upper(),
                prenom=request.POST['prenom'].strip().capitalize(),
                sexe=request.POST['sexe'],
                etat_civil=request.POST['etat_civil'],
                date_naissance=request.POST['date_naissance'],
                telephone=request.POST['telephone'].strip(),
                adresse=request.POST.get('adresse', '').strip(),
                nombre_enfants=int(request.POST.get('nombre_enfants', 0) or 0),
                est_actif=True,
            )
            if request.FILES.get('photo'):
                employe.photo = request.FILES['photo']
            employe.save()
            messages.success(request, f"Employé {employe} créé avec succès.")
            return redirect('rh:detail-employe', pk=employe.pk)

    return render(request, 'rh/employes/form.html', {
        'titre': 'Nouvel employé',
        'action': 'creer',
        'branches': branches,
        'admin': admin,
        'sexe_choices': Employe.SEXE_CHOICES,
        'etat_civil_choices': Employe.ETAT_CIVIL,
    })


@login_requis
def modifier_employe(request, pk):
    entreprise = get_entreprise_utilisateur(request.user)
    admin = utilisateur_est_admin(request.user)
    employe = get_object_or_404(Employe, pk=pk)

    if admin and entreprise:
        branches = Branche.objects.filter(entreprise=entreprise, est_actif=True)
    elif not admin:
        branche = getattr(request.user, 'branche', None)
        branches = Branche.objects.filter(pk=branche.pk) if branche else Branche.objects.none()
    else:
        branches = Branche.objects.none()

    if request.method == 'POST':
        erreurs = _valider_employe(request.POST, instance=employe)
        if erreurs:
            for e in erreurs:
                messages.error(request, e)
        else:
            employe.matricule = request.POST['matricule'].strip()
            employe.nom = request.POST['nom'].strip().upper()
            employe.postnom = request.POST.get('postnom', '').strip().upper()
            employe.prenom = request.POST['prenom'].strip().capitalize()
            employe.sexe = request.POST['sexe']
            employe.etat_civil = request.POST['etat_civil']
            employe.date_naissance = request.POST['date_naissance']
            employe.telephone = request.POST['telephone'].strip()
            employe.adresse = request.POST.get('adresse', '').strip()
            employe.nombre_enfants = int(request.POST.get('nombre_enfants', 0) or 0)
            if request.FILES.get('photo'):
                employe.photo = request.FILES['photo']
            if admin:
                employe.branche_id = request.POST.get('branche')
            employe.save()
            messages.success(request, f"Employé {employe} mis à jour.")
            return redirect('rh:detail-employe', pk=employe.pk)

    return render(request, 'rh/employes/form.html', {
        'titre': f'Modifier — {employe}',
        'action': 'modifier',
        'employe': employe,
        'branches': branches,
        'admin': admin,
        'sexe_choices': Employe.SEXE_CHOICES,
        'etat_civil_choices': Employe.ETAT_CIVIL,
    })


def _valider_employe(data, instance=None):
    erreurs = []
    if not data.get('matricule', '').strip():
        erreurs.append("Le matricule est obligatoire.")
    else:
        qs = Employe.objects.filter(matricule=data['matricule'].strip())
        if instance:
            qs = qs.exclude(pk=instance.pk)
        if qs.exists():
            erreurs.append(f"Le matricule « {data['matricule'].strip()} » est déjà utilisé.")
    if not data.get('nom', '').strip():
        erreurs.append("Le nom est obligatoire.")
    if not data.get('prenom', '').strip():
        erreurs.append("Le prénom est obligatoire.")
    if not data.get('sexe'):
        erreurs.append("Le sexe est obligatoire.")
    if not data.get('etat_civil'):
        erreurs.append("L'état civil est obligatoire.")
    if not data.get('date_naissance'):
        erreurs.append("La date de naissance est obligatoire.")
    if not data.get('telephone', '').strip():
        erreurs.append("Le téléphone est obligatoire.")
    return erreurs


# ─────────────────────────────────────────────
# Employés — Toggle actif / inactif
# ─────────────────────────────────────────────

@login_requis
def imprimer_fiche_employe(request, pk):
    employe = get_object_or_404(
        Employe.objects.select_related('branche__entreprise', 'user_compte'),
        pk=pk,
    )
    contrats = employe.contrats.select_related('departement', 'devise').order_by('-date_debut')
    contrat_actuel = contrats.filter(est_actuel=True).first()
    return render(request, 'rh/employes/imprimer_fiche.html', {
        'employe': employe,
        'contrats': contrats,
        'contrat_actuel': contrat_actuel,
        'entreprise': employe.branche.entreprise,
        'today': timezone.now(),
    })


@login_requis
@require_POST
def toggle_statut_employe(request, pk):
    employe = get_object_or_404(Employe, pk=pk)
    employe.est_actif = not employe.est_actif
    employe.save(update_fields=['est_actif'])
    etat = "activé" if employe.est_actif else "désactivé"
    messages.success(request, f"Employé {employe} {etat}.")
    return redirect('rh:detail-employe', pk=pk)


# ─────────────────────────────────────────────
# Contrats
# ─────────────────────────────────────────────

@login_requis
def nouveau_contrat(request, employe_pk):
    employe = get_object_or_404(Employe, pk=employe_pk)
    entreprise = get_entreprise_utilisateur(request.user)
    admin = utilisateur_est_admin(request.user)

    departements = _scope_departements(request.user, entreprise, admin)
    if entreprise:
        devises = Devise.objects.filter(entreprise=entreprise)
    else:
        devises = Devise.objects.none()

    if request.method == 'POST':
        erreurs = []
        dept_id = request.POST.get('departement')
        type_contrat = request.POST.get('type_contrat')
        titre = request.POST.get('titre_poste', '').strip()
        date_debut = request.POST.get('date_debut')
        date_fin = request.POST.get('date_fin') or None
        salaire_raw = request.POST.get('salaire_base', '').strip()
        devise_id = request.POST.get('devise')
        est_actuel = request.POST.get('est_actuel') == '1'

        if not dept_id:
            erreurs.append("Veuillez sélectionner un département.")
        if not type_contrat:
            erreurs.append("Le type de contrat est obligatoire.")
        if not titre:
            erreurs.append("Le titre du poste est obligatoire.")
        if not date_debut:
            erreurs.append("La date de début est obligatoire.")
        if not salaire_raw:
            erreurs.append("Le salaire de base est obligatoire.")
        else:
            try:
                salaire = Decimal(salaire_raw.replace(',', '.'))
                if salaire < 0:
                    erreurs.append("Le salaire doit être positif.")
            except Exception:
                erreurs.append("Salaire invalide.")
        if not devise_id:
            erreurs.append("Veuillez sélectionner une devise.")

        if erreurs:
            for e in erreurs:
                messages.error(request, e)
        else:
            if est_actuel:
                employe.contrats.filter(est_actuel=True).update(est_actuel=False)

            Contrat.objects.create(
                employe=employe,
                departement_id=dept_id,
                type_contrat=type_contrat,
                titre_poste=titre,
                date_debut=date_debut,
                date_fin=date_fin,
                salaire_base=Decimal(salaire_raw.replace(',', '.')),
                devise_id=devise_id,
                est_actuel=est_actuel,
            )
            messages.success(request, "Contrat enregistré.")
            return redirect('rh:detail-employe', pk=employe.pk)

    return render(request, 'rh/employes/contrat_form.html', {
        'employe': employe,
        'departements': departements,
        'devises': devises,
        'types_contrat': Contrat.TYPES_CONTRAT,
    })


# ─────────────────────────────────────────────
# Départements — Liste
# ─────────────────────────────────────────────

@login_requis
def liste_departements(request):
    entreprise = get_entreprise_utilisateur(request.user)
    admin = utilisateur_est_admin(request.user)
    departements = _scope_departements(request.user, entreprise, admin)
    return render(request, 'rh/departements/liste.html', {
        'departements': departements,
    })


# ─────────────────────────────────────────────
# Départements — Création / Modification
# ─────────────────────────────────────────────

@login_requis
def creer_departement(request):
    entreprise = get_entreprise_utilisateur(request.user)
    admin = utilisateur_est_admin(request.user)

    if admin and entreprise:
        branches = Branche.objects.filter(entreprise=entreprise, est_actif=True)
    elif not admin:
        branche = getattr(request.user, 'branche', None)
        branches = Branche.objects.filter(pk=branche.pk) if branche else Branche.objects.none()
    else:
        branches = Branche.objects.none()

    employes_choices = _scope_employes(request.user, entreprise, admin).filter(est_actif=True)

    if request.method == 'POST':
        nom = request.POST.get('nom', '').strip()
        responsable_id = request.POST.get('responsable') or None
        branche_id = request.POST.get('branche')
        if not admin:
            branche = getattr(request.user, 'branche', None)
            branche_id = branche.pk if branche else None

        if not nom:
            messages.error(request, "Le nom du département est obligatoire.")
        else:
            Departement.objects.create(
                nom=nom,
                branche_id=branche_id,
                responsable_id=responsable_id,
            )
            messages.success(request, f"Département « {nom} » créé.")
            return redirect('rh:liste-departements')

    return render(request, 'rh/departements/form.html', {
        'titre': 'Nouveau département',
        'action': 'creer',
        'branches': branches,
        'admin': admin,
        'employes': employes_choices,
        'exemples_departements': ['Finance', 'Logistique', 'Commercial', 'RH', 'Informatique', 'Production', 'Achats', 'Direction'],
    })


@login_requis
def modifier_departement(request, pk):
    entreprise = get_entreprise_utilisateur(request.user)
    admin = utilisateur_est_admin(request.user)
    departement = get_object_or_404(Departement, pk=pk)

    if admin and entreprise:
        branches = Branche.objects.filter(entreprise=entreprise, est_actif=True)
    elif not admin:
        branche = getattr(request.user, 'branche', None)
        branches = Branche.objects.filter(pk=branche.pk) if branche else Branche.objects.none()
    else:
        branches = Branche.objects.none()

    employes_choices = _scope_employes(request.user, entreprise, admin).filter(est_actif=True)

    if request.method == 'POST':
        nom = request.POST.get('nom', '').strip()
        responsable_id = request.POST.get('responsable') or None

        if not nom:
            messages.error(request, "Le nom du département est obligatoire.")
        else:
            departement.nom = nom
            departement.responsable_id = responsable_id
            if admin:
                departement.branche_id = request.POST.get('branche')
            departement.save()
            messages.success(request, f"Département « {nom} » mis à jour.")
            return redirect('rh:liste-departements')

    return render(request, 'rh/departements/form.html', {
        'titre': f'Modifier — {departement.nom}',
        'action': 'modifier',
        'departement': departement,
        'branches': branches,
        'admin': admin,
        'employes': employes_choices,
        'exemples_departements': ['Finance', 'Logistique', 'Commercial', 'RH', 'Informatique', 'Production', 'Achats', 'Direction'],
    })


# ─────────────────────────────────────────────
# Avances sur salaire — Liste
# ─────────────────────────────────────────────

@login_requis
def liste_avances(request):
    entreprise = get_entreprise_utilisateur(request.user)
    admin = utilisateur_est_admin(request.user)
    qs = _scope_avances(request.user, entreprise, admin)

    statut = request.GET.get('statut', '')
    employe_id = request.GET.get('employe', '')
    if statut:
        qs = qs.filter(statut=statut)
    if employe_id:
        qs = qs.filter(employe_id=employe_id)

    employes = _scope_employes(request.user, entreprise, admin).filter(est_actif=True)

    return render(request, 'rh/avances/liste.html', {
        'avances': qs,
        'statuts': AvanceSalaire.STATUTS,
        'filtre_statut': statut,
        'filtre_employe': employe_id,
        'employes': employes,
        'peut_approuver': _peut_approuver(request.user),
    })


# ─────────────────────────────────────────────
# Avances sur salaire — Création
# ─────────────────────────────────────────────

@login_requis
def nouvelle_avance(request):
    entreprise = get_entreprise_utilisateur(request.user)
    admin = utilisateur_est_admin(request.user)

    employes = _scope_employes(request.user, entreprise, admin).filter(est_actif=True)

    if entreprise:
        devises = Devise.objects.filter(entreprise=entreprise)
        points_vente = PointVente.objects.filter(branche__entreprise=entreprise, est_actif=True)
    else:
        devises = Devise.objects.none()
        points_vente = PointVente.objects.none()

    if request.method == 'POST':
        employe_id  = request.POST.get('employe')
        pv_id       = request.POST.get('point_vente')
        montant_raw = request.POST.get('montant', '').strip()
        devise_id   = request.POST.get('devise')
        motif       = request.POST.get('motif', '').strip()

        erreurs = []
        if not employe_id:
            erreurs.append("Veuillez sélectionner un employé.")
        if not pv_id:
            erreurs.append("Veuillez sélectionner un point de vente.")
        if not montant_raw:
            erreurs.append("Le montant est obligatoire.")
        else:
            try:
                montant = Decimal(montant_raw.replace(',', '.'))
                if montant <= 0:
                    erreurs.append("Le montant doit être positif.")
            except Exception:
                erreurs.append("Montant invalide.")
        if not devise_id:
            erreurs.append("Veuillez sélectionner une devise.")

        if erreurs:
            for e in erreurs:
                messages.error(request, e)
        else:
            employe   = get_object_or_404(Employe, pk=employe_id)
            pv        = get_object_or_404(PointVente, pk=pv_id)
            devise    = get_object_or_404(Devise, pk=devise_id)

            avance = AvanceSalaire.objects.create(
                employe     = employe,
                point_vente = pv,
                montant     = Decimal(montant_raw.replace(',', '.')),
                devise      = devise,
                motif       = motif,
                statut      = 'DEMANDE',
                demande_par = request.user,
            )
            messages.success(request, f"Avance {avance.numero} enregistrée — en attente d'approbation.")
            return redirect('rh:liste-avances')

    return render(request, 'rh/avances/nouvelle.html', {
        'employes':     employes,
        'devises':      devises,
        'points_vente': points_vente,
    })


# ─────────────────────────────────────────────
# Avances sur salaire — Détail
# ─────────────────────────────────────────────

@login_requis
def detail_avance(request, pk):
    avance = get_object_or_404(
        AvanceSalaire.objects.select_related(
            'employe', 'devise', 'point_vente',
            'demande_par', 'approuve_par', 'decaisse_par',
            'transaction_caisse',
        ),
        pk=pk,
    )
    return render(request, 'rh/avances/detail.html', {
        'avance': avance,
        'peut_approuver': _peut_approuver(request.user),
    })


# ─────────────────────────────────────────────
# Avances sur salaire — Approbation / Rejet
# ─────────────────────────────────────────────

@login_requis
@require_POST
def approuver_avance(request, pk):
    avance = get_object_or_404(AvanceSalaire, pk=pk)

    if not _peut_approuver(request.user):
        messages.error(request, "Vous n'avez pas la permission d'approuver les avances.")
        return redirect('rh:detail-avance', pk=pk)

    if avance.statut != 'DEMANDE':
        messages.warning(request, "Cette avance n'est plus en attente d'approbation.")
        return redirect('rh:detail-avance', pk=pk)

    action = request.POST.get('action')
    note   = request.POST.get('note_approbation', '').strip()

    if action == 'approuver':
        avance.statut           = 'APPROUVEE'
        avance.approuve_par     = request.user
        avance.date_approbation = timezone.now()
        avance.note_approbation = note
        avance.save(update_fields=['statut', 'approuve_par', 'date_approbation', 'note_approbation'])
        messages.success(request, f"Avance {avance.numero} approuvée.")
    elif action == 'rejeter':
        avance.statut           = 'REJETEE'
        avance.approuve_par     = request.user
        avance.date_approbation = timezone.now()
        avance.note_approbation = note
        avance.save(update_fields=['statut', 'approuve_par', 'date_approbation', 'note_approbation'])
        messages.warning(request, f"Avance {avance.numero} rejetée.")
    else:
        messages.error(request, "Action inconnue.")

    return redirect('rh:detail-avance', pk=pk)


# ─────────────────────────────────────────────
# Avances sur salaire — Décaissement
# ─────────────────────────────────────────────

@login_requis
@require_POST
def decaisser_avance(request, pk):
    avance = get_object_or_404(AvanceSalaire, pk=pk)
    # Permet à la page caisse de récupérer la main après l'action
    next_url = request.POST.get('next', '')

    def _redirect_back():
        from django.utils.http import url_has_allowed_host_and_scheme
        if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
            return redirect(next_url)
        return redirect('rh:detail-avance', pk=pk)

    if avance.statut != 'APPROUVEE':
        messages.error(request, "L'avance doit être approuvée avant d'être décaissée.")
        return _redirect_back()

    from caisse.services import enregistrer_decaissement_avance
    txn = enregistrer_decaissement_avance(avance, request.user)

    if txn is None:
        messages.error(
            request,
            f"Aucune session de caisse ouverte sur « {avance.point_vente.nom} ». "
            "Ouvrez une session avant de décaisser."
        )
        return _redirect_back()

    avance.statut             = 'DECAISSEE'
    avance.decaisse_par       = request.user
    avance.date_decaissement  = timezone.now()
    avance.transaction_caisse = txn
    avance.save(update_fields=[
        'statut', 'decaisse_par', 'date_decaissement', 'transaction_caisse'
    ])
    messages.success(
        request,
        f"Avance {avance.numero} décaissée — transaction {txn.numero} enregistrée en caisse."
    )
    return _redirect_back()


# ─────────────────────────────────────────────
# Avances sur salaire — Remboursement
# ─────────────────────────────────────────────

@login_requis
@require_POST
def rembourser_avance(request, pk):
    avance = get_object_or_404(AvanceSalaire, pk=pk)

    if avance.statut != 'DECAISSEE':
        messages.error(request, "Seules les avances décaissées peuvent être marquées comme remboursées.")
        return redirect('rh:detail-avance', pk=pk)

    avance.statut = 'REMBOURSEE'
    avance.save(update_fields=['statut'])
    messages.success(request, f"Avance {avance.numero} marquée comme remboursée.")
    return redirect('rh:detail-avance', pk=pk)


# ─────────────────────────────────────────────────────────────────────────────
# CONGÉS
# ─────────────────────────────────────────────────────────────────────────────

def _scope_conges(user, entreprise, admin):
    """Filtre les congés selon le périmètre de l'utilisateur."""
    employes = _scope_employes(user, entreprise, admin)
    return Conge.objects.filter(employe__in=employes)


@login_requis
def liste_conges(request):
    entreprise = get_entreprise_utilisateur(request.user)
    admin = utilisateur_est_admin(request.user)

    qs = _scope_conges(request.user, entreprise, admin)

    # Filtres
    statut = request.GET.get('statut', '')
    type_c = request.GET.get('type_conge', '')
    q      = request.GET.get('q', '')
    mois   = request.GET.get('mois', '')

    if statut:
        qs = qs.filter(statut=statut)
    if type_c:
        qs = qs.filter(type_conge=type_c)
    if q:
        qs = qs.filter(
            Q(employe__nom__icontains=q) | Q(employe__prenom__icontains=q)
        )
    if mois:
        try:
            annee, m = mois.split('-')
            qs = qs.filter(date_debut__year=int(annee), date_debut__month=int(m))
        except (ValueError, AttributeError):
            pass

    qs = qs.select_related('employe', 'demande_par', 'approuve_par')

    # Stats rapides
    base_conges  = _scope_conges(request.user, entreprise, admin)
    nb_demandes  = base_conges.filter(statut='DEMANDE').count()
    nb_approuves = base_conges.filter(
        statut='APPROUVEE',
        date_fin__gte=timezone.now().date()
    ).count()

    return render(request, 'rh/conges/liste.html', {
        'conges':       qs,
        'nb_demandes':  nb_demandes,
        'nb_approuves': nb_approuves,
        'statut':       statut,
        'type_conge':   type_c,
        'q':            q,
        'mois':         mois,
        'statuts':      Conge.STATUTS,
        'types_conge':  Conge.TYPE_CONGE,
    })


@login_requis
def nouvelle_demande_conge(request, employe_pk=None):
    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    employes   = _scope_employes(request.user, entreprise, admin)

    employe_initial = None
    if employe_pk:
        employe_initial = get_object_or_404(employes, pk=employe_pk)

    if request.method == 'POST':
        employe_id = request.POST.get('employe')
        type_conge = request.POST.get('type_conge')
        date_debut = request.POST.get('date_debut')
        date_fin   = request.POST.get('date_fin')
        motif      = request.POST.get('motif', '').strip()

        erreurs = []
        if not employe_id:
            erreurs.append("L'employé est requis.")
        if not type_conge:
            erreurs.append("Le type de congé est requis.")
        if not date_debut:
            erreurs.append("La date de début est requise.")
        if not date_fin:
            erreurs.append("La date de fin est requise.")

        employe = None
        if employe_id:
            try:
                employe = employes.get(pk=employe_id)
            except Employe.DoesNotExist:
                erreurs.append("Employé introuvable.")

        if not erreurs and date_debut and date_fin:
            from datetime import date as _date
            try:
                if _date.fromisoformat(date_debut) > _date.fromisoformat(date_fin):
                    erreurs.append("La date de fin doit être après la date de début.")
            except ValueError:
                erreurs.append("Format de date invalide.")

        if erreurs:
            for e in erreurs:
                messages.error(request, e)
        else:
            from datetime import date as _date
            d_debut = _date.fromisoformat(date_debut)
            d_fin   = _date.fromisoformat(date_fin)
            conge = Conge.objects.create(
                employe     = employe,
                type_conge  = type_conge,
                date_debut  = d_debut,
                date_fin    = d_fin,
                motif       = motif,
                statut      = 'DEMANDE',
                demande_par = request.user,
            )
            messages.success(
                request,
                f"Demande de congé pour {employe} enregistrée ({conge.nb_jours} jour(s))."
            )
            return redirect('rh:detail-conge', pk=conge.pk)

    return render(request, 'rh/conges/form.html', {
        'employes':       employes.filter(est_actif=True),
        'employe_initial':employe_initial,
        'types_conge':    Conge.TYPE_CONGE,
        'titre':          'Nouvelle demande de congé',
    })


@login_requis
def detail_conge(request, pk):
    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    conge      = get_object_or_404(_scope_conges(request.user, entreprise, admin), pk=pk)

    can_approuver = admin or utilisateur_peut_permission(request.user, 'approuver_conge')

    return render(request, 'rh/conges/detail.html', {
        'conge':         conge,
        'can_approuver': can_approuver,
    })


@login_requis
@require_POST
def approuver_conge(request, pk):
    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    conge      = get_object_or_404(_scope_conges(request.user, entreprise, admin), pk=pk)
    profil     = request.user

    if not (admin or utilisateur_peut_permission(request.user, 'approuver_conge')):
        messages.error(request, "Vous n'êtes pas autorisé à approuver des congés.")
        return redirect('rh:detail-conge', pk=pk)

    if conge.statut != 'DEMANDE':
        messages.error(request, "Seules les demandes en attente peuvent être approuvées.")
        return redirect('rh:detail-conge', pk=pk)

    note = request.POST.get('note_approbation', '').strip()

    conge.statut          = 'APPROUVEE'
    conge.approuve_par    = profil
    conge.date_approbation= timezone.now()
    conge.note_approbation= note
    conge.save(update_fields=['statut', 'approuve_par', 'date_approbation', 'note_approbation'])

    # Créer automatiquement des entrées de présence "CONGE"
    from datetime import timedelta
    current = conge.date_debut
    while current <= conge.date_fin:
        Presence.objects.update_or_create(
            employe=conge.employe,
            date=current,
            defaults={'statut': 'CONGE', 'note': f"Congé #{conge.pk}"},
        )
        current += timedelta(days=1)

    messages.success(
        request,
        f"Congé de {conge.employe} approuvé ({conge.nb_jours} jour(s)). "
        f"Présences mises à jour automatiquement."
    )
    return redirect('rh:detail-conge', pk=pk)


@login_requis
@require_POST
def rejeter_conge(request, pk):
    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    conge      = get_object_or_404(_scope_conges(request.user, entreprise, admin), pk=pk)
    profil     = request.user

    if not (admin or utilisateur_peut_permission(request.user, 'approuver_conge')):
        messages.error(request, "Vous n'êtes pas autorisé à rejeter des congés.")
        return redirect('rh:detail-conge', pk=pk)

    if conge.statut != 'DEMANDE':
        messages.error(request, "Seules les demandes en attente peuvent être rejetées.")
        return redirect('rh:detail-conge', pk=pk)

    note = request.POST.get('note_approbation', '').strip()

    conge.statut          = 'REJETEE'
    conge.approuve_par    = profil
    conge.date_approbation= timezone.now()
    conge.note_approbation= note
    conge.save(update_fields=['statut', 'approuve_par', 'date_approbation', 'note_approbation'])

    messages.warning(request, f"Demande de congé de {conge.employe} rejetée.")
    return redirect('rh:detail-conge', pk=pk)


@login_requis
@require_POST
def annuler_conge(request, pk):
    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    conge      = get_object_or_404(_scope_conges(request.user, entreprise, admin), pk=pk)

    if conge.statut not in ('DEMANDE', 'APPROUVEE'):
        messages.error(request, "Ce congé ne peut plus être annulé.")
        return redirect('rh:detail-conge', pk=pk)

    conge.statut = 'ANNULEE'
    conge.save(update_fields=['statut'])
    messages.success(request, f"Congé de {conge.employe} annulé.")
    return redirect('rh:liste-conges')


# ─────────────────────────────────────────────────────────────────────────────
# PRÉSENCES
# ─────────────────────────────────────────────────────────────────────────────

@login_requis
def tableau_presences(request):
    """Tableau mensuel des présences — une ligne par employé, une colonne par jour."""
    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    employes   = _scope_employes(request.user, entreprise, admin).filter(est_actif=True).order_by('nom', 'prenom')

    # Mois courant (ou via GET)
    today  = timezone.now().date()
    annee  = int(request.GET.get('annee', today.year))
    mois   = int(request.GET.get('mois', today.month))

    # Bornes du mois
    from datetime import date
    _, nb_jours = calendar.monthrange(annee, mois)
    debut_mois  = date(annee, mois, 1)
    fin_mois    = date(annee, mois, nb_jours)
    jours       = list(range(1, nb_jours + 1))
    dates_mois  = [date(annee, mois, j) for j in jours]

    # Pré-charger toutes les présences du mois
    presences_qs = Presence.objects.filter(
        employe__in=employes,
        date__range=(debut_mois, fin_mois),
    )
    # Indexer par (employe_id, day)
    presences_map = {}
    for p in presences_qs:
        presences_map[(p.employe_id, p.date.day)] = p

    # Construire les lignes du tableau
    lignes = []
    for emp in employes:
        row = {'employe': emp, 'jours': []}
        for j, d in zip(jours, dates_mois):
            p = presences_map.get((emp.pk, j))
            row['jours'].append({'presence': p, 'date': d})
        # Stats du mois
        row['nb_presents']  = sum(1 for cell in row['jours'] if cell['presence'] and cell['presence'].statut == 'PRESENT')
        row['nb_absents']   = sum(1 for cell in row['jours'] if cell['presence'] and cell['presence'].statut == 'ABSENT')
        row['nb_retards']   = sum(1 for cell in row['jours'] if cell['presence'] and cell['presence'].statut == 'RETARD')
        row['nb_conges']    = sum(1 for cell in row['jours'] if cell['presence'] and cell['presence'].statut == 'CONGE')
        row['nb_non_saisi'] = sum(1 for cell in row['jours'] if cell['presence'] is None)
        lignes.append(row)

    # Navigation mois précédent / suivant
    if mois == 1:
        mois_prev = (annee - 1, 12)
    else:
        mois_prev = (annee, mois - 1)
    if mois == 12:
        mois_next = (annee + 1, 1)
    else:
        mois_next = (annee, mois + 1)

    noms_mois = ['', 'Janvier','Février','Mars','Avril','Mai','Juin',
                 'Juillet','Août','Septembre','Octobre','Novembre','Décembre']

    return render(request, 'rh/presences/tableau.html', {
        'lignes':      lignes,
        'jours':       jours,
        'dates_mois':  dates_mois,
        'annee':       annee,
        'mois':        mois,
        'nom_mois':    noms_mois[mois],
        'mois_prev':   mois_prev,
        'mois_next':   mois_next,
        'statuts':     Presence.STATUTS,
        'nb_jours':    nb_jours,
    })


@login_requis
def pointer_presence(request, employe_pk):
    """Saisir ou modifier une présence pour un employé à une date donnée."""
    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    employes   = _scope_employes(request.user, entreprise, admin)
    employe    = get_object_or_404(employes, pk=employe_pk)

    today = timezone.now().date()
    date_str = request.GET.get('date', today.isoformat())
    try:
        from datetime import date as _date
        jour = _date.fromisoformat(date_str)
    except ValueError:
        jour = today

    presence, _ = Presence.objects.get_or_create(
        employe=employe,
        date=jour,
        defaults={'statut': 'PRESENT'},
    )

    if request.method == 'POST':
        statut        = request.POST.get('statut', 'PRESENT')
        heure_arrivee = request.POST.get('heure_arrivee') or None
        heure_depart  = request.POST.get('heure_depart') or None
        note          = request.POST.get('note', '').strip()

        presence.statut        = statut
        presence.heure_arrivee = heure_arrivee
        presence.heure_depart  = heure_depart
        presence.note          = note
        presence.save()

        messages.success(
            request,
            f"Présence de {employe} pour le {jour.strftime('%d/%m/%Y')} enregistrée."
        )
        return redirect(reverse('rh:tableau-presences') + f"?annee={jour.year}&mois={jour.month}")

    return render(request, 'rh/presences/pointer.html', {
        'employe':  employe,
        'presence': presence,
        'jour':     jour,
        'statuts':  Presence.STATUTS,
    })


@login_requis
def pointage_rapide(request):
    """Saisie groupée des présences du jour pour tous les employés actifs."""
    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    employes   = _scope_employes(request.user, entreprise, admin).filter(est_actif=True).order_by('nom', 'prenom')
    today    = timezone.now().date()

    # Présences déjà saisies aujourd'hui
    presences_today = {
        p.employe_id: p
        for p in Presence.objects.filter(employe__in=employes, date=today)
    }

    if request.method == 'POST':
        for emp in employes:
            statut        = request.POST.get(f'statut_{emp.pk}', '')
            heure_arrivee = request.POST.get(f'heure_arrivee_{emp.pk}') or None
            heure_depart  = request.POST.get(f'heure_depart_{emp.pk}') or None
            note          = request.POST.get(f'note_{emp.pk}', '').strip()

            if not statut:
                continue

            Presence.objects.update_or_create(
                employe=emp,
                date=today,
                defaults={
                    'statut':        statut,
                    'heure_arrivee': heure_arrivee,
                    'heure_depart':  heure_depart,
                    'note':          note,
                },
            )
        messages.success(request, f"Présences du {today.strftime('%d/%m/%Y')} enregistrées.")
        return redirect(reverse('rh:tableau-presences') + f"?annee={today.year}&mois={today.month}")

    lignes = []
    for emp in employes:
        lignes.append({
            'employe':  emp,
            'presence': presences_today.get(emp.pk),
        })

    return render(request, 'rh/presences/pointage_rapide.html', {
        'lignes':  lignes,
        'today':   today,
        'statuts': Presence.STATUTS,
    })


# ─────────────────────────────────────────────────────────────────────────────
# BULLETINS DE PAIE
# ─────────────────────────────────────────────────────────────────────────────

def _scope_bulletins(user, entreprise, admin):
    employes = _scope_employes(user, entreprise, admin)
    return BulletinPaie.objects.filter(employe__in=employes)


@login_requis
def liste_bulletins(request):
    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    qs         = _scope_bulletins(request.user, entreprise, admin)

    statut    = request.GET.get('statut', '')
    mois_str  = request.GET.get('mois', '')
    emp_id    = request.GET.get('employe', '')

    if statut:
        qs = qs.filter(statut=statut)
    if emp_id:
        qs = qs.filter(employe_id=emp_id)
    if mois_str:
        try:
            annee, mois = mois_str.split('-')
            qs = qs.filter(periode_annee=int(annee), periode_mois=int(mois))
        except (ValueError, AttributeError):
            pass

    qs = qs.select_related('employe', 'devise', 'contrat')

    employes = _scope_employes(request.user, entreprise, admin).filter(est_actif=True)

    return render(request, 'rh/bulletins/liste.html', {
        'bulletins':    qs,
        'statuts':      BulletinPaie.STATUTS,
        'statut':       statut,
        'mois_str':     mois_str,
        'employe_id':   emp_id,
        'employes':     employes,
        'nb_brouillons': _scope_bulletins(request.user, entreprise, admin).filter(statut='BROUILLON').count(),
        'nb_valides':    _scope_bulletins(request.user, entreprise, admin).filter(statut='VALIDE').count(),
    })


@login_requis
def nouveau_bulletin(request):
    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    employes   = _scope_employes(request.user, entreprise, admin).filter(est_actif=True)

    today = timezone.now().date()
    erreur = None

    if request.method == 'POST':
        employe_id    = request.POST.get('employe')
        mois          = request.POST.get('mois')
        annee         = request.POST.get('annee')
        jours_ouv     = request.POST.get('jours_ouvrables', '26')

        try:
            employe       = employes.get(pk=employe_id)
            mois_int      = int(mois)
            annee_int     = int(annee)
            jours_ouv_int = int(jours_ouv) if jours_ouv else 26

            bulletin = generer_bulletin(
                employe       = employe,
                mois          = mois_int,
                annee         = annee_int,
                cree_par      = request.user,
                jours_ouvrables = jours_ouv_int,
            )
            messages.success(
                request,
                f"Bulletin {bulletin.numero} généré pour {employe} — "
                f"{bulletin.nom_mois} {annee_int}."
            )
            return redirect('rh:detail-bulletin', pk=bulletin.pk)

        except Employe.DoesNotExist:
            erreur = "Employé introuvable."
        except ValueError as e:
            erreur = str(e)

        if erreur:
            messages.error(request, erreur)

    return render(request, 'rh/bulletins/form.html', {
        'employes': employes.order_by('nom', 'prenom'),
        'today':    today,
        'annees':   range(today.year - 2, today.year + 1),
        'mois_choices': [
            (1,'Janvier'),(2,'Février'),(3,'Mars'),(4,'Avril'),
            (5,'Mai'),(6,'Juin'),(7,'Juillet'),(8,'Août'),
            (9,'Septembre'),(10,'Octobre'),(11,'Novembre'),(12,'Décembre'),
        ],
        'mois_defaut':  today.month,
        'annee_defaut': today.year,
    })


@login_requis
def detail_bulletin(request, pk):
    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    bulletin   = get_object_or_404(
        _scope_bulletins(request.user, entreprise, admin)
        .select_related('employe', 'contrat__departement', 'devise',
                        'cree_par', 'valide_par', 'paye_par'),
        pk=pk,
    )
    lignes_avantages = bulletin.lignes.filter(type='AVANTAGE')
    lignes_retenues  = bulletin.lignes.filter(type='RETENUE')

    can_validate = admin or utilisateur_peut_permission(request.user, 'valider_bulletin')

    return render(request, 'rh/bulletins/detail.html', {
        'bulletin':         bulletin,
        'lignes_avantages': lignes_avantages,
        'lignes_retenues':  lignes_retenues,
        'can_validate':     can_validate,
    })


@login_requis
@require_POST
def ajouter_ligne_bulletin(request, pk):
    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    bulletin   = get_object_or_404(_scope_bulletins(request.user, entreprise, admin), pk=pk)

    if bulletin.statut != 'BROUILLON':
        messages.error(request, "Impossible de modifier un bulletin validé ou payé.")
        return redirect('rh:detail-bulletin', pk=pk)

    type_ligne = request.POST.get('type')
    libelle    = request.POST.get('libelle', '').strip()
    montant_str= request.POST.get('montant', '').strip()

    if not libelle or not montant_str or type_ligne not in ('AVANTAGE', 'RETENUE'):
        messages.error(request, "Tous les champs sont requis.")
        return redirect('rh:detail-bulletin', pk=pk)

    try:
        montant = Decimal(montant_str.replace(',', '.'))
        if montant <= 0:
            raise ValueError
    except (ValueError, Exception):
        messages.error(request, "Montant invalide.")
        return redirect('rh:detail-bulletin', pk=pk)

    LigneBulletin.objects.create(
        bulletin = bulletin,
        type     = type_ligne,
        libelle  = libelle,
        montant  = montant,
    )
    recalculer_totaux(bulletin)
    messages.success(request, f"Ligne ajoutée : {libelle} — {montant}")
    return redirect('rh:detail-bulletin', pk=pk)


@login_requis
@require_POST
def supprimer_ligne_bulletin(request, pk, ligne_pk):
    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    bulletin   = get_object_or_404(_scope_bulletins(request.user, entreprise, admin), pk=pk)

    if bulletin.statut != 'BROUILLON':
        messages.error(request, "Impossible de modifier un bulletin validé ou payé.")
        return redirect('rh:detail-bulletin', pk=pk)

    try:
        ligne = bulletin.lignes.get(pk=ligne_pk, avance__isnull=True)
        ligne.delete()
        recalculer_totaux(bulletin)
        messages.success(request, "Ligne supprimée.")
    except LigneBulletin.DoesNotExist:
        messages.error(request, "Ligne introuvable ou non supprimable (avance liée).")

    return redirect('rh:detail-bulletin', pk=pk)


@login_requis
@require_POST
def valider_bulletin(request, pk):
    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    bulletin   = get_object_or_404(_scope_bulletins(request.user, entreprise, admin), pk=pk)

    if not (admin or utilisateur_peut_permission(request.user, 'valider_bulletin')):
        messages.error(request, "Vous n'êtes pas autorisé à valider des bulletins.")
        return redirect('rh:detail-bulletin', pk=pk)

    if bulletin.statut != 'BROUILLON':
        messages.error(request, "Seuls les brouillons peuvent être validés.")
        return redirect('rh:detail-bulletin', pk=pk)

    bulletin.statut         = 'VALIDE'
    bulletin.valide_par     = request.user
    bulletin.date_validation= timezone.now()
    bulletin.save(update_fields=['statut', 'valide_par', 'date_validation'])

    messages.success(request, f"Bulletin {bulletin.numero} validé.")
    return redirect('rh:detail-bulletin', pk=pk)


@login_requis
@require_POST
def payer_bulletin(request, pk):
    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    bulletin   = get_object_or_404(_scope_bulletins(request.user, entreprise, admin), pk=pk)

    if not (admin or utilisateur_peut_permission(request.user, 'valider_bulletin')):
        messages.error(request, "Vous n'êtes pas autorisé à enregistrer le paiement.")
        return redirect('rh:detail-bulletin', pk=pk)

    if bulletin.statut != 'VALIDE':
        messages.error(request, "Seuls les bulletins validés peuvent être marqués payés.")
        return redirect('rh:detail-bulletin', pk=pk)

    bulletin.statut       = 'PAYE'
    bulletin.paye_par     = request.user
    bulletin.date_paiement= timezone.now()
    bulletin.save(update_fields=['statut', 'paye_par', 'date_paiement'])

    # Marquer les avances associées comme remboursées
    for ligne in bulletin.lignes.filter(avance__isnull=False):
        avance = ligne.avance
        if avance and avance.statut == 'DECAISSEE':
            avance.statut = 'REMBOURSEE'
            avance.save(update_fields=['statut'])

    messages.success(
        request,
        f"Bulletin {bulletin.numero} marqué comme payé. "
        f"Les avances associées ont été marquées remboursées."
    )
    return redirect('rh:detail-bulletin', pk=pk)


@login_requis
def imprimer_bulletin(request, pk):
    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    bulletin   = get_object_or_404(
        _scope_bulletins(request.user, entreprise, admin)
        .select_related('employe__branche__entreprise', 'contrat__departement', 'devise',
                        'cree_par', 'valide_par', 'paye_par'),
        pk=pk,
    )
    lignes_avantages = bulletin.lignes.filter(type='AVANTAGE')
    lignes_retenues  = bulletin.lignes.filter(type='RETENUE')

    return render(request, 'rh/bulletins/imprimer.html', {
        'bulletin':         bulletin,
        'lignes_avantages': lignes_avantages,
        'lignes_retenues':  lignes_retenues,
        'entreprise':       bulletin.employe.branche.entreprise,
        'today':            timezone.now(),
    })
