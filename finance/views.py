"""Vues module Finance & Comptabilité."""

from django.db.models import Sum
from django.shortcuts import render

from depenses.models import Depense
from stock.access import (
    get_entreprise_utilisateur,
    queryset_points_vente_visibles,
    utilisateur_est_admin,
)
from utilisateur.decorators import login_requis


@login_requis
def hub_finance(request):
    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    pdvs_vis   = queryset_points_vente_visibles(request.user, entreprise, admin)
    qs_dep     = Depense.objects.filter(point_vente__in=pdvs_vis)

    stats          = qs_dep.filter(statut='VALIDEE').aggregate(total=Sum('montant'))
    nb_en_attente  = qs_dep.filter(statut='BROUILLON').count()

    modules_avenir = [
        {
            'titre':          'Plan comptable',
            'description':    'Comptes, classes, nature de comptes',
            'icone':          'ti ti-hierarchy',
            'bg':             '#f3e5f5',
            'color':          '#7b1fa2',
            'fonctionnalites': [
                'Classes et comptes OHADA (1 à 8)',
                'Comptes auxiliaires clients / fournisseurs',
                'Paramétrage de la codification',
            ],
        },
        {
            'titre':          'Journaux comptables',
            'description':    'Saisie des écritures, lettrage',
            'icone':          'ti ti-notebook',
            'bg':             '#e8eaf6',
            'color':          '#3949ab',
            'fonctionnalites': [
                'Journal de ventes',
                "Journal d'achats",
                'Journal de caisse',
                'Journal des opérations diverses',
            ],
        },
        {
            'titre':          'Grand Livre & Balance',
            'description':    'Consultation et impression comptable',
            'icone':          'ti ti-book',
            'bg':             '#e3f2fd',
            'color':          '#1565c0',
            'fonctionnalites': [
                'Grand livre par compte',
                'Balance des comptes',
                'Rapprochement bancaire',
            ],
        },
        {
            'titre':          'Bilan & Compte de résultats',
            'description':    'États financiers périodiques',
            'icone':          'ti ti-chart-pie',
            'bg':             '#e8f5e9',
            'color':          '#2e7d32',
            'fonctionnalites': [
                'Bilan actif / passif',
                'Compte de résultats',
                'Tableau des flux de trésorerie',
            ],
        },
        {
            'titre':          'Budget & Prévisions',
            'description':    'Planification financière et suivi budgétaire',
            'icone':          'ti ti-target',
            'bg':             '#fff8e1',
            'color':          '#f57f17',
            'fonctionnalites': [
                'Budget annuel par département',
                'Suivi des écarts',
                'Prévisions de trésorerie',
            ],
        },
        {
            'titre':          'TVA & Impôts',
            'description':    'Déclarations fiscales et taxes',
            'icone':          'ti ti-building-bank',
            'bg':             '#fce4ec',
            'color':          '#c62828',
            'fonctionnalites': [
                'Calcul automatique TVA',
                'Déclaration mensuelle / trimestrielle',
                'Registre des taxes',
            ],
        },
        {
            'titre':          'Rapports financiers',
            'description':    'Tableaux de bord et analyses',
            'icone':          'ti ti-chart-bar',
            'bg':             '#e0f2f1',
            'color':          '#00695c',
            'fonctionnalites': [
                'KPI financiers',
                'Évolution CA / charges',
                'Export Excel / PDF',
            ],
        },
        {
            'titre':          'Lettres de change & Effets',
            'description':    'Gestion des effets commerciaux',
            'icone':          'ti ti-credit-card',
            'bg':             '#e8eaf6',
            'color':          '#4527a0',
            'fonctionnalites': [
                "Émission d'effets",
                'Suivi des échéances',
                'Portefeuille effets',
            ],
        },
    ]

    return render(request, 'finance/hub.html', {
        'nb_depenses_attente': nb_en_attente,
        'total_depenses':      stats['total'] or 0,
        'modules_avenir':      modules_avenir,
    })
