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
from .decorators import login_requis

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


def _est_super_admin(user):
    return bool(getattr(user, 'admin', False) or getattr(user, 'is_superuser', False))


def _get_entreprise_liee(user):
    """
    Entreprise à laquelle l'utilisateur est rattaché (hors mode super-admin).
    Branche d'affectation, sinon entreprise dont il est le propriétaire (Entreprise.user).
    """
    if getattr(user, 'branche_id', None):
        return user.branche.entreprise
    return Entreprise.objects.filter(user=user).first()


def _entreprise_utilisateur_cible(utilisateur):
    if utilisateur.branche_id:
        return utilisateur.branche.entreprise
    if utilisateur.role_id:
        return utilisateur.role.entreprise
    return None


def _peut_modifier_utilisateur_hors_superadmin(actor, cible):
    ae = _get_entreprise_liee(actor)
    if not ae:
        return False
    ce = _entreprise_utilisateur_cible(cible)
    if ce is None:
        return True
    return ce == ae


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
        if request.htmx:
            return render(request, 'user/profil/partial/form_profil.html', {'form': form, 'success': True})
        messages.success(request, "Votre profil a été mis à jour.")
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

@login_requis
def liste_utilisateurs(request):
    if not (_est_super_admin(request.user) or request.user.a_la_permission(
        'acces_administration_utilisateurs'
    )):
        messages.error(request, "Accès réservé.")
        return redirect('entreprise:dashboard')

    qs = User.objects.select_related('branche', 'role').order_by('last_name', 'first_name')
    super_adm = _est_super_admin(request.user)
    ent_scope = None
    if not super_adm:
        ent_scope = _get_entreprise_liee(request.user)
        if not ent_scope:
            messages.error(request, "Aucune entreprise associée à votre compte.")
            return redirect('entreprise:dashboard')
        qs = qs.filter(Q(branche__entreprise=ent_scope) | Q(role__entreprise=ent_scope))

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

    roles_qs = Role.objects.all().order_by('nom') if super_adm else Role.objects.filter(
        entreprise=ent_scope,
    ).order_by('nom')

    contexte = {
        'page_obj': page,
        'roles': roles_qs,
        'q': q,
        'branche_id': branche_id,
        'role_id': role_id,
        'actif': actif,
        'est_super_admin': super_adm,
    }
    if request.htmx and request.htmx.target == 'tableau-utilisateurs':
        return render(request, 'user/utilisateurs/partial/tableau.html', contexte)
    return render(request, 'user/utilisateurs/liste.html', contexte)


@login_requis
def creer_utilisateur(request):
    if not (_est_super_admin(request.user) or request.user.a_la_permission(
        'acces_administration_utilisateurs'
    )):
        messages.error(request, "Accès réservé.")
        return redirect('entreprise:dashboard')

    choix = _est_super_admin(request.user)
    entreprise_liee = _get_entreprise_liee(request.user)

    entreprise_eff = None
    if choix:
        raw_ec = request.POST.get('entreprise_cible') if request.method == 'POST' else request.GET.get(
            'entreprise_cible'
        )
        if raw_ec:
            entreprise_eff = get_object_or_404(Entreprise, pk=raw_ec)
    else:
        entreprise_eff = entreprise_liee
        if not entreprise_eff:
            messages.error(request, "Aucune entreprise associée à votre compte.")
            return redirect('entreprise:dashboard')

    htmx_ent_url = reverse('user:creer-utilisateur') if choix else ''
    prom_admin = _est_super_admin(request.user)

    if (
        request.method == 'POST'
        and request.htmx
        and getattr(request.htmx, 'target', None) == 'form-container'
        and request.POST.get('entreprise_refresh') == '1'
    ):
        entreprise_kw = None if choix else entreprise_eff
        form = CreationUtilisateurForm(
            request.POST,
            request.FILES or None,
            entreprise=entreprise_kw,
            choix_entreprise=choix,
            htmx_entreprise_url=htmx_ent_url,
            peut_promouvoir_admin=prom_admin,
        )
        return render(request, 'user/utilisateurs/partial/form.html', {
            'form': form,
            'entreprise_affichage': None if choix else entreprise_eff,
        })

    entreprise_kw = None if (request.method == 'POST' and choix) else entreprise_eff
    form = CreationUtilisateurForm(
        request.POST or None, request.FILES or None,
        entreprise=entreprise_kw,
        choix_entreprise=choix,
        htmx_entreprise_url=htmx_ent_url,
        peut_promouvoir_admin=prom_admin,
    )
    if request.method == "POST":
        if form.is_valid():
            form.save()
            messages.success(request, "Utilisateur créé avec succès.")
            if request.htmx and request.htmx.target == 'form-container':
                return render(request, 'user/utilisateurs/partial/form.html', {
                    'form': CreationUtilisateurForm(
                        entreprise=None if choix else entreprise_liee,
                        choix_entreprise=choix,
                        htmx_entreprise_url=htmx_ent_url,
                        peut_promouvoir_admin=prom_admin,
                    ),
                    'success': True,
                    'entreprise_affichage': None if choix else entreprise_liee,
                })
            return redirect('user:liste-utilisateurs')
        elif request.htmx and request.htmx.target == 'form-container':
            return render(request, 'user/utilisateurs/partial/form.html', {
                'form': form,
                'entreprise_affichage': None if choix else entreprise_eff,
            })
    return render(request, 'user/utilisateurs/form.html', {
        'form': form,
        'titre': "Créer un utilisateur",
        'entreprise_affichage': None if choix else entreprise_eff,
    })


