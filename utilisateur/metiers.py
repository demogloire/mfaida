"""Familles métier (postes), catalogue de permissions par défaut et synchronisation."""

VOIR_PRIX_ACHAT_HT = 'voir_prix_achat_ht'


def codes_permissions_catalogues() -> dict[str, str]:
    """Codes canoniques créés par migration avec libellés pour l’UI éventuelle."""
    return {
        'acces_configuration_entreprise': "Configurer l'entreprise (branches, dépôts, points de vente, devises)",
        'acces_configuration_catalogue': 'Gérer le catalogue produits (catégories, import)',
        'acces_module_tiers': 'Clients et fournisseurs',
        'acces_module_achat': 'Achats et réceptions',
        'acces_achat_bons_commande': 'Bons de commande (création, envoi et lignes — sous-module achats)',
        'acces_module_stock': 'Stock, inventaires et mouvements',
        'acces_stock_depot': 'Stock dépôt — niveaux, synthèse, mouvements, corrections internes',
        'acces_stock_pdv': 'Stock point de vente — niveaux, synthèse, mouvements, corrections internes',
        'acces_transfert_depot_pdv':   'Transfert stock Dépôt → Point de vente',
        'acces_transfert_pdv_depot':   'Transfert stock Point de vente → Dépôt',
        'acces_transfert_depot_depot': 'Transfert stock Dépôt → Dépôt',
        'acces_transfert_pdv_pdv':     'Transfert stock Point de vente → Point de vente',
        'acces_bons_ajustement': 'Bons d\'ajustement de stock (création, validation)',
        'acces_mise_a_ecart': 'Mise à l\'écart de stock (quarantaine, retrait)',
        'acces_campagnes_inventaire': 'Campagnes d\'inventaire (création, clôture)',
        'acces_module_vente': 'Facturation et ventes',
        'acces_facturation_proforma': 'Factures proforma (devis / commande — sous-module ventes)',
        'approuver_facture_proforma': 'Approuver ou rejeter les factures proforma (managers)',
        'acces_ventes_retournees': 'Ventes retournées (avoirs / retours — sous-module ventes)',
        'acces_module_finance': 'Finance et comptabilité (tableaux / écritures à venir)',
        'acces_module_rh': 'Ressources humaines (employés, contrats, présence, congés…)',
        'acces_module_caisse':       'Caisse — accès au module (sessions, transactions)',
        'ouvrir_session_caisse':     'Caisse — ouvrir une session',
        'cloturer_session_caisse':   'Caisse — soumettre la clôture de session',
        'approuver_cloture_caisse':  'Caisse — approuver ou rejeter la clôture (manager)',
        'depot_retrait_caisse':      'Caisse — dépôts et retraits manuels en cours de session',
        'acces_rapport_caisse':      'Caisse — rapports et historique complet',
        'acces_module_depenses': 'Dépenses caisse (liste, consultation)',
        'valider_depense': 'Valider ou annuler une dépense caisse',
        'acces_administration_utilisateurs': 'Utilisateurs, rôles, permissions et journal de connexion',
        VOIR_PRIX_ACHAT_HT: "Consulter les prix d'achat et les coûts (PA HT, valorisation)",
    }


