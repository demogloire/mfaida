import secrets
import string
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import (
    authenticate, login, logout,
    get_user_model, update_session_auth_hash,
)
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django_htmx.http import HttpResponseLocation
from django.urls import reverse

from entreprise.models import Entreprise, Depot, PointVente
from .models import (
    Role, PermissionPersonnalisee, RolePermission,
    JournalConnexion, JournalAction,
    AccesDepot, AccesPointVente,
)
from .forms import (
    CreationSuperUser, LoginForm, MotDePasseOublieForm,
    ModificationProfilForm, ChangerMotDePasseForm,
    SecuriteForm, SignatureForm,
    CreationUtilisateurForm, ModificationUtilisateurForm,
    AccesDepotForm, AccesPointVenteForm,
    RoleForm, PermissionForm, GererPermissionsRoleForm,
)
from .decorators import login_requis, admin_requis

User = get_user_model()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _enregistrer_connexion(request, utilisateur=None, username_tente='', succes=False):
    JournalConnexion.objects.create(
        utilisateur=utilisateur,
        username_tente=username_tente,
        adresse_ip=_get_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
        succes=succes,
    )


def _generer_mot_de_passe():
    alphabet = string.ascii_letters + string.digits + string.punctuation
    return ''.join(secrets.choice(alphabet) for _ in range(12))


def _get_entreprise(user):
    """
    Retourne l'entreprise de l'utilisateur.
    Priorité : branche.entreprise > première entreprise disponible (admins sans branche).
    """
    if user.branche_id:
        return getattr(user.branche, 'entreprise', None)
    if user.admin or user.is_superuser:
        return Entreprise.objects.first()
    return None


# ── Authentification ──────────────────────────────────────────────────────────

