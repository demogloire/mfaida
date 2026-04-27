# M-Faida — Système de Gestion Commerciale

Application web de gestion commerciale complète développée avec **Django**, **HTMX** et **Bootstrap 5**.

---

## Fonctionnalités

### Entreprise
- Gestion des entreprises (multi-entreprises)
- Branches, dépôts, points de vente
- Devises et taux de change
- Fournisseurs
- Étagères / emplacements de stockage

### Utilisateurs
- Authentification et gestion des sessions
- Rôles et permissions personnalisées
- Accès granulaires par dépôt et point de vente
- Profil, sécurité, signature numérique
- Journal des connexions et actions (audit)

### Catalogue Produits
- Catégories et sous-catégories
- Produits avec prix, TVA, marge calculée automatiquement
- Méthodes de gestion de stock (FIFO, FEFO, LIFO)
- Import en masse via fichier Excel (.xlsx)
- Upload d'images produits

---

## Stack technique

| Composant | Technologie |
|-----------|-------------|
| Backend | Python 3.x / Django 5.x |
| Frontend | Bootstrap 5, HTMX, Tabler Icons |
| Base de données | MySQL |
| Templates | Django Templates + widget_tweaks |
| Import Excel | openpyxl |
| Auth | Django Auth (AbstractUser étendu) |

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
# Copier et adapter le fichier de configuration
cp core/settings.py.example core/settings.py
# Modifier DATABASES avec vos identifiants MySQL

# 5. Appliquer les migrations
python manage.py migrate

# 6. Créer un super-utilisateur
python manage.py createsuperuser

# 7. Lancer le serveur
python manage.py runserver
```

---

## Structure du projet

```
m-faida/
├── core/               # Configuration Django (settings, urls)
├── entreprise/         # App : entreprises, branches, dépôts, PdV
├── utilisateur/        # App : utilisateurs, rôles, permissions
├── produit/            # App : catalogue produits, import Excel
├── stock/              # App : mouvements de stock, inventaire
├── facturation/        # App : factures, proformas
├── finance/            # App : comptabilité
├── rh/                 # App : ressources humaines
├── templates/          # Templates HTML globaux
├── static/             # Fichiers statiques (CSS, JS)
└── utilities/          # Utilitaires partagés
```

---

## Import Excel des produits

Un fichier modèle Excel est disponible depuis l'interface :
**Catalogue → Import Excel → Télécharger le modèle**

Colonnes supportées : `nom`, `categorie`, `sous_categorie`, `code_barre`, `description`, `prix_achat_ht`, `prix_vente_ht`, `tva_taux`, `unite_mesure`, `stock_alerte`, `methode_gestion`, `vie`

---

## Licence

Projet privé — tous droits réservés.
