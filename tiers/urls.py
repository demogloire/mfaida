from django.urls import path
from . import views

app_name = 'tiers'

urlpatterns = [
    # ── Clients ──
    path('clients/', views.liste_clients, name='liste-clients'),
    path('clients/creer/', views.creer_client, name='creer-client'),
    path('clients/<int:pk>/modifier/', views.modifier_client, name='modifier-client'),
    path('clients/<int:pk>/toggle/', views.toggle_client, name='toggle-client'),
    path('clients/<int:pk>/supprimer/', views.supprimer_client, name='supprimer-client'),
    path('clients/<int:pk>/', views.detail_client, name='detail-client'),

    # ── Fournisseurs ──
    path('fournisseurs/', views.liste_fournisseurs, name='liste-fournisseurs'),
    path('fournisseurs/creer/', views.creer_fournisseur, name='creer-fournisseur'),
    path('fournisseurs/<int:pk>/modifier/', views.modifier_fournisseur, name='modifier-fournisseur'),
    path('fournisseurs/<int:pk>/toggle/', views.toggle_fournisseur, name='toggle-fournisseur'),
    path('fournisseurs/<int:pk>/supprimer/', views.supprimer_fournisseur, name='supprimer-fournisseur'),
    path('fournisseurs/<int:pk>/', views.detail_fournisseur, name='detail-fournisseur'),
]