@login_requis
def modifier_utilisateur(request, pk):
    utilisateur = get_object_or_404(User, pk=pk)
    if not (_est_super_admin(request.user) or request.user.a_la_permission(
        'acces_administration_utilisateurs'
    )):
        messages.error(request, "Accès réservé.")
        return redirect('entreprise:dashboard')
    if not (_est_super_admin(request.user)
            or _peut_modifier_utilisateur_hors_superadmin(request.user, utilisateur)):
        messages.error(request, "Vous ne pouvez pas modifier cet utilisateur.")
        return redirect('user:liste-utilisateurs')

    choix = _est_super_admin(request.user)
    u_ent = _entreprise_utilisateur_cible(utilisateur)

    entreprise_eff = None
    if choix:
        raw_ec = request.POST.get('entreprise_cible') if request.method == 'POST' else request.GET.get(
            'entreprise_cible'
        )
        if raw_ec:
            entreprise_eff = get_object_or_404(Entreprise, pk=raw_ec)
        else:
            entreprise_eff = u_ent
    else:
        entreprise_eff = _get_entreprise_liee(request.user)

    htmx_ent_url = reverse('user:modifier-utilisateur', args=[utilisateur.pk]) if choix else ''
    prom_admin = _est_super_admin(request.user)

    if (
        request.method == 'POST'
        and request.htmx
        and getattr(request.htmx, 'target', None) == 'form-container'
        and request.POST.get('entreprise_refresh') == '1'
    ):
        entreprise_kw = None if choix else entreprise_eff
        form = ModificationUtilisateurForm(
            request.POST,
            request.FILES or None,
            instance=utilisateur,
            entreprise=entreprise_kw,
            choix_entreprise=choix,
            htmx_entreprise_url=htmx_ent_url,
            peut_promouvoir_admin=prom_admin,
        )
        return render(request, 'user/utilisateurs/partial/form.html', {
            'form': form,
            'utilisateur': utilisateur,
            'entreprise_affichage': None if choix else entreprise_eff,
        })

    entreprise_kw = None if (request.method == 'POST' and choix) else entreprise_eff
    form = ModificationUtilisateurForm(
        request.POST or None, request.FILES or None,
        instance=utilisateur,
        entreprise=entreprise_kw,
        choix_entreprise=choix,
        htmx_entreprise_url=htmx_ent_url,
        peut_promouvoir_admin=prom_admin,
    )
    if request.method == "POST":
        if form.is_valid():
            user = form.save(commit=False)
            user.username = user.email
            user.save()
            utilisateur.refresh_from_db()
            u_ent_apres = _entreprise_utilisateur_cible(utilisateur)
            messages.success(request, "Utilisateur modifié avec succès.")
            if request.htmx and request.htmx.target == 'form-container':
                return render(request, 'user/utilisateurs/partial/form.html', {
                    'form': ModificationUtilisateurForm(
                        instance=utilisateur,
                        entreprise=u_ent_apres or entreprise_eff,
                        choix_entreprise=choix,
                        htmx_entreprise_url=htmx_ent_url,
                        peut_promouvoir_admin=prom_admin,
                    ),
                    'utilisateur': utilisateur,
                    'success': True,
                    'entreprise_affichage': None if choix else _get_entreprise_liee(request.user),
                })
            return redirect('user:liste-utilisateurs')
        elif request.htmx and request.htmx.target == 'form-container':
            return render(request, 'user/utilisateurs/partial/form.html', {
                'form': form,
                'utilisateur': utilisateur,
                'entreprise_affichage': None if choix else entreprise_eff,
            })
    return render(request, 'user/utilisateurs/form.html', {
        'form': form,
        'utilisateur': utilisateur,
        'titre': f"Modifier — {utilisateur.get_full_name()}",
        'entreprise_affichage': None if choix else entreprise_eff,
    })


