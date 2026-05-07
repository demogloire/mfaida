# M-Faida — Système de Gestion Commerciale

Application web de gestion commerciale complète développée avec **Django**, **HTMX** et **Bootstrap 5**.

---

## Fonctionnalités

### Entreprise
- Gestion des entreprises (multi-entreprises)
- Branches (avec préfixes documents : facture, proforma, **bon de commande** `init_bdcommande`, etc.), dépôts, points de vente
- Devises et taux de change
- Étagères / emplacements de stockage
- Liste des branches avec **affichage de l’entreprise** sur chaque carte

### Tiers (`tiers`)
- **Clients** rattachés à une branche : code automatique **`CLI-` + numéro sur 6 chiffres**, **unique par entreprise** (contrainte base + champ `entreprise`)
- **Fournisseurs** par entreprise (bons de commande, achats)
- Listes filtrées : administrateur applicatif (tout voir) / utilisateur limité à son entreprise ; recherche par code, nom, branche, entreprise

### Achats (`achat`)
- **Bons de commande fournisseur** : dépôt / point de vente, lignes produits, fusion des lignes identiques, import Excel des lignes
- **Réceptions** marchandises
- **Exports** : Excel « données » ; **PDF** type document commercial (logo entreprise via storage Django, méta-document, bloc émetteur/fournisseur, QR code, totaux, signature **utilisateur créateur** si `Profil.signature` est renseignée)
- Numéro de bon de commande généré avec le **préfixe `Branche.init_bdcommande`** (sinon branche siège / première branche ; repli `BC-`)

### Catalogue Produits
- Catégories et sous-catégories
- Produits rattachés à une **entreprise** ; **SKU unique par entreprise**
- Prix, TVA, marge calculée automatiquement
- Méthodes de gestion de stock (FIFO, FEFO, LIFO)
- Import en masse via fichier Excel (.xlsx), liste et détail produits enrichis

### Stock (`stock`)
Application dédiée : URLs sous `/stock/` (voir `stock/urls.py`).

**Périmètres séparés** : stock **dépôt** (sans point de vente) et stock **points de vente** (même logique métier avec `depot_source` + `pointvente` sur les lignes).

- **Liste des niveaux par lots** : mouvements actifs ; **constats d’inventaire** (`quantité active` à 0) peuvent être listés pour la traçabilité.
- **Synthèse par produit** : agrégats `Stock`, mises à l’écart, valorisation indicative.
- **Mouvements** (historique) et **exports** Excel / PDF (`stock/export_tabular.py`, `stock/export_views.py`).
- **Mise à l’écart** : retrait du disponible sur un lot sans sortie physique comptabilisée comme vente (`StockMiseAEcart`).
- **Ajustement manuel** : entrées/sorties sur lignes encore actives, regroupées en **bons d’ajustement** (`BonAjustementStock`, `LigneBonAjustement`).
- **Correction interne** : mise à jour des métadonnées d’une ligne (lot, dates fabrication/expiration, emplacement référencé ou code libre, marque, conditionnement) sans modifier les quantités ni l’agrégé ; périmètres dépôt / PDV ; motif obligatoire (trace dans `MouvementStock.motif`).
- **Inventaires** : campagne par dépôt ou PDV ; saisie / import Excel des quantités physiques (`stock/inventaire_excel_import.py`) ; disponibilité théorique basée sur la **somme des `quantite_active`** des lots (alignée avec FIFO / FEFO / LIFO en cas de déficit) ; à la clôture : excédent = nouvelle ligne inventaire ; manquant = consommation des lots puis ligne de constat ; intégration comptable possible (`finance/posting` selon configuration).
- **Réception → stock** : application validée depuis `stock/reception_stock.py` avec cohérence dépôt / PDV (`MouvementStock`, ligne `Stock`).

**Contrôle d’accès stock** : `stock/access.py` (visibilité et droits **modifier** par dépôt / point de vente selon `Profil`).

### Facturation (`facturation`)
- Factures clients avec lignes produits et mouvements de stock
- **Proformas** (devis) : brouillon → soumis → approuvé → converti en facture
- **Retours vente** : workflow soumission / approbation / avoir
- **Hub approbations** : validation proformas et retours en un seul endroit
- Paiements multiples par facture (espèces, Mobile Money, carte, crédit)
- Impression facture A4, ticket et ticket détaillé

### Caisse (`caisse`)
- **Sessions de caisse** : ouverture / fermeture avec bilan automatique
- Encaissement des factures en attente (`statut = EN_CAISSE`)
- Comptes clients : solde, transactions, historique
- **Décaissement des avances sur salaire** approuvées (sortie de fonds tracée)
- Dashboard caisse avec KPIs en temps réel

### Dépenses (`depenses`)
- Création et validation de dépenses par point de vente
- **Types de dépenses configurables** (catégories personnalisables)
- Impression de reçus de dépense

