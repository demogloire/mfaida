"""Vues module Dépenses — liste, création, détail, validation, annulation."""

from decimal import Decimal

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from entreprise.models import Devise, PointVente
from stock.access import get_entreprise_utilisateur, utilisateur_est_admin, queryset_points_vente_visibles
from utilisateur.acces_metier import utilisateur_peut_permission
from utilisateur.decorators import login_requis

from .models import Depense, TypeDepense


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _peut_valider(user):
    return utilisateur_peut_permission(user, 'valider_depense')


def _scope_depenses(user, entreprise, admin):
    qs = Depense.objects.select_related(
        'point_vente', 'devise', 'enregistre_par', 'valide_par', 'retour_vente'
    ).order_by('-date_depense')

    if admin:
        if entreprise:
            return qs.filter(point_vente__branche__entreprise=entreprise)
        return qs

    if not entreprise:
        return Depense.objects.none()

    branche = getattr(user, 'branche', None)
    if not branche:
        return Depense.objects.none()

    return qs.filter(point_vente__branche=branche)


# ─────────────────────────────────────────────
# Liste
# ─────────────────────────────────────────────

@login_requis
def liste_depenses(request):
    entreprise = get_entreprise_utilisateur(request.user)
    admin = utilisateur_est_admin(request.user)
    peut_valider = _peut_valider(request.user)

    qs = _scope_depenses(request.user, entreprise, admin)

    statuts_ok  = {c[0] for c in Depense.STATUTS}
    types_ok    = {c[0] for c in Depense.TYPES}
    statut_f    = (request.GET.get('statut') or '').strip()
    type_f      = (request.GET.get('type_depense') or '').strip()
    q_f         = (request.GET.get('q') or '').strip()
    date_de_raw = (request.GET.get('date_de') or '').strip()
    date_a_raw  = (request.GET.get('date_a') or '').strip()

    d_de = parse_date(date_de_raw) if date_de_raw else None
    d_a  = parse_date(date_a_raw)  if date_a_raw  else None
    if d_de and d_a and d_de > d_a:
        d_de, d_a = d_a, d_de

    if statut_f in statuts_ok:
        qs = qs.filter(statut=statut_f)
    if type_f in types_ok:
        qs = qs.filter(type_depense=type_f)
    if q_f:
        qs = qs.filter(
            Q(numero_depense__icontains=q_f)
            | Q(motif__icontains=q_f)
            | Q(point_vente__nom__icontains=q_f)
        )
    if d_de:
        qs = qs.filter(date_depense__date__gte=d_de)
    if d_a:
        qs = qs.filter(date_depense__date__lte=d_a)

    if admin or peut_valider:
        points_vente = (
            PointVente.objects.filter(branche__entreprise=entreprise, est_actif=True)
            if entreprise else PointVente.objects.filter(est_actif=True)
        )
    else:
        points_vente = queryset_points_vente_visibles(request.user, entreprise, admin)

    return render(request, 'depenses/liste_depenses.html', {
        'depenses':       qs[:500],
        'actif':          'depenses',
        'points_vente':   points_vente,
        'statuts_choix':  Depense.STATUTS,
        'types_choix':    Depense.TYPES,
        'filt_statut':    statut_f if statut_f in statuts_ok else '',
        'filt_type':      type_f   if type_f   in types_ok  else '',
        'filt_q':         q_f,
        'filt_date_de':   d_de.isoformat() if d_de else '',
        'filt_date_a':    d_a.isoformat()  if d_a  else '',
        'peut_valider':   peut_valider,
    })


# ─────────────────────────────────────────────
# Nouvelle dépense manuelle
# ─────────────────────────────────────────────

