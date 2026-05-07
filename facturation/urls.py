from django.urls import path

from . import views
from . import proforma_views
from . import retour_views
from . import approbation_views

app_name = 'facturation'

urlpatterns = [
    # ── Factures ──────────────────────────────────────────────────────────
    path('', views.liste_factures, name='liste-factures'),
    path('nouvelle/', views.nouvelle_facture, name='nouvelle-facture'),
    path(
        'nouvelle/client-rapide/',
        views.creer_client_rapide_facture,
        name='client-rapide-facture',
    ),
    path(
        'api/clients-autocomplete/',
        views.clients_autocomplete,
        name='clients-autocomplete',
    ),
    path(
        '<int:pk>/api/produits-autocomplete/',
        views.produits_autocomplete_facture,
        name='produits-autocomplete-facture',
    ),
    path(
        '<int:pk>/imprimer/ticket/',
        views.imprimer_facture_ticket,
        name='imprimer-facture-ticket',
    ),
    path(
        '<int:pk>/imprimer/ticket-detail/',
        views.imprimer_facture_ticket_detail,
        name='imprimer-facture-ticket-detail',
    ),
    path(
        '<int:pk>/imprimer/a4/',
        views.imprimer_facture_a4,
        name='imprimer-facture-a4',
    ),
    path('<int:pk>/', views.detail_facture, name='detail-facture'),
    path('<int:pk>/lignes/', views.ajouter_ligne_facture, name='ajouter-ligne-facture'),
    path(
        '<int:pk>/lignes/<int:ligne_pk>/supprimer/',
        views.supprimer_ligne_facture,
        name='supprimer-ligne-facture',
    ),
    path('<int:pk>/supprimer/', views.supprimer_facture, name='supprimer-facture'),
    path('<int:pk>/paiement/', views.enregistrer_paiement_facture, name='paiement-facture'),
    path('paiement/<int:paiement_pk>/recu/', views.imprimer_recu_paiement, name='recu-paiement'),
    path('<int:pk>/terminer-caisse/', views.terminer_facture_caisse, name='terminer-facture-caisse'),
    path('<int:pk>/valider/', views.valider_facture, name='valider-facture'),

    # ── Proformas ─────────────────────────────────────────────────────────
    path('proforma/', proforma_views.liste_proformas, name='liste-proformas'),
    path('proforma/nouvelle/', proforma_views.nouvelle_proforma, name='nouvelle-proforma'),
    path(
        'proforma/api/clients-autocomplete/',
        proforma_views.clients_autocomplete_proforma,
        name='clients-autocomplete-proforma',
    ),
    path(
        'proforma/<int:pk>/api/produits-autocomplete/',
        proforma_views.produits_autocomplete_proforma,
        name='produits-autocomplete-proforma',
    ),
    path('proforma/<int:pk>/', proforma_views.detail_proforma, name='detail-proforma'),
    path(
        'proforma/<int:pk>/lignes/',
        proforma_views.ajouter_ligne_proforma,
        name='ajouter-ligne-proforma',
    ),
    path(
        'proforma/<int:pk>/lignes/<int:ligne_pk>/supprimer/',
        proforma_views.supprimer_ligne_proforma,
        name='supprimer-ligne-proforma',
    ),
    path(
        'proforma/<int:pk>/supprimer/',
        proforma_views.supprimer_proforma,
        name='supprimer-proforma',
    ),
    path(
        'proforma/<int:pk>/soumettre/',
        proforma_views.soumettre_proforma,
        name='soumettre-proforma',
    ),
    path(
        'proforma/<int:pk>/approuver/',
        proforma_views.approuver_proforma,
        name='approuver-proforma',
    ),
    path(
        'proforma/<int:pk>/rejeter/',
        proforma_views.rejeter_proforma,
        name='rejeter-proforma',
    ),
    path(
        'proforma/<int:pk>/convertir/',
        proforma_views.convertir_en_brouillon,
        name='convertir-proforma',
    ),
    path(
        'proforma/<int:pk>/imprimer/',
        proforma_views.imprimer_proforma,
        name='imprimer-proforma',
    ),

    # ── Hub approbations ─────────────────────────────────────────────────
    path('approbations/', approbation_views.hub_approbations, name='hub-approbations'),

    # ── Ventes retournées ─────────────────────────────────────────────────
    path('retours/', retour_views.liste_retours, name='liste-retours'),
    path('retours/nouveau/', retour_views.nouveau_retour, name='nouveau-retour'),
    path(
        'retours/nouveau/<int:facture_pk>/',
        retour_views.detail_retour_init,
        name='detail-retour-init',
    ),
    path('retours/<int:pk>/', retour_views.detail_retour, name='detail-retour'),
    path('retours/<int:pk>/soumettre/', retour_views.soumettre_retour,  name='soumettre-retour'),
    path('retours/<int:pk>/approuver/', retour_views.approuver_retour, name='approuver-retour'),
    path('retours/<int:pk>/rejeter/',   retour_views.rejeter_retour,   name='rejeter-retour'),
    path('retours/<int:pk>/annuler/',   retour_views.annuler_retour,   name='annuler-retour'),
]