### Ressources Humaines (`rh`)
- **Annuaire employés** : fiche complète (photo, état civil, contrat, département)
- **Contrats** (CDI, CDD, stage, prestataire) avec date début/fin
- **Départements** et organigramme
- **Présences & Pointage** : saisie quotidienne, tableau mensuel, rapport
- **Congés** : demande → approbation manager → clôture (annuel, maladie, maternité…)
- **Avances sur salaire** : demande → approbation → décaissement caisse → retenue sur bulletin
- **Bulletins de paie** : génération automatique (salaire de base, avantages, déductions, avances retenues, net à payer) ; workflow brouillon → validé → payé
- Impression fiche employé

### Comptabilité & Finance (`finance`)
- **Hub Finance** : vue d'ensemble des modules financiers actifs
- Accès centralisé : Dépenses, Caisse, Facturation, Bulletins de paie
- Modules à venir : Plan comptable, Journaux, Grand Livre, Bilan, Budget, TVA

### Rapports (`rapports`)
- **14 rapports opérationnels** couvrant tous les modules métier
- Filtrage par **branche** (pour les admins) ou périmètre utilisateur
- **Export PDF** optimisé impression (déclenchement automatique `window.print()`)
- Permissions granulaires par section de rapport

| Catégorie | Rapports disponibles |
|---|---|
| Ventes & Facturation | CA, Bénéfice brut & net, Produits vendus, Créances impayées, Retours |
| Stock | Inventaire valorisé, Mouvements, Ruptures & alertes, Expirations |
| Achats | Achats par fournisseur, commandes en attente |
| Ressources Humaines | Présences, Masse salariale, Avances salaire |
| Caisse & Trésorerie | Sessions, encaissements par mode de paiement |
| Dépenses | Par type, catégorie, point de vente, évolution mensuelle |
| Clients & Tiers | Top clients, Vieillissement des créances |

### Utilisateurs
- Authentification et gestion des sessions
- Rôles et permissions personnalisées (18+ migrations de permissions)
- Accès granulaires par dépôt, point de vente et module métier
- Profil : photo, **signature image** (PDF bons de commande), etc.
- Journal des connexions et actions (audit)

---

## Stack technique

| Composant | Technologie |
|-----------|-------------|
| Backend | Python 3.x / **Django 4.0** |
| Frontend | Bootstrap 5, HTMX (`django-htmx`), Tabler Icons ; notifications **toast** Bootstrap (`templates/toast.html`, `static/toasts.js`) + messages Django |
| Base de données | MySQL |
| Templates | Django Templates + django-widget-tweaks |
| Import Excel | openpyxl |
| PDF / QR (achats) | reportlab, qrcode, Pillow |
| Auth | Django Auth (`Profil` — AbstractUser étendu) |

---

## Installation

### Prérequis
- Python 3.10+
- MySQL
- pip

### Étapes

```bash
# 1. Cloner le dépôt
git clone https://github.com/demogloire/mfaida.git
cd mfaida

# 2. Créer et activer l'environnement virtuel
python -m venv env
env\Scripts\activate        # Windows
# source env/bin/activate   # Linux/Mac

# 3. Installer les dépendances
pip install -r requirements.txt

# 4. Configurer la base de données
# Adapter DATABASES dans core/settings.py avec vos identifiants MySQL

# 5. Appliquer les migrations
python manage.py migrate

# 6. Créer un super-utilisateur
python manage.py createsuperuser

# 7. Lancer le serveur
python manage.py runserver
```

---

## Configuration optionnelle (PDF / QR)

Dans `core/settings.py` (ou variable d’environnement équivalente) :

- **`SITE_PUBLIC_URL`** : URL publique de l’application (ex. `https://mondomaine.com`). Si défini, le QR code du PDF bon de commande pointe vers la fiche du BC ; sinon une chaîne interne est encodée.
- **`BC_PDF_FOOTER_TEXT`** : texte personnalisé du pied de page PDF (sinon libellé par défaut avec référence interne).

---

## Notifications (succès, erreurs, etc.)

Les retours utilisateur passent par `django.contrib.messages` et **`MESSAGE_TAGS`** dans `core/settings.py` (libellés adaptés aux classes Bootstrap : `success`, `danger`, etc.).

- Après redirection, les messages sont rendus dans **`templates/toast.html`** (coins supérieurs droits) avec un titre (« Succès », « Erreur », …).
- Pour les **succès**, une ligne de confirmation rappelle que **l’activité s’est effectuée avec succès**.
- Les réponses **HTMX** peuvent faire apparaître les mêmes toasts via `utilisateur.middleware.HtmxMessageMiddleware` et l’écoute du déclencheur `messages` dans `static/toasts.js`.

---

## Structure du projet