@login_requis
def activer_desactiver_utilisateur(request, pk):
    utilisateur = get_object_or_404(User, pk=pk)
    if not (_est_super_admin(request.user) or request.user.a_la_permission(
        'acces_administration_utilisateurs'
    )):
        messages.error(request, "Accès refusé.")
        return redirect('entreprise:dashboard')
    if not (_est_super_admin(request.user)
            or _peut_modifier_utilisateur_hors_superadmin(request.user, utilisateur)):
        messages.error(request, "Vous ne pouvez pas modifier cet utilisateur.")
        return redirect('user:liste-utilisateurs')
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


@login_requis
def reinitialiser_mot_de_passe(request, pk):
    utilisateur = get_object_or_404(User, pk=pk)
    if not (_est_super_admin(request.user) or request.user.a_la_permission(
        'acces_administration_utilisateurs'
    )):
        messages.error(request, "Accès refusé.")
        return redirect('entreprise:dashboard')
    if not (_est_super_admin(request.user)
            or _peut_modifier_utilisateur_hors_superadmin(request.user, utilisateur)):
        messages.error(request, "Vous ne pouvez pas modifier cet utilisateur.")
        return redirect('user:liste-utilisateurs')
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


@login_requis
def supprimer_utilisateur(request, pk):
    utilisateur = get_object_or_404(User, pk=pk)
    if not (_est_super_admin(request.user) or request.user.a_la_permission(
        'acces_administration_utilisateurs'
    )):
        messages.error(request, "Accès refusé.")
        return redirect('entreprise:dashboard')
    if not (_est_super_admin(request.user)
            or _peut_modifier_utilisateur_hors_superadmin(request.user, utilisateur)):
        messages.error(request, "Vous ne pouvez pas supprimer cet utilisateur.")
        return redirect('user:liste-utilisateurs')
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


@login_requis
def gerer_acces_utilisateur(request, pk):
    """Gérer les accès dépôts et points de vente d'un utilisateur."""
    utilisateur = get_object_or_404(User, pk=pk)
    if not (_est_super_admin(request.user) or request.user.a_la_permission(
        'acces_administration_utilisateurs'
    )):
        messages.error(request, "Accès refusé.")
        return redirect('entreprise:dashboard')
    if not (_est_super_admin(request.user)
            or _peut_modifier_utilisateur_hors_superadmin(request.user, utilisateur)):
        messages.error(request, "Vous ne pouvez pas gérer les accès de cet utilisateur.")
        return redirect('user:liste-utilisateurs')
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

def _assert_peut_gerer_role(request, role):
    user = request.user
    if _est_super_admin(user):
        return True
    if not user.a_la_permission('acces_administration_utilisateurs'):
        return False
    ae = _get_entreprise_liee(user)
    return bool(ae and role.entreprise_id == ae.pk)


@login_requis
def liste_roles(request):
    if not (_est_super_admin(request.user) or request.user.a_la_permission(
        'acces_administration_utilisateurs'
    )):
        messages.error(request, "Accès réservé.")
        return redirect('entreprise:dashboard')

    super_adm = _est_super_admin(request.user)
    ent_liee = _get_entreprise_liee(request.user)

    if super_adm:
        roles = (
            Role.objects.select_related('entreprise')
            .prefetch_related('permissions__permission')
            .order_by('entreprise__nom', 'nom')
        )
        entreprise_ctx = True
    else:
        if not ent_liee:
            messages.error(request, "Aucune entreprise associée à votre compte.")
            return redirect('entreprise:dashboard')
        roles = (
            Role.objects.filter(entreprise=ent_liee)
            .select_related('entreprise')
            .prefetch_related('permissions__permission')
            .order_by('nom')
        )
        entreprise_ctx = ent_liee

    return render(request, 'user/roles/liste.html', {
        'roles': roles,
        'entreprise': entreprise_ctx,
        'est_super_admin': super_adm,
        'entreprise_affichage': None if super_adm else ent_liee,
    })


