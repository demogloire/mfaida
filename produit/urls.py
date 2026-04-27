from django.urls import path
from . import views

app_name = 'produit'

urlpatterns = [
    # Catégories
    path('categories/', views.liste_categories, name='categories'),
    path('categories/creer/', views.creer_categorie, name='categorie-creer'),
    path('categories/<int:pk>/modifier/', views.modifier_categorie, name='categorie-modifier'),
    path('categories/<int:pk>/supprimer/', views.supprimer_categorie, name='categorie-supprimer'),

    # Sous-catégories
    path('sous-categories/', views.liste_sous_categories, name='sous-categories'),
    path('sous-categories/creer/', views.creer_sous_categorie, name='sous-categorie-creer'),
    path('sous-categories/<int:pk>/modifier/', views.modifier_sous_categorie, name='sous-categorie-modifier'),
    path('sous-categories/<int:pk>/supprimer/', views.supprimer_sous_categorie, name='sous-categorie-supprimer'),

    # Produits
    path('', views.liste_produits, name='liste'),
    path('creer/', views.creer_produit, name='creer'),
    path('<int:pk>/', views.detail_produit, name='detail'),
    path('<int:pk>/modifier/', views.modifier_produit, name='modifier'),
    path('<int:pk>/toggle/', views.toggle_produit, name='toggle'),
    path('<int:pk>/supprimer/', views.supprimer_produit, name='supprimer'),

    # Import Excel
    path('import/', views.import_produits, name='import'),
    path('import/modele/', views.telecharger_modele_excel, name='import-modele'),
]
