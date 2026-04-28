
from django.contrib import admin
from django.urls import path
from .views import (Dashboard, Information, ListEntreprise, EntrepriseStatus, ModifierEntreprise, 
                    BrancheAjouter, ListeDeBranche, BrancheStatus,ModifierBranche, Etagere, ListeLocation, 
                    EtagereModifier, UploadExcel, AjouterDepot, ListeDepot, ListeDepotTous, MajDepot, AjouterPoindeVente,
                    ListePVente, ListePVenteTous, MajPDVente, DeviseAjouter, DeviseListe, DeviseMaj, DeviseSupprimer)


app_name='entreprise'

urlpatterns = [
    path('dashboard/', Dashboard, name="dashboard"),
    path('information/', Information, name="entreprise-info"),
    path('listes/', ListEntreprise, name="entreprise-liste"),
    path('liste/<int:pk>/status', EntrepriseStatus, name="entreprise-maj"),
    path('<int:pk>/mod', ModifierEntreprise, name="entreprise-mod"),

    #Branche
    path('branche/', BrancheAjouter, name="entreprise-branche"),
    path('branche/listes/', ListeDeBranche, name="branche-liste"),
    path('branche/liste/<int:pk>', BrancheStatus, name="branche-maj"),
    path('branche/<int:pk>', ModifierBranche, name="branche-mod"),
    path('branche/upload_excel/etagere/<int:pk>', UploadExcel, name="branche-excel-upload-etagere"),

    #Etagere
    path('branche/<int:pk>/etagere', Etagere, name="etagere-ajouter"),
    path('branche/<int:pk>/etagere/liste', ListeLocation, name="etagere-liste"),
    path('branche/<int:branche_id>/etagere/<int:pk>', EtagereModifier, name="etagere-mod"),

    #Dépôt
    path('branche/<int:pk>/depot', AjouterDepot, name="depot-ajouter"),
    path('branche/<int:pk>/depot/liste', ListeDepot, name="depot-liste"),
    path('depot/listes/', ListeDepotTous, name="depot-liste-tous"),
    path('branche/<int:pk>/depot/maj', MajDepot, name="depot-maj"),

    #PVente
    path('branche/<int:pk>/pvente', AjouterPoindeVente, name="pvente-ajouter"),
    path('branche/<int:pk>/pvente/liste', ListePVente, name="pvente-liste"),
    path('pvente/listes/', ListePVenteTous, name="pvente-liste-tous"),
    path('branche/<int:pk>/pvente/maj', MajPDVente, name="pvente-maj"),

    #Devise
    path('devise/', DeviseAjouter, name="devise-ajouter"),
    path('devise/listes/', DeviseListe, name="devise-liste"),
    path('devise/<int:pk>/maj', DeviseMaj, name="devise-maj"),
    path('devise/<int:pk>/supprimer', DeviseSupprimer, name="devise-supprimer"),

]
