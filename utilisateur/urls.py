from django.urls import path
from . import views

app_name = 'user'

urlpatterns = [
    # ── Authentification ───────────────────────────────────────────────────────
    path('superuser/', views.AdminUser, name='ajouter-superadmin'),
    path('connexion/', views.Connexion, name='connexion'),
    path('logout/', views.logout_view, name='logout'),
    path('mot-de-passe-oublie/', views.mot_de_passe_oublie, name='mot-de-passe-oublie'),

    # ── Profil personnel ───────────────────────────────────────────────────────
    path('profil/', views.mon_profil, name='mon-profil'),
    path('profil/modifier/', views.modifier_profil, name='modifier-profil'),
    path('profil/mot-de-passe/', views.changer_mot_de_passe, name='changer-mot-de-passe'),

    # ── CRUD Utilisateurs ──────────────────────────────────────────────────────
    path('utilisateurs/', views.liste_utilisateurs, name='liste-utilisateurs'),
    path('utilisateurs/creer/', views.creer_utilisateur, name='creer-utilisateur'),
    path('utilisateurs/<int:pk>/modifier/', views.modifier_utilisateur, name='modifier-utilisateur'),
    path('utilisateurs/<int:pk>/toggle/', views.activer_desactiver_utilisateur, name='toggle-utilisateur'),
    path('utilisateurs/<int:pk>/reset/', views.reinitialiser_mot_de_passe, name='reset-mdp-utilisateur'),
    path('utilisateurs/<int:pk>/supprimer/', views.supprimer_utilisateur, name='supprimer-utilisateur'),
    path('utilisateurs/<int:pk>/activite/', views.activite_utilisateur, name='activite-utilisateur'),
    path('utilisateurs/<int:pk>/acces/', views.gerer_acces_utilisateur, name='acces-utilisateur'),

    # ── CRUD Rôles ─────────────────────────────────────────────────────────────
    path('roles/', views.liste_roles, name='liste-roles'),
    path('roles/creer/', views.creer_role, name='creer-role'),
    path('roles/<int:pk>/modifier/', views.modifier_role, name='modifier-role'),
    path('roles/<int:pk>/permissions/', views.gerer_permissions_role, name='permissions-role'),
    path('roles/<int:pk>/supprimer/', views.supprimer_role, name='supprimer-role'),

    # ── CRUD Permissions ───────────────────────────────────────────────────────
    path('permissions/', views.liste_permissions, name='liste-permissions'),
    path('permissions/creer/', views.creer_permission, name='creer-permission'),
    path('permissions/<int:pk>/modifier/', views.modifier_permission, name='modifier-permission'),
    path('permissions/<int:pk>/supprimer/', views.supprimer_permission, name='supprimer-permission'),

    # ── Journal ────────────────────────────────────────────────────────────────
    path('journal/', views.journal_connexions, name='journal-connexions'),

    # ── Paramètres généraux (Générale) ─────────────────────────────────────────
    path('parametres/securite/', views.securite, name='securite'),
    path('parametres/signature/', views.signature, name='signature'),
    path('parametres/audit/', views.audit_personnel, name='audit-personnel'),
]
