from django.urls import path
from . import views

app_name = 'rapports'

urlpatterns = [
    # Hub
    path('',                      views.hub_rapports,            name='hub'),

    # ── Ventes & Facturation ─────────────────────────────────────────────
    path('ventes/',               views.rapport_ventes,          name='ventes'),
    path('ventes/produits/',      views.rapport_produits_vendus,  name='produits-vendus'),
    path('ventes/creances/',      views.rapport_creances,         name='creances'),
    path('ventes/retours/',       views.rapport_retours_vente,    name='retours-vente'),
    path('ventes/benefice/',      views.rapport_benefice,         name='benefice'),

    # ── Achats ───────────────────────────────────────────────────────────
    path('achats/',               views.rapport_achats,           name='achats'),

    # ── Stock ────────────────────────────────────────────────────────────
    path('stock/inventaire/',     views.rapport_inventaire,       name='inventaire'),
    path('stock/mouvements/',     views.rapport_mouvements_stock, name='mouvements-stock'),
    path('stock/ruptures/',       views.rapport_ruptures,         name='ruptures'),
    path('stock/expirations/',    views.rapport_expirations,      name='expirations'),

    # ── RH ───────────────────────────────────────────────────────────────
    path('rh/presences/',         views.rapport_presences_rh,     name='presences-rh'),
    path('rh/masse-salariale/',   views.rapport_masse_salariale,  name='masse-salariale'),
    path('rh/avances/',           views.rapport_avances_rh,       name='avances-rh'),

    # ── Caisse ───────────────────────────────────────────────────────────
    path('caisse/',               views.rapport_caisse,           name='caisse'),

    # ── Dépenses ─────────────────────────────────────────────────────────
    path('depenses/',             views.rapport_depenses,         name='depenses'),

    # ── Tiers ────────────────────────────────────────────────────────────
    path('tiers/clients/',        views.rapport_clients,          name='clients'),
    path('tiers/creances-age/',   views.rapport_vieillissement,   name='vieillissement'),
]
