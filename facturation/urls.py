from django.urls import path

from . import views

app_name = 'facturation'

urlpatterns = [
    path('', views.liste_factures, name='liste-factures'),
    path('nouvelle/', views.nouvelle_facture, name='nouvelle-facture'),
    path('<int:pk>/', views.detail_facture, name='detail-facture'),
    path('<int:pk>/lignes/', views.ajouter_ligne_facture, name='ajouter-ligne-facture'),
    path('<int:pk>/lignes/<int:ligne_pk>/supprimer/', views.supprimer_ligne_facture, name='supprimer-ligne-facture'),
    path('<int:pk>/valider/', views.valider_facture, name='valider-facture'),
]