@login_requis
def creer_role(request):
    if not (_est_super_admin(request.user) or request.user.a_la_permission(
        'acces_administration_utilisateurs'
    )):
        messages.error(request, "Accès réservé.")
        return redirect('entreprise:dashboard')

    choix = _est_super_admin(request.user)
    ent_liee = _get_entreprise_liee(request.user)

    if not choix and not ent_liee:
        messages.error(request, "Aucune entreprise associée à votre compte.")
        return redirect('user:liste-roles')

    form = RoleForm(
        request.POST or None,
        show_entreprise=choix,
        entreprise_fixe=None if choix else ent_liee,
    )
    if request.method == "POST":
        if form.is_valid():
            form.save()
            messages.success(request, f"Rôle «\u00a0{form.instance.nom}\u00a0» créé.")
            if request.htmx and request.htmx.target == 'form-role':
                return render(request, 'user/roles/partial/form.html', {
                    'form': RoleForm(show_entreprise=choix, entreprise_fixe=None if choix else ent_liee),
                    'success': True,
                    'entreprise_affichage': None if choix else ent_liee,
                })
            return redirect('user:liste-roles')
        elif request.htmx and request.htmx.target == 'form-role':
            return render(request, 'user/roles/partial/form.html', {
                'form': form,
                'entreprise_affichage': None if choix else ent_liee,
            })
    return render(request, 'user/roles/form.html', {
        'form': form,
        'titre': "Créer un rôle",
        'est_super_admin': choix,
        'entreprise_affichage': None if choix else ent_liee,
    })


@login_requis
def modifier_role(request, pk):
    if not (_est_super_admin(request.user) or request.user.a_la_permission(
        'acces_administration_utilisateurs'
    )):
        messages.error(request, "Accès réservé.")
        return redirect('entreprise:dashboard')

    role = get_object_or_404(Role.objects.select_related('entreprise'), pk=pk)
    if not _assert_peut_gerer_role(request, role):
        messages.error(request, "Vous ne pouvez pas modifier ce rôle.")
        return redirect('user:liste-roles')

    choix = _est_super_admin(request.user)
    ent_liee = _get_entreprise_liee(request.user)

    form = RoleForm(
        request.POST or None,
        instance=role,
        show_entreprise=choix,
        entreprise_fixe=role.entreprise if not choix else None,
    )
    if request.method == "POST":
        if form.is_valid():
            form.save()
            role.refresh_from_db()
            messages.success(request, f"Rôle «\u00a0{role.nom}\u00a0» modifié.")
            if request.htmx and request.htmx.target == 'form-role':
                return render(request, 'user/roles/partial/form.html', {
                    'form': RoleForm(
                        instance=role,
                        show_entreprise=choix,
                        entreprise_fixe=role.entreprise if not choix else None,
                    ),
                    'role': role,
                    'success': True,
                    'entreprise_affichage': None if choix else ent_liee,
                })
            return redirect('user:liste-roles')
        elif request.htmx and request.htmx.target == 'form-role':
            return render(request, 'user/roles/partial/form.html', {
                'form': form,
                'role': role,
                'entreprise_affichage': None if choix else ent_liee,
            })
    return render(request, 'user/roles/form.html', {
        'form': form,
        'role': role,
        'titre': f"Modifier — {role.nom}",
        'est_super_admin': choix,
        'entreprise_affichage': None if choix else ent_liee,
    })


@login_requis
def supprimer_role(request, pk):
    role = get_object_or_404(Role, pk=pk)
    if not (_est_super_admin(request.user) or request.user.a_la_permission(
        'acces_administration_utilisateurs'
    )):
        messages.error(request, "Accès réservé.")
        return redirect('entreprise:dashboard')
    if not _assert_peut_gerer_role(request, role):
        messages.error(request, "Vous ne pouvez pas supprimer ce rôle.")
        return redirect('user:liste-roles')
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


@login_requis
def gerer_permissions_role(request, pk):
    role = get_object_or_404(Role, pk=pk)
    if not _assert_peut_gerer_role(request, role):
        messages.error(request, "Vous ne pouvez pas gérer les permissions de ce rôle.")
        return redirect('user:liste-roles')
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

@login_requis
def liste_permissions(request):
    permissions = (
        PermissionPersonnalisee.objects.order_by('nom').prefetch_related('roles__role')
    )
    return render(request, 'user/permissions/liste.html', {'permissions': permissions})


@login_requis
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


@login_requis
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


@login_requis
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

@login_requis
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
    peut_voir = (
        request.user.pk == pk
        or _est_super_admin(request.user)
        or (
            request.user.a_la_permission('acces_administration_utilisateurs')
            and _peut_modifier_utilisateur_hors_superadmin(request.user, utilisateur)
        )
    )
    if not peut_voir:
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
    if request.htmx and request.htmx.target == 'audit-container':
        return render(request, 'user/audit/partial/table_actions.html', contexte)
    return render(request, 'user/audit/index.html', contexte)