def AdminUser(request):
    form = CreationSuperUser(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            if User.objects.filter(email=form.cleaned_data["email"]).exists():
                raise ValidationError("Cet utilisateur existe déjà")
            User.objects.create_user(
                email=form.cleaned_data["email"],
                first_name=form.cleaned_data["first_name"],
                last_name=form.cleaned_data["last_name"],
                password=form.cleaned_data["password1"],
                username=form.cleaned_data["email"],
                admin=True,
            )
            messages.success(request, "Utilisateur créé !")
            response = render(request, 'user/partial/connexion.html', {'form': LoginForm()})
            response['HX-Push-Url'] = '/user/connexion/'
            return response
        else:
            error_msg = " | ".join([f"{', '.join(e)}" for f, e in form.errors.items()])
            messages.info(request, error_msg)
        if request.htmx:
            return render(request, 'user/partial/add_user.html', {'form': form})
    return render(request, 'user/adminuser.html', {'form': form})


def Connexion(request):
    if request.user.is_authenticated:
        return redirect("entreprise:dashboard")

    next_url = request.GET.get("next") or False
    request.session["next_url"] = next_url

    form = LoginForm()
    context = {"form": form}

    if request.method == "POST":
        form = LoginForm(request.POST)
        context["form"] = form
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            remember_me = form.cleaned_data['remember_me']
            user = authenticate(username=username, password=password)
            if user:
                login(request, user)
                if remember_me:
                    request.session.set_expiry(1209600)
                _enregistrer_connexion(request, utilisateur=user, username_tente=username, succes=True)
                new_url = next_url or reverse('entreprise:dashboard')
                return HttpResponseLocation(redirect_to=new_url)
            else:
                _enregistrer_connexion(request, username_tente=username, succes=False)
                messages.error(request, "E-mail ou mot de passe incorrect.")
                if request.htmx:
                    return render(request, 'user/partial/connexion.html', context)

    return render(request, 'user/login.html', context)


def logout_view(request):
    logout(request)
    return redirect("user:connexion")


def mot_de_passe_oublie(request):
    form = MotDePasseOublieForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data['email']
        user = User.objects.get(email=email)
        nouveau_mdp = _generer_mot_de_passe()
        user.set_password(nouveau_mdp)
        user.save()
        messages.success(
            request,
            f"Un nouveau mot de passe temporaire a été généré : {nouveau_mdp} — "
            "Veuillez le changer dès votre prochaine connexion."
        )
        return redirect('user:connexion')
    return render(request, 'user/mot_de_passe_oublie.html', {'form': form})


# ── Profil personnel ──────────────────────────────────────────────────────────

@login_requis
def mon_profil(request):
    contexte = {
        'profil': request.user,
        'journal': JournalConnexion.objects.filter(utilisateur=request.user)[:10],
    }
    return render(request, 'user/profil/detail.html', contexte)


@login_requis
def modifier_profil(request):
    form = ModificationProfilForm(request.POST or None, request.FILES or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        user = form.save(commit=False)
        user.username = user.email
        user.save()
        messages.success(request, "Votre profil a été mis à jour.")
        if request.htmx:
            return render(request, 'user/profil/partial/form_profil.html', {'form': form})
        return redirect('user:mon-profil')
    return render(request, 'user/profil/modifier.html', {'form': form})


@login_requis
def changer_mot_de_passe(request):
    form = ChangerMotDePasseForm(user=request.user, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        update_session_auth_hash(request, form.user)
        messages.success(request, "Mot de passe modifié avec succès.")
        if request.htmx:
            return render(request, 'user/profil/partial/form_mdp.html', {'form': ChangerMotDePasseForm(user=request.user)})
        return redirect('user:mon-profil')
    return render(request, 'user/profil/changer_mdp.html', {'form': form})


# ── CRUD Utilisateurs ─────────────────────────────────────────────────────────

@admin_requis
def liste_utilisateurs(request):
    qs = User.objects.select_related('branche', 'role').order_by('last_name', 'first_name')

    q = request.GET.get('q', '').strip()
    branche_id = request.GET.get('branche')
    role_id = request.GET.get('role')
    actif = request.GET.get('actif')

    if q:
        qs = qs.filter(
            Q(first_name__icontains=q) |
            Q(last_name__icontains=q) |
            Q(email__icontains=q)
        )
    if branche_id:
        qs = qs.filter(branche_id=branche_id)
    if role_id:
        qs = qs.filter(role_id=role_id)
    if actif == '1':
        qs = qs.filter(is_active=True)
    elif actif == '0':
        qs = qs.filter(is_active=False)

    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get('page'))

    contexte = {
        'page_obj': page,
        'roles': Role.objects.all(),
        'q': q,
        'branche_id': branche_id,
        'role_id': role_id,
        'actif': actif,
    }
    if request.htmx and request.htmx.target == 'tableau-utilisateurs':
        return render(request, 'user/utilisateurs/partial/tableau.html', contexte)
    return render(request, 'user/utilisateurs/liste.html', contexte)


@admin_requis
def creer_utilisateur(request):
    entreprise = _get_entreprise(request.user)
    form = CreationUtilisateurForm(request.POST or None, request.FILES or None, entreprise=entreprise)
    if request.method == "POST":
        if form.is_valid():
            form.save()
            messages.success(request, "Utilisateur créé avec succès.")
            if request.htmx and request.htmx.target == 'form-container':
                return render(request, 'user/utilisateurs/partial/form.html', {
                    'form': CreationUtilisateurForm(entreprise=entreprise),
                    'success': True,
                })
            return redirect('user:liste-utilisateurs')
        elif request.htmx and request.htmx.target == 'form-container':
            return render(request, 'user/utilisateurs/partial/form.html', {'form': form})
    return render(request, 'user/utilisateurs/form.html', {'form': form, 'titre': "Créer un utilisateur"})


@admin_requis
def modifier_utilisateur(request, pk):
    utilisateur = get_object_or_404(User, pk=pk)
    entreprise = _get_entreprise(utilisateur) or _get_entreprise(request.user)
    form = ModificationUtilisateurForm(
        request.POST or None, request.FILES or None,
        instance=utilisateur, entreprise=entreprise,
    )
    if request.method == "POST":
        if form.is_valid():
            user = form.save(commit=False)
            user.username = user.email
            user.save()
            messages.success(request, "Utilisateur modifié avec succès.")
            if request.htmx and request.htmx.target == 'form-container':
                return render(request, 'user/utilisateurs/partial/form.html', {
                    'form': form, 'utilisateur': utilisateur, 'success': True,
                })
            return redirect('user:liste-utilisateurs')
        elif request.htmx and request.htmx.target == 'form-container':
            return render(request, 'user/utilisateurs/partial/form.html', {
                'form': form, 'utilisateur': utilisateur,
            })
    return render(request, 'user/utilisateurs/form.html', {
        'form': form,
        'utilisateur': utilisateur,
        'titre': f"Modifier — {utilisateur.get_full_name()}",
    })


@admin_requis
def activer_desactiver_utilisateur(request, pk):
    utilisateur = get_object_or_404(User, pk=pk)
    if utilisateur == request.user:
        messages.error(request, "Vous ne pouvez pas désactiver votre propre compte.")
    else:
        utilisateur.is_active = not utilisateur.is_active
        utilisateur.save(update_fields=['is_active'])
        statut = "activé" if utilisateur.is_active else "désactivé"
        messages.success(request, f"Compte de {utilisateur.get_full_name()} {statut}.")
    if request.htmx:
        return render(request, 'user/utilisateurs/partial/ligne.html', {'u': utilisateur})
    return redirect('user:liste-utilisateurs')


@admin_requis
def reinitialiser_mot_de_passe(request, pk):
    utilisateur = get_object_or_404(User, pk=pk)
    if request.method == "POST":
        nouveau_mdp = _generer_mot_de_passe()
        utilisateur.set_password(nouveau_mdp)
        utilisateur.save()
        messages.success(
            request,
            f"Nouveau mot de passe temporaire pour {utilisateur.get_full_name()} : {nouveau_mdp}"
        )
        if request.htmx:
            return render(request, 'user/utilisateurs/partial/mdp_reset.html', {
                'utilisateur': utilisateur, 'nouveau_mdp': nouveau_mdp,
            })
        return redirect('user:liste-utilisateurs')
    return render(request, 'user/utilisateurs/confirm_reset.html', {'utilisateur': utilisateur})


@admin_requis
def supprimer_utilisateur(request, pk):
    utilisateur = get_object_or_404(User, pk=pk)
    if utilisateur == request.user:
        messages.error(request, "Vous ne pouvez pas supprimer votre propre compte.")
        return redirect('user:liste-utilisateurs')
    if request.method == "POST":
        nom = utilisateur.get_full_name()
        utilisateur.delete()
        messages.success(request, f"Utilisateur {nom} supprimé.")
        if request.htmx:
            return HttpResponseLocation(redirect_to=reverse('user:liste-utilisateurs'))
        return redirect('user:liste-utilisateurs')
    return render(request, 'user/utilisateurs/confirmer_suppression.html', {'utilisateur': utilisateur})


_DEPOT_PERMS = [
    ('peut_voir',        'Voir le stock',          'ti-eye'),
    ('peut_recevoir',    'Réceptionner',            'ti-package-import'),
    ('peut_expedier',    'Expédier',                'ti-package-export'),
    ('peut_inventorier', 'Inventaire',              'ti-clipboard-list'),
    ('peut_administrer', 'Administrer',             'ti-settings'),
]

_PV_PERMS = [
    ('peut_voir',         'Voir',                  'ti-eye'),
    ('peut_vendre',       'Vendre',                'ti-receipt'),
    ('peut_faire_avoir',  'Avoirs',                'ti-receipt-refund'),
    ('peut_remise',       'Remises',               'ti-discount'),
    ('peut_gerer_caisse', 'Caisse',                'ti-cash'),
    ('peut_administrer',  'Administrer',           'ti-settings'),
]


@admin_requis
def gerer_acces_utilisateur(request, pk):
    """Gérer les accès dépôts et points de vente d'un utilisateur."""
    utilisateur = get_object_or_404(User, pk=pk)
    branche = utilisateur.branche

    depots = Depot.objects.filter(branche=branche, est_actif=True) if branche else Depot.objects.none()
    points_vente = PointVente.objects.filter(branche=branche, est_actif=True) if branche else PointVente.objects.none()

    if request.method == "POST":
        # ── Dépôts ──────────────────────────────────────────────────────────
        AccesDepot.objects.filter(utilisateur=utilisateur).delete()
        for depot in depots:
            prefix = f"depot_{depot.pk}_"
            actif = request.POST.get(f"{prefix}actif") == "1"
            if actif:
                AccesDepot.objects.create(
                    utilisateur=utilisateur,
                    depot=depot,
                    peut_voir=        request.POST.get(f"{prefix}peut_voir")        == "1",
                    peut_recevoir=    request.POST.get(f"{prefix}peut_recevoir")    == "1",
                    peut_expedier=    request.POST.get(f"{prefix}peut_expedier")    == "1",
                    peut_inventorier= request.POST.get(f"{prefix}peut_inventorier") == "1",
                    peut_administrer= request.POST.get(f"{prefix}peut_administrer") == "1",
                )

        # ── Points de vente ──────────────────────────────────────────────────
        AccesPointVente.objects.filter(utilisateur=utilisateur).delete()
        for pv in points_vente:
            prefix = f"pv_{pv.pk}_"
            actif = request.POST.get(f"{prefix}actif") == "1"
            if actif:
                AccesPointVente.objects.create(
                    utilisateur=utilisateur,
                    point_vente=pv,
                    peut_voir=         request.POST.get(f"{prefix}peut_voir")         == "1",
                    peut_vendre=       request.POST.get(f"{prefix}peut_vendre")       == "1",
                    peut_faire_avoir=  request.POST.get(f"{prefix}peut_faire_avoir")  == "1",
                    peut_remise=       request.POST.get(f"{prefix}peut_remise")       == "1",
                    peut_gerer_caisse= request.POST.get(f"{prefix}peut_gerer_caisse") == "1",
                    peut_administrer=  request.POST.get(f"{prefix}peut_administrer")  == "1",
                )

        messages.success(request, f"Accès de {utilisateur.get_full_name()} mis à jour.")
        if request.htmx and request.htmx.target == 'acces-container':
            return render(request, 'user/utilisateurs/partial/acces.html', {
                'utilisateur': utilisateur,
                'branche': branche,
                'depots': depots,
                'points_vente': points_vente,
                'acces_depots': {a.depot_id: a for a in utilisateur.acces_depots.select_related('depot')},
                'acces_pv': {a.point_vente_id: a for a in utilisateur.acces_points_vente.select_related('point_vente')},
                'depot_perms': _DEPOT_PERMS,
                'pv_perms': _PV_PERMS,
                'success': True,
            })
        return redirect('user:acces-utilisateur', pk=pk)

    contexte = {
        'utilisateur': utilisateur,
        'branche': branche,
        'depots': depots,
        'points_vente': points_vente,
        'acces_depots': {a.depot_id: a for a in utilisateur.acces_depots.select_related('depot')},
        'acces_pv': {a.point_vente_id: a for a in utilisateur.acces_points_vente.select_related('point_vente')},
        'depot_perms': _DEPOT_PERMS,
        'pv_perms': _PV_PERMS,
    }
    return render(request, 'user/utilisateurs/acces.html', contexte)


# ── CRUD Rôles ────────────────────────────────────────────────────────────────

@admin_requis
def liste_roles(request):
    entreprise = _get_entreprise(request.user)
    roles = Role.objects.filter(entreprise=entreprise).prefetch_related('permissions__permission') if entreprise else Role.objects.none()
    return render(request, 'user/roles/liste.html', {'roles': roles, 'entreprise': entreprise})


@admin_requis
def creer_role(request):
    entreprise = _get_entreprise(request.user)
    if not entreprise:
        messages.error(request, "Aucune entreprise trouvée dans le système. Créez d'abord une entreprise.")
        return redirect('user:liste-roles')
    form = RoleForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            role = form.save(commit=False)
            role.entreprise = entreprise
            role.save()
            messages.success(request, f"Rôle «\u00a0{role.nom}\u00a0» créé.")
            if request.htmx and request.htmx.target == 'form-role':
                return render(request, 'user/roles/partial/form.html', {
                    'form': RoleForm(), 'success': True,
                })
            return redirect('user:liste-roles')
        elif request.htmx and request.htmx.target == 'form-role':
            return render(request, 'user/roles/partial/form.html', {'form': form})
    return render(request, 'user/roles/form.html', {'form': form, 'titre': "Créer un rôle"})


@admin_requis
def modifier_role(request, pk):
    role = get_object_or_404(Role, pk=pk)
    form = RoleForm(request.POST or None, instance=role)
    if request.method == "POST":
        if form.is_valid():
            form.save()
            messages.success(request, f"Rôle «\u00a0{role.nom}\u00a0» modifié.")
            if request.htmx and request.htmx.target == 'form-role':
                return render(request, 'user/roles/partial/form.html', {'form': form, 'role': role, 'success': True})
            return redirect('user:liste-roles')
        elif request.htmx and request.htmx.target == 'form-role':
            return render(request, 'user/roles/partial/form.html', {'form': form, 'role': role})
    return render(request, 'user/roles/form.html', {'form': form, 'role': role, 'titre': f"Modifier — {role.nom}"})


@admin_requis
def supprimer_role(request, pk):
    role = get_object_or_404(Role, pk=pk)
    if request.method == "POST":
        if role.utilisateurs.exists():
            messages.error(request, f"Impossible : {role.utilisateurs.count()} utilisateur(s) ont ce rôle.")
            return redirect('user:liste-roles')
        nom = role.nom
        role.delete()
        messages.success(request, f"Rôle «\u00a0{nom}\u00a0» supprimé.")
        if request.htmx:
            return HttpResponseLocation(redirect_to=reverse('user:liste-roles'))
        return redirect('user:liste-roles')
    return render(request, 'user/roles/confirmer_suppression.html', {'role': role})


@admin_requis
def gerer_permissions_role(request, pk):
    role = get_object_or_404(Role, pk=pk)
    toutes_permissions = PermissionPersonnalisee.objects.order_by('nom')

    if request.method == "POST":
        # PKs cochées envoyées par le formulaire (cases à cocher name="permissions")
        pks_coches = set(request.POST.getlist('permissions'))
        RolePermission.objects.filter(role=role).delete()
        RolePermission.objects.bulk_create([
            RolePermission(role=role, permission=p)
            for p in toutes_permissions
            if str(p.pk) in pks_coches
        ])
        pks_actifs = pks_coches
        messages.success(request, f"Permissions du rôle «\u00a0{role.nom}\u00a0» mises à jour.")
        if request.htmx and request.htmx.target == 'perm-container':
            return render(request, 'user/roles/partial/permissions.html', {
                'role': role,
                'toutes_permissions': toutes_permissions,
                'pks_actifs': pks_actifs,
                'success': True,
            })
        return redirect('user:liste-roles')

    pks_actifs = set(str(p.pk) for p in PermissionPersonnalisee.objects.filter(roles__role=role))
    return render(request, 'user/roles/permissions.html', {
        'role': role,
        'toutes_permissions': toutes_permissions,
        'pks_actifs': pks_actifs,
    })


# ── CRUD Permissions ──────────────────────────────────────────────────────────

@admin_requis
def liste_permissions(request):
    permissions = PermissionPersonnalisee.objects.order_by('nom')
    return render(request, 'user/permissions/liste.html', {'permissions': permissions})


@admin_requis
def creer_permission(request):
    form = PermissionForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            perm = form.save()
            messages.success(request, f"Permission «\u00a0{perm.nom}\u00a0» créée.")
            if request.htmx and request.htmx.target == 'form-perm':
                return render(request, 'user/permissions/partial/form.html', {
                    'form': PermissionForm(), 'success': True,
                })
            return redirect('user:liste-permissions')
        elif request.htmx and request.htmx.target == 'form-perm':
            return render(request, 'user/permissions/partial/form.html', {'form': form})
    return render(request, 'user/permissions/form.html', {'form': form, 'titre': "Créer une permission"})


@admin_requis
def modifier_permission(request, pk):
    permission = get_object_or_404(PermissionPersonnalisee, pk=pk)
    form = PermissionForm(request.POST or None, instance=permission)
    if request.method == "POST":
        if form.is_valid():
            form.save()
            messages.success(request, f"Permission «\u00a0{permission.nom}\u00a0» modifiée.")
            if request.htmx and request.htmx.target == 'form-perm':
                return render(request, 'user/permissions/partial/form.html', {
                    'form': form, 'permission': permission, 'success': True,
                })
            return redirect('user:liste-permissions')
        elif request.htmx and request.htmx.target == 'form-perm':
            return render(request, 'user/permissions/partial/form.html', {
                'form': form, 'permission': permission,
            })
    return render(request, 'user/permissions/form.html', {
        'form': form, 'permission': permission, 'titre': f"Modifier — {permission.nom}",
    })


@admin_requis
def supprimer_permission(request, pk):
    permission = get_object_or_404(PermissionPersonnalisee, pk=pk)
    if request.method == "POST":
        nom = permission.nom
        permission.delete()
        messages.success(request, f"Permission «\u00a0{nom}\u00a0» supprimée.")
        if request.htmx:
            return HttpResponseLocation(redirect_to=reverse('user:liste-permissions'))
        return redirect('user:liste-permissions')
    return render(request, 'user/permissions/confirmer_suppression.html', {'permission': permission})


# ── Journal des connexions ────────────────────────────────────────────────────

@admin_requis
def journal_connexions(request):
    qs = JournalConnexion.objects.select_related('utilisateur').order_by('-date_heure')

    utilisateur_id = request.GET.get('utilisateur')
    succes = request.GET.get('succes')
    date_debut = request.GET.get('date_debut')
    date_fin = request.GET.get('date_fin')

    if utilisateur_id:
        qs = qs.filter(utilisateur_id=utilisateur_id)
    if succes == '1':
        qs = qs.filter(succes=True)
    elif succes == '0':
        qs = qs.filter(succes=False)
    if date_debut:
        qs = qs.filter(date_heure__date__gte=date_debut)
    if date_fin:
        qs = qs.filter(date_heure__date__lte=date_fin)

    paginator = Paginator(qs, 30)
    page = paginator.get_page(request.GET.get('page'))

    contexte = {
        'page_obj': page,
        'utilisateurs': User.objects.filter(journal_connexions__isnull=False).distinct(),
        'utilisateur_id': utilisateur_id,
        'succes': succes,
        'date_debut': date_debut,
        'date_fin': date_fin,
    }
    if request.htmx and request.htmx.target == 'journal-tableau':
        return render(request, 'user/journal/partial/tableau.html', contexte)
    return render(request, 'user/journal/liste.html', contexte)


@login_requis
def activite_utilisateur(request, pk):
    utilisateur = get_object_or_404(User, pk=pk)
    if not request.user.admin and request.user.pk != pk:
        messages.error(request, "Accès refusé.")
        return redirect('entreprise:dashboard')
    journal = JournalConnexion.objects.filter(utilisateur=utilisateur).order_by('-date_heure')
    paginator = Paginator(journal, 20)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'user/journal/activite.html', {
        'utilisateur': utilisateur,
        'page_obj': page,
    })


# ── Helper audit ──────────────────────────────────────────────────────────────

def enregistrer_action(request, verbe, module='', description=''):
    """
    Enregistre une action dans JournalAction.
    À appeler depuis n'importe quelle vue après une opération significative.

    Exemple :
        enregistrer_action(request, 'creation', 'facturation', 'Facture #123 créée')
    """
    if request.user.is_authenticated:
        JournalAction.objects.create(
            utilisateur=request.user,
            verbe=verbe,
            module=module,
            description=description,
            adresse_ip=_get_client_ip(request),
        )


# ── Paramètres généraux ───────────────────────────────────────────────────────

@login_requis
def securite(request):
    """
    Page de sécurité : changement d'e-mail (avec confirmation MDP)
    et changement de mot de passe dans la même vue en deux formulaires distincts.
    """
    form_email = SecuriteForm(
        request.POST if request.POST.get('action') == 'email' else None,
        instance=request.user,
        utilisateur=request.user,
        prefix='email',
    )
    form_mdp = ChangerMotDePasseForm(
        user=request.user,
        data=request.POST if request.POST.get('action') == 'mdp' else None,
        prefix='mdp',
    )

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'email' and form_email.is_valid():
            user = form_email.save(commit=False)
            user.username = user.email
            user.save()
            enregistrer_action(request, 'modification', 'utilisateurs', "Adresse e-mail modifiée")
            messages.success(request, "Adresse e-mail mise à jour.")
            if request.htmx:
                return render(request, 'user/securite/partial/form_email.html', {
                    'form_email': SecuriteForm(instance=request.user, utilisateur=request.user, prefix='email'),
                    'success': True,
                })
            return redirect('user:securite')

        if action == 'mdp' and form_mdp.is_valid():
            form_mdp.save()
            update_session_auth_hash(request, form_mdp.user)
            enregistrer_action(request, 'modification', 'utilisateurs', "Mot de passe modifié")
            messages.success(request, "Mot de passe modifié avec succès.")
            if request.htmx:
                return render(request, 'user/securite/partial/form_mdp.html', {
                    'form_mdp': ChangerMotDePasseForm(user=request.user, prefix='mdp'),
                    'success': True,
                })
            return redirect('user:securite')

    contexte = {
        'form_email': form_email,
        'form_mdp': form_mdp,
        'dernieres_connexions': JournalConnexion.objects.filter(
            utilisateur=request.user
        )[:5],
    }
    return render(request, 'user/securite/index.html', contexte)


@login_requis
def signature(request):
    """
    Page de gestion de la signature personnelle.
    La signature est utilisée dans les documents générés (factures, bons, etc.).
    """
    form = SignatureForm(
        request.POST or None,
        request.FILES or None,
        instance=request.user,
    )
    if request.method == 'POST' and form.is_valid():
        form.save()
        enregistrer_action(request, 'modification', 'utilisateurs', "Signature mise à jour")
        messages.success(request, "Signature mise à jour avec succès.")
        if request.htmx:
            return render(request, 'user/signature/partial/apercu.html', {
                'profil': request.user,
                'form': SignatureForm(instance=request.user),
                'success': True,
            })
        return redirect('user:signature')
    return render(request, 'user/signature/index.html', {
        'form': form,
        'profil': request.user,
    })


@login_requis
def audit_personnel(request):
    """
    Audit de l'utilisateur connecté : connexions + toutes ses actions.
    """
    module = request.GET.get('module', '').strip()
    verbe = request.GET.get('verbe', '').strip()
    date_debut = request.GET.get('date_debut', '')
    date_fin = request.GET.get('date_fin', '')

    actions_qs = JournalAction.objects.filter(utilisateur=request.user)
    if module:
        actions_qs = actions_qs.filter(module__icontains=module)
    if verbe:
        actions_qs = actions_qs.filter(verbe=verbe)
    if date_debut:
        actions_qs = actions_qs.filter(date_heure__date__gte=date_debut)
    if date_fin:
        actions_qs = actions_qs.filter(date_heure__date__lte=date_fin)

    connexions_qs = JournalConnexion.objects.filter(utilisateur=request.user)

    paginator_actions = Paginator(actions_qs, 20)
    paginator_connexions = Paginator(connexions_qs, 10)

    page_actions = paginator_actions.get_page(request.GET.get('page_a'))
    page_connexions = paginator_connexions.get_page(request.GET.get('page_c'))

    contexte = {
        'page_actions': page_actions,
        'page_connexions': page_connexions,
        'verbe_choices': JournalAction.VERBE_CHOICES,
        'module': module,
        'verbe': verbe,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'total_actions': JournalAction.objects.filter(utilisateur=request.user).count(),
        'total_connexions': connexions_qs.count(),
        'connexions_succes': connexions_qs.filter(succes=True).count(),
        'connexions_echec': connexions_qs.filter(succes=False).count(),
    }
    return render(request, 'user/audit/index.html', contexte)