@login_requis
def nouvelle_depense(request):
    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    if not entreprise and not admin:
        messages.error(request, 'Aucune entreprise associée.')
        return redirect('entreprise:dashboard')

    branche = getattr(request.user, 'branche', None)

    if request.method == 'POST':
        pv_pk       = request.POST.get('point_vente', '').strip()
        categorie_pk= request.POST.get('categorie', '').strip()
        montant_r   = request.POST.get('montant', '').strip()
        devise_pk   = request.POST.get('devise', '').strip()
        motif       = request.POST.get('motif', '').strip()

        erreurs = []
        pv = None
        if pv_pk.isdigit():
            pv_qs = PointVente.objects.filter(pk=int(pv_pk), est_actif=True)
            if entreprise:
                pv_qs = pv_qs.filter(branche__entreprise=entreprise)
            if not admin and branche:
                pv_qs = pv_qs.filter(branche=branche)
            pv = pv_qs.first()
        if not pv:
            erreurs.append('Point de vente invalide.')
        else:
            # Vérifier qu'une session de caisse est ouverte sur ce PDV
            from caisse.models import SessionCaisse
            if not SessionCaisse.objects.filter(point_vente=pv, statut='OUVERTE').exists():
                erreurs.append(
                    f'Aucune session de caisse ouverte sur « {pv.nom} ». '
                    f'Ouvrez une session avant d\'enregistrer une dépense.'
                )

        montant = None
        try:
            montant = Decimal(montant_r.replace(',', '.'))
            if montant <= 0:
                erreurs.append('Le montant doit être positif.')
        except Exception:
            erreurs.append('Montant invalide.')

        devise = None
        if devise_pk.isdigit():
            qs_dev = Devise.objects.filter(pk=int(devise_pk))
            if entreprise:
                qs_dev = qs_dev.filter(entreprise=entreprise)
            devise = qs_dev.first()
        if not devise:
            erreurs.append('Devise invalide.')

        if not motif:
            erreurs.append('Le motif est obligatoire.')

        # Résoudre la catégorie configurée
        categorie = None
        if categorie_pk.isdigit() and entreprise:
            categorie = TypeDepense.objects.filter(pk=int(categorie_pk), entreprise=entreprise, est_actif=True).first()

        if erreurs:
            for e in erreurs:
                messages.error(request, e)
        else:
            dep = Depense(
                point_vente=pv,
                type_depense='AUTRE',   # valeur legacy maintenue
                categorie=categorie,
                montant=montant,
                devise=devise,
                taux_echange=devise.taux_echange,
                motif=motif,
                statut='BROUILLON',
                enregistre_par=request.user,
            )
            dep.save()
            messages.success(request, f'Dépense {dep.numero_depense} créée.')
            return redirect('depenses:detail-depense', pk=dep.pk)

    # GET
    from caisse.models import SessionCaisse
    if entreprise:
        pvs     = PointVente.objects.filter(branche__entreprise=entreprise, est_actif=True)
        devises = Devise.objects.filter(entreprise=entreprise).order_by('code')
        categories = TypeDepense.objects.filter(entreprise=entreprise, est_actif=True, est_systeme=False).order_by('ordre', 'nom')
        if not admin and branche:
            pvs = pvs.filter(branche=branche)
    else:
        pvs        = PointVente.objects.filter(est_actif=True)
        devises    = Devise.objects.all().order_by('code')
        categories = TypeDepense.objects.none()

    # PKs des PDVs ayant une session ouverte (pour indicateurs visuels + JS)
    pvs_avec_session = set(
        SessionCaisse.objects.filter(
            point_vente__in=pvs, statut='OUVERTE'
        ).values_list('point_vente_id', flat=True)
    )

    devise_principale = devises.filter(est_principale=True).first() or devises.first()

    return render(request, 'depenses/nouvelle_depense.html', {
        'actif':              'depenses',
        'points_vente':       pvs,
        'devises':            devises,
        'categories':         categories,
        'devise_principale':  devise_principale,
        'url_config_types':   'depenses:liste-types-depense',
        'pvs_avec_session':   pvs_avec_session,
    })


# ─────────────────────────────────────────────
# Détail
# ─────────────────────────────────────────────

@login_requis
def detail_depense(request, pk):
    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    dep = get_object_or_404(
        _scope_depenses(request.user, entreprise, admin).select_related(
            'point_vente__branche__entreprise', 'devise',
            'enregistre_par', 'valide_par', 'retour_vente',
        ),
        pk=pk,
    )
    return render(request, 'depenses/detail_depense.html', {
        'depense':      dep,
        'actif':        'depenses',
        'peut_valider': _peut_valider(request.user),
    })


# ─────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────

@login_requis
@require_POST
def valider_depense(request, pk):
    if not _peut_valider(request.user):
        messages.error(request, 'Droits insuffisants pour valider une dépense.')
        return redirect('depenses:detail-depense', pk=pk)

    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    dep = get_object_or_404(_scope_depenses(request.user, entreprise, admin), pk=pk)

    if dep.statut != 'BROUILLON':
        messages.warning(request, 'Seule une dépense en brouillon peut être validée.')
        return redirect('depenses:detail-depense', pk=pk)

    dep.statut          = 'VALIDEE'
    dep.valide_par      = request.user
    dep.date_validation = timezone.now()
    dep.save(update_fields=['statut', 'valide_par', 'date_validation'])

    # Transaction caisse automatique
    try:
        from caisse.services import enregistrer_decaissement_depense
        enregistrer_decaissement_depense(dep, request.user)
    except Exception:
        pass

    messages.success(request, f'Dépense {dep.numero_depense} validée.')
    return redirect('depenses:detail-depense', pk=pk)


# ─────────────────────────────────────────────
# Annulation
# ─────────────────────────────────────────────

@login_requis
def imprimer_depense(request, pk):
    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    dep = get_object_or_404(
        _scope_depenses(request.user, entreprise, admin).select_related(
            'point_vente__branche__entreprise', 'devise',
            'enregistre_par', 'valide_par', 'retour_vente__facture_origine',
        ),
        pk=pk,
    )
    from entreprise.models import Entreprise
    ent = entreprise or (dep.point_vente.branche.entreprise if dep.point_vente.branche else None)
    return render(request, 'depenses/imprimer_depense.html', {
        'depense':     dep,
        'entreprise':  ent,
    })