```
m-faida/
├── core/               # Configuration Django (settings, urls, context_processors)
├── entreprise/         # Entreprises, branches, dépôts, PdV, devises, produits, dashboard
├── tiers/              # Clients et fournisseurs
├── achat/              # Bons de commande, réceptions, exports Excel/PDF
├── utilisateur/        # Utilisateurs, rôles, permissions (18+ migrations)
├── produit/            # Vues / templates catalogue (réexport entreprise.Produit)
├── stock/              # Stock dépôt/PDV, inventaires, réception, transferts, exports
├── finance/            # Hub Comptabilité & Finance, écritures (OHADA)
├── facturation/        # Factures, proformas, retours, approbations, paiements
├── caisse/             # Sessions de caisse, encaissements, décaissements
├── depenses/           # Dépenses par point de vente, types configurables
├── rh/                 # Employés, contrats, présences, congés, avances, bulletins
├── rapports/           # 14 rapports multi-modules avec export PDF
├── templates/          # Templates HTML globaux et par module
├── static/             # Fichiers statiques (CSS, JS)
└── media/              # Fichiers téléversés (logos, signatures, etc.)
```

---

### Collectstatic (production)

```bash
python manage.py collectstatic --noinput
```

Configurer `STATIC_ROOT` et le serveur (Nginx, etc.) comme d’usage sur Django.

---

## Import Excel des produits

Un fichier modèle Excel est disponible depuis l’interface catalogue.

Colonnes typiques : `nom`, `categorie`, `sous_categorie`, SKU, `code_barre`, `description`, prix, TVA, unité, etc. (voir écran d’import dans l’application).

---

## Journal des modifications (principales évolutions)

- **Apps `tiers` et `achat`** : modularisation clients/fournisseurs et cycle d’achat (commandes, réceptions), migrations depuis l’ancienne structure `entreprise`.
- **Produits** : SKU et unicité **par entreprise** ; imports et écrans liste/détail adaptés.
- **Clients** : génération de code **`CLI-xxxxxxxx`** contrôlée en base (**unicité entreprise + code**) ; formulaires et listes (colonnes entreprise / branche pour les admins).
- **Bons de commande** : numérotation basée sur **`init_bdcommande`** de la branche liée au dépôt (sinon siège) ; formulaire **date de livraison prévue** au format ISO pour navigateurs français ; liste avec entreprise, dépôt, point de vente et devise.
- **PDF bon de commande** : mise en page « document commercial », logo entreprise, QR, signature du créateur, devise.
- **Interface** : redesign de plusieurs écrans (dépôts, devises, points de vente, branches…), barres latérales achat/tiers, configuration CSRF pour requêtes HTMX.
- **Dépendances** : ajout de **openpyxl**, **reportlab**, **qrcode** pour imports et exports PDF.

### Récent (stock, UX)

- Inventaire : dispo « théorique » alignée sur **lots actifs** ; clôture avec traçabilité **physique / constat** ; import Excel campagne ; sous-menu navigation **Correction interne** ; hub stock.
- **Correction interne** des lignes (lot, DLC/DLUO, emplacement, marque, conditionnement) sans mouvement de quantités.
- **Toasts Bootstrap** harmonisés (titres FR, phrase de confirmation sur les succès) ; **`toasts.js`** pour HTMX.
- Droits **`voir prix achat HT`** (permission profil / template tags) où applicable à l’ERP.


### Recent (RH, Caisse, Finance, Rapports, UI)

- **Module RH complet** : annuaire employes, contrats, departements, presences & pointage, conges (workflow approbation manager), avances sur salaire (workflow caisse), bulletins de paie automatiques avec retenues.
- **Caisse enrichie** : sessions ouverture/fermeture, encaissement factures EN_CAISSE, decaissement avances RH (sortie de fonds tracee), comptes clients, dashboard KPIs.
- **Depenses** : types configurables par entreprise, validation, impression recus.
- **Hub Comptabilite & Finance** (finance/) : vue d ensemble avec modules actifs et modules a venir (Plan comptable, Journaux, Grand Livre, Bilan, Budget, TVA).
- **Module Rapports** (rapports/) : 14 rapports couvrant Ventes, Stock, Achats, RH, Caisse, Depenses et Tiers - filtrage multi-branche/entreprise, export PDF print-optimise, permissions granulaires.
- **Dashboard principal redesigne** : KPIs temps reel (CA jour/mois, caisse, depenses, profit estime), barre d alertes dynamique, factures recentes, acces rapides.
- **Header entierement dynamique** : selecteur entreprise/branche reel, menu Creer en francais (9 actions rapides M-Faida), notifications temps reel (ruptures, factures caisse, conges, avances a decaisser), bouton Caisse.
- **Sidebar remplacee** : ancien menu template generique supprime ; menu M-Faida operationnel (8 sections, permissions par module, etats actifs).
- **Context processor global** (core/context_processors.py) : injection automatique de entreprise_courante, branche_courante, branches_disponibles et notifs_header dans tous les templates.
- **Transferts de stock** inter-depots/PDV avec contraintes metier et tracabilite complete.
- **Permissions etendues** (migrations 0008-0019) : RH, proforma, retours, bons de commande, depenses, stock avance, depot/PDV, transferts, caisse, rapports.

---

## Licence

Projet privé — tous droits réservés.
