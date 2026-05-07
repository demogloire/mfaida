from django.urls import path

from . import views

app_name = 'rh'

urlpatterns = [
    path('', views.hub_rh, name='hub'),

    # ── Employés ──────────────────────────────────────────────────────────
    path('employes/',                        views.liste_employes,       name='liste-employes'),
    path('employes/nouveau/',                views.creer_employe,        name='creer-employe'),
    path('employes/<int:pk>/',               views.detail_employe,       name='detail-employe'),
    path('employes/<int:pk>/modifier/',      views.modifier_employe,     name='modifier-employe'),
    path('employes/<int:pk>/toggle/',        views.toggle_statut_employe,  name='toggle-statut-employe'),
    path('employes/<int:pk>/imprimer/',      views.imprimer_fiche_employe, name='imprimer-employe'),
    path('employes/<int:employe_pk>/contrat/', views.nouveau_contrat,    name='nouveau-contrat'),

    # ── Départements ──────────────────────────────────────────────────────
    path('departements/',                    views.liste_departements,   name='liste-departements'),
    path('departements/nouveau/',            views.creer_departement,    name='creer-departement'),
    path('departements/<int:pk>/modifier/',  views.modifier_departement, name='modifier-departement'),

    # ── Avances sur salaire ───────────────────────────────────────────────
    path('avances/',                         views.liste_avances,        name='liste-avances'),
    path('avances/nouvelle/',                views.nouvelle_avance,      name='nouvelle-avance'),
    path('avances/<int:pk>/',                views.detail_avance,        name='detail-avance'),
    path('avances/<int:pk>/approuver/',      views.approuver_avance,     name='approuver-avance'),
    path('avances/<int:pk>/decaisser/',      views.decaisser_avance,     name='decaisser-avance'),
    path('avances/<int:pk>/rembourser/',     views.rembourser_avance,    name='rembourser-avance'),

    # ── Congés ────────────────────────────────────────────────────────────
    path('conges/',                          views.liste_conges,            name='liste-conges'),
    path('conges/nouveau/',                  views.nouvelle_demande_conge,  name='nouvelle-conge'),
    path('conges/nouveau/<int:employe_pk>/', views.nouvelle_demande_conge,  name='nouvelle-conge-employe'),
    path('conges/<int:pk>/',                 views.detail_conge,            name='detail-conge'),
    path('conges/<int:pk>/approuver/',       views.approuver_conge,         name='approuver-conge'),
    path('conges/<int:pk>/rejeter/',         views.rejeter_conge,           name='rejeter-conge'),
    path('conges/<int:pk>/annuler/',         views.annuler_conge,           name='annuler-conge'),

    # ── Présences ─────────────────────────────────────────────────────────
    path('presences/',                       views.tableau_presences,       name='tableau-presences'),
    path('presences/pointer/',               views.pointage_rapide,         name='pointage-rapide'),
    path('presences/<int:employe_pk>/',      views.pointer_presence,        name='pointer-presence'),

    # ── Bulletins de paie ─────────────────────────────────────────────────────
    path('bulletins/',                                         views.liste_bulletins,           name='liste-bulletins'),
    path('bulletins/nouveau/',                                 views.nouveau_bulletin,          name='nouveau-bulletin'),
    path('bulletins/<int:pk>/',                                views.detail_bulletin,           name='detail-bulletin'),
    path('bulletins/<int:pk>/ligne/ajouter/',                  views.ajouter_ligne_bulletin,    name='ajouter-ligne-bulletin'),
    path('bulletins/<int:pk>/ligne/<int:ligne_pk>/supprimer/', views.supprimer_ligne_bulletin,  name='supprimer-ligne-bulletin'),
    path('bulletins/<int:pk>/valider/',                        views.valider_bulletin,          name='valider-bulletin'),
    path('bulletins/<int:pk>/payer/',                          views.payer_bulletin,            name='payer-bulletin'),
    path('bulletins/<int:pk>/imprimer/',                       views.imprimer_bulletin,         name='imprimer-bulletin'),
]
