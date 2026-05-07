from django.urls import path
from . import views

app_name = 'caisse'

urlpatterns = [
    path('',                             views.dashboard_caisse,  name='dashboard'),
    path('sessions/',                    views.liste_sessions,    name='liste-sessions'),
    path('sessions/ouvrir/',             views.ouvrir_session,    name='ouvrir-session'),
    path('sessions/<int:pk>/',           views.detail_session,    name='detail-session'),
    path('sessions/<int:pk>/depot-retrait/', views.depot_retrait, name='depot-retrait'),
    path('sessions/<int:pk>/cloturer/',  views.soumettre_cloture, name='soumettre-cloture'),
    path('sessions/<int:pk>/approuver/', views.approuver_cloture, name='approuver-cloture'),
    path('sessions/<int:pk>/rejeter/',   views.rejeter_cloture,   name='rejeter-cloture'),
    path('sessions/<int:pk>/rapport/',   views.rapport_session,   name='rapport-session'),
    path('clients/',                     views.liste_clients_caisse,     name='liste-clients'),
    path('clients/autocomplete/',        views.api_autocomplete_clients, name='api-autocomplete-clients'),
    path('clients/<int:client_pk>/',     views.compte_client,            name='compte-client'),

    # Avances RH — file de décaissement caissier
    path('avances/',                     views.avances_a_decaisser,      name='avances-a-decaisser'),
]