def _famille_tokens():
    from .models import Role
    m = Role.FamilleMetier
    tous = frozenset(codes_permissions_catalogues().keys())
    tous_avec_prix = tous | frozenset({VOIR_PRIX_ACHAT_HT, 'approuver_facture_proforma'})
    admin_u = frozenset({'acces_administration_utilisateurs'})
    vente_pv = frozenset({
        'acces_module_vente',
        'acces_module_tiers',
        'acces_facturation_proforma',
        'acces_ventes_retournees',
        'acces_module_depenses',
        'valider_depense',
        'acces_module_stock',
        'acces_stock_pdv',
        'acces_module_caisse',
        'ouvrir_session_caisse',
        'cloturer_session_caisse',
    })
    finance = frozenset({
        'acces_module_finance',
        'acces_module_vente',
        'acces_module_tiers',
        'acces_facturation_proforma',
        'acces_ventes_retournees',
        'acces_module_rh',
        'acces_module_caisse',
        'acces_rapport_caisse',
        VOIR_PRIX_ACHAT_HT,
    })
    return {
        m.MANAGER: tous_avec_prix,
        m.ASSISTANT_MANAGER: tous_avec_prix - admin_u,
        m.CAISSIER: vente_pv,
        m.VENDEUR: vente_pv,
        m.MAGASINIER: frozenset({
            'acces_module_stock',
            'acces_stock_depot',
            'acces_transfert_depot_pdv',
            'acces_transfert_depot_depot',
            'acces_bons_ajustement',
            'acces_mise_a_ecart',
            'acces_campagnes_inventaire',
            'acces_module_achat',
            'acces_achat_bons_commande',
            'acces_module_tiers',
        }),
        m.FINANCIER: finance,
        m.COMPTABLE: finance,
        m.LOGISTICIEN: frozenset({
            'acces_module_stock',
            'acces_stock_depot',
            'acces_stock_pdv',
            'acces_transfert_depot_pdv',
            'acces_transfert_pdv_depot',
            'acces_transfert_depot_depot',
            'acces_transfert_pdv_pdv',
            'acces_bons_ajustement',
            'acces_mise_a_ecart',
            'acces_campagnes_inventaire',
            'acces_module_achat',
            'acces_achat_bons_commande',
            'acces_module_tiers',
            'acces_configuration_entreprise',
        }),
        m.RESSOURCES_HUMAINES: frozenset({
            'acces_module_rh',
        }),
        '': frozenset(),
    }


def permissions_pour_famille(famille):
    fm = famille or ''
    table = _famille_tokens()
    return table.get(fm, frozenset())


def synchroniser_permissions_role(role, famille=None, remplacer: bool = True) -> None:
    """
    Réapplique le jeu de permissions associé à la famille métier.
    Si famille vide : ne fait rien.
    """
    from .models import PermissionPersonnalisee, RolePermission

    fm = (famille or '').strip()
    if not fm:
        return
    codes = permissions_pour_famille(fm)
    if not codes:
        return
    perms = list(PermissionPersonnalisee.objects.filter(code__in=codes))
    if remplacer:
        RolePermission.objects.filter(role=role).delete()
    existants = {
        rp.permission_id for rp in RolePermission.objects.filter(role=role)
    }
    for p in perms:
        if p.pk not in existants:
            RolePermission.objects.get_or_create(role=role, permission=p)


def familles_liens_doc():
    """Texte court pour aides / formulaires (poste ↔ périmètre)."""
    from .models import Role
    m = Role.FamilleMetier
    return [
        (m.MANAGER, "Vue d'ensemble entreprise ; tous les modules, RH et l’administration des comptes."),
        (m.ASSISTANT_MANAGER, "Entreprise : comme le manager (y compris RH), sans administration des utilisateurs."),
        (m.CAISSIER, "Point de vente : ventes et clients."),
        (m.VENDEUR, "Point de vente : ventes et relation client."),
        (m.MAGASINIER, "Dépôt : stock et liaison réceptions / achats."),
        (m.FINANCIER, "Finance, suivi des flux commerciaux et RH pour la partie paie lorsque configurée."),
        (m.COMPTABLE, "Comptabilité, synthèses et RH pour données salariales liées à la compta."),
        (m.LOGISTICIEN,
            'Réception et flux physiques ; à étendre quand les écrans logistiques dédiés seront disponibles.'),
        (
            m.RESSOURCES_HUMAINES,
            'Lié à l’entreprise (tout le périmètre juridique) : module RH (employés, contrats, présence, '
            'congés…) ; autres droits peuvent être ajoutés au rôle si besoin.',
        ),
    ]
