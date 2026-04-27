from django.db import models
from django.conf import settings
from stock.models import MouvementStock
from entreprise.models import Produit, PointVente, Client, Devise, Branche, Entreprise
from utilisateur.models import Profil


class CompteComptable(models.Model):
    CLASSES_OHADA = [
        ('1', 'Comptes de capitaux'),
        ('2', 'Comptes d\'immobilisations'),
        ('3', 'Comptes de stocks'),
        ('4', 'Comptes de tiers'),
        ('5', 'Comptes de trésorerie'),
        ('6', 'Comptes de charges'),
        ('7', 'Comptes de produits'),
        ('8', 'Comptes spéciaux'),
    ]

    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE)
    numero = models.CharField(max_length=10, unique=True) # ex: 411100 (Client)
    libelle = models.CharField(max_length=255)
    classe = models.CharField(max_length=1, choices=CLASSES_OHADA)
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True) # Pour hiérarchie
    est_actif = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.numero} - {self.libelle}"


class Journal(models.Model):
    TYPES_JOURNAL = [
        ('VENTE', 'Journal des Ventes'),
        ('ACHAT', 'Journal des Achats'),
        ('CAISSE', 'Journal de Caisse'),
        ('BANQUE', 'Journal de Banque'),
        ('OD', 'Opérations Diverses'),
    ]
    code = models.CharField(max_length=10, unique=True) # ex: JVT (Ventes)
    nom = models.CharField(max_length=100)
    type_journal = models.CharField(max_length=10, choices=TYPES_JOURNAL)

class EcritureComptable(models.Model):
    journal = models.ForeignKey(Journal, on_delete=models.PROTECT)
    reference_piece = models.CharField(max_length=50) # ex: N° Facture
    date_comptable = models.DateField()
    libelle = models.CharField(max_length=255)
    date_creation = models.DateTimeField(auto_now_add=True)
    auteur = models.ForeignKey(Profil, on_delete=models.SET_NULL, null=True)

class LigneEcriture(models.Model):
    ecriture = models.ForeignKey(EcritureComptable, on_delete=models.CASCADE, related_name='lignes')
    compte = models.ForeignKey(CompteComptable, on_delete=models.PROTECT)
    debit = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    credit = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    
    def __str__(self):
        return f"{self.compte.numero} | D:{self.debit} C:{self.credit}"

