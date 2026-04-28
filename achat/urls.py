from django.urls import path
from . import views

app_name = 'achat'

urlpatterns = [
    # ── Ordres d'achat ──
    path('commandes/', views.liste_commandes, name='liste-commandes'),
    path('commandes/creer/', views.creer_commande, name='creer-commande'),
    path('commandes/<int:pk>/', views.detail_commande, name='detail-commande'),
    path('commandes/<int:pk>/export/excel/', views.export_commande_excel, name='export-commande-excel'),
    path('commandes/<int:pk>/export/pdf/', views.export_commande_pdf, name='export-commande-pdf'),
    path('commandes/<int:pk>/modifier/', views.modifier_commande, name='modifier-commande'),
    path('commandes/<int:pk>/annuler/', views.annuler_commande, name='annuler-commande'),

    # ── Lignes (HTMX) ──
    path('commandes/<int:pk>/lignes/ajouter/', views.ajouter_ligne, name='ajouter-ligne'),
    path('commandes/<int:pk>/lignes/importer/', views.import_lignes_commande, name='import-lignes-commande'),
    path(
        'commandes/<int:pk>/lignes/modele-excel/',
        views.telecharger_modele_lignes_bc,
        name='modele-excel-lignes-bc',
    ),
    path('lignes/<int:pk>/supprimer/', views.supprimer_ligne, name='supprimer-ligne'),

    # ── Réceptions ──
    path('receptions/', views.liste_receptions, name='liste-receptions'),
    path('receptions/creer/<int:ordre_pk>/', views.creer_reception, name='creer-reception'),
    path('receptions/<int:pk>/', views.detail_reception, name='detail-reception'),
    path('receptions/<int:pk>/valider/', views.valider_reception, name='valider-reception'),
]
