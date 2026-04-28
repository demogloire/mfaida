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

### Stock & facturation
- Mouvements de stock, lignes d’achat liées aux apps `achat` / `tiers`
- Facturation : références client alignées sur `tiers.Client`

### Utilisateurs
- Authentification et gestion des sessions
- Rôles et permissions personnalisées
- Accès granulaires par dépôt et point de vente
- Profil : photo, **signature image** (PDF bons de commande), etc.
- Journal des connexions et actions (audit)

---

## Stack technique

| Composant | Technologie |
|-----------|-------------|
| Backend | Python 3.x / **Django 4.0** |
| Frontend | Bootstrap 5, HTMX, Tabler Icons |
| Base de données | MySQL |
| Templates | Django Templates + widget_tweaks |
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

## Structure du projet

```
m-faida/
├── core/               # Configuration Django (settings, urls)
├── entreprise/         # Entreprises, branches, dépôts, PdV, devises, produits…
├── tiers/              # Clients et fournisseurs
├── achat/              # Bons de commande, réceptions, exports Excel/PDF
├── utilisateur/        # Utilisateurs, rôles, permissions
├── produit/            # Vues / templates catalogue (réexport entreprise.Produit)
├── stock/              # Mouvements de stock, inventaire
├── facturation/        # Factures, proformas
├── finance/            # Comptabilité
├── rh/                 # Ressources humaines
├── templates/          # Templates HTML globaux et par module
├── static/             # Fichiers statiques (CSS, JS)
└── media/              # Fichiers téléversés (logos, signatures, etc.)
```

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

---

## Licence

Projet privé — tous droits réservés.