@login_requis
@require_POST
def annuler_depense(request, pk):
    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    dep = get_object_or_404(_scope_depenses(request.user, entreprise, admin), pk=pk)

    if dep.statut == 'VALIDEE' and not _peut_valider(request.user):
        messages.error(request, 'Seul un utilisateur avec le droit de validation peut annuler une dépense validée.')
        return redirect('depenses:detail-depense', pk=pk)

    if dep.statut == 'ANNULEE':
        messages.warning(request, 'Cette dépense est déjà annulée.')
        return redirect('depenses:detail-depense', pk=pk)

    dep.statut = 'ANNULEE'
    dep.save(update_fields=['statut'])
    messages.warning(request, f'Dépense {dep.numero_depense} annulée.')
    return redirect('depenses:detail-depense', pk=pk)


# ─────────────────────────────────────────────────────────────────────────────
# Paramètres — Types de dépenses (configurable Manager / Admin)
# ─────────────────────────────────────────────────────────────────────────────

def _peut_configurer(user):
    return utilisateur_peut_permission(user, 'acces_configuration_entreprise') or utilisateur_est_admin(user)


@login_requis
def liste_types_depense(request):
    if not _peut_configurer(request.user):
        messages.error(request, 'Accès refusé.')
        return redirect('entreprise:dashboard')

    entreprise = get_entreprise_utilisateur(request.user)
    if not entreprise:
        messages.error(request, 'Aucune entreprise associée.')
        return redirect('entreprise:dashboard')

    types = TypeDepense.objects.filter(entreprise=entreprise).order_by('ordre', 'nom')
    return render(request, 'depenses/types/liste.html', {
        'actif': 'parametres',
        'types': types,
    })


@login_requis
def creer_type_depense(request):
    if not _peut_configurer(request.user):
        messages.error(request, 'Accès refusé.')
        return redirect('entreprise:dashboard')

    entreprise = get_entreprise_utilisateur(request.user)
    if not entreprise:
        messages.error(request, 'Aucune entreprise associée.')
        return redirect('entreprise:dashboard')

    if request.method == 'POST':
        nom         = request.POST.get('nom', '').strip()
        description = request.POST.get('description', '').strip()
        icone       = request.POST.get('icone', 'ti-cash').strip() or 'ti-cash'
        couleur     = request.POST.get('couleur', '#4c6ef5').strip() or '#4c6ef5'
        ordre_raw   = request.POST.get('ordre', '0').strip()
        ordre       = int(ordre_raw) if ordre_raw.isdigit() else 0

        if not nom:
            messages.error(request, 'Le nom est obligatoire.')
        elif TypeDepense.objects.filter(entreprise=entreprise, nom__iexact=nom).exists():
            messages.error(request, f'Un type « {nom} » existe déjà.')
        else:
            TypeDepense.objects.create(
                entreprise=entreprise,
                nom=nom,
                description=description,
                icone=icone,
                couleur=couleur,
                ordre=ordre,
                est_systeme=False,
            )
            messages.success(request, f'Type « {nom} » créé.')
            return redirect('depenses:liste-types-depense')
    return redirect('depenses:liste-types-depense')


@login_requis
def modifier_type_depense(request, pk):
    if not _peut_configurer(request.user):
        messages.error(request, 'Accès refusé.')
        return redirect('entreprise:dashboard')

    entreprise = get_entreprise_utilisateur(request.user)
    td = get_object_or_404(TypeDepense, pk=pk, entreprise=entreprise)

    if request.method == 'POST':
        nom         = request.POST.get('nom', '').strip()
        description = request.POST.get('description', '').strip()
        icone       = request.POST.get('icone', td.icone).strip() or td.icone
        couleur     = request.POST.get('couleur', td.couleur).strip() or td.couleur
        ordre_raw   = request.POST.get('ordre', '0').strip()
        ordre       = int(ordre_raw) if ordre_raw.isdigit() else td.ordre
        est_actif   = request.POST.get('est_actif') == '1'

        if not nom:
            messages.error(request, 'Le nom est obligatoire.')
            return redirect('depenses:liste-types-depense')

        dup = TypeDepense.objects.filter(entreprise=entreprise, nom__iexact=nom).exclude(pk=pk)
        if dup.exists():
            messages.error(request, f'Un type « {nom} » existe déjà.')
            return redirect('depenses:liste-types-depense')

        td.nom = nom
        td.description = description
        td.icone = icone
        td.couleur = couleur
        td.ordre = ordre
        td.est_actif = est_actif
        td.save()
        messages.success(request, f'Type « {nom} » mis à jour.')
    return redirect('depenses:liste-types-depense')


@login_requis
@require_POST
def supprimer_type_depense(request, pk):
    if not _peut_configurer(request.user):
        messages.error(request, 'Accès refusé.')
        return redirect('entreprise:dashboard')

    entreprise = get_entreprise_utilisateur(request.user)
    td = get_object_or_404(TypeDepense, pk=pk, entreprise=entreprise)

    if td.est_systeme:
        messages.error(request, 'Ce type système ne peut pas être supprimé.')
        return redirect('depenses:liste-types-depense')
    if td.depenses.exists():
        messages.error(request, f'Impossible : des dépenses utilisent ce type.')
        return redirect('depenses:liste-types-depense')

    td.delete()
    messages.success(request, 'Type supprimé.')
    return redirect('depenses:liste-types-depense')


