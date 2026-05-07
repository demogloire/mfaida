from django.urls import path
from . import views

app_name = 'depenses'

urlpatterns = [
    path('',                    views.liste_depenses,  name='liste-depenses'),
    path('nouvelle/',           views.nouvelle_depense, name='nouvelle-depense'),
    path('<int:pk>/',           views.detail_depense,  name='detail-depense'),
    path('<int:pk>/valider/',   views.valider_depense,  name='valider-depense'),
    path('<int:pk>/annuler/',   views.annuler_depense,  name='annuler-depense'),
    path('<int:pk>/imprimer/',  views.imprimer_depense, name='imprimer-depense'),

    # Paramètres — Types de dépenses
    path('parametres/types/',                   views.liste_types_depense,    name='liste-types-depense'),
    path('parametres/types/creer/',             views.creer_type_depense,     name='creer-type-depense'),
    path('parametres/types/<int:pk>/modifier/', views.modifier_type_depense,  name='modifier-type-depense'),
    path('parametres/types/<int:pk>/supprimer/',views.supprimer_type_depense, name='supprimer-type-depense'),
]
