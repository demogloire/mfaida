from django.db import models
from django.conf import settings
from stock.models import MouvementStock
from entreprise.models import Produit, PointVente, Client, Devise, Branche
from utilisateur.models import Profil


class Facture(models.Model):
    MODES_PAIEMENT = [
        ('CASH', 'Espèces'),
        ('MOBILE_MONEY', 'Mobile Money'),
        ('CARTE', 'Carte Bancaire'),
        ('CREDIT', 'Crédit / À terme'),
    ]
    
    STATUTS_FACTURE = [
        ('BROUILLON', 'Brouillon'),
        ('VALIDEE', 'Validée'),
        ('ANNULEE', 'Annulée'),
    ]

    # Liens Organisationnels
    numero_facture = models.CharField(max_length=50, unique=True, editable=False)
    point_vente = models.ForeignKey(PointVente, on_delete=models.PROTECT)
    vendeur = models.ForeignKey(Profil, on_delete=models.PROTECT)
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name='factures')
    
    # Finance
    devise = models.ForeignKey(Devise, on_delete=models.PROTECT)
    taux_echange_appliqué = models.DecimalField(max_digits=15, decimal_places=4) # Pour historique
    
    # Totaux
    total_ht = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    total_tva = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    total_ttc = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    montant_paye = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    reste_a_payer = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    
    # Infos Paiement et Statut
    mode_paiement = models.CharField(max_length=20, choices=MODES_PAIEMENT, default='CASH')
    statut = models.CharField(max_length=20, choices=STATUTS_FACTURE, default='BROUILLON')
    date_facture = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"FACT {self.numero_facture} - {self.client.nom}"

class LigneFacture(models.Model):
    facture = models.ForeignKey(Facture, on_delete=models.CASCADE, related_name='lignes')
    stock=models.ForeignKey(MouvementStock, on_delete=models.CASCADE, related_name='stocks') 
    produit=models.ForeignKey(Produit, on_delete=models.CASCADE, related_name='produits') 

    
    quantite = models.DecimalField(max_digits=15, decimal_places=2)
    prix_unitaire_ht = models.DecimalField(max_digits=15, decimal_places=2) # Prix figé à la vente
    tva_montant = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    remise = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    
    sous_total_ttc = models.DecimalField(max_digits=15, decimal_places=2, editable=False)

    def save(self, *args, **kwargs):
        # Calcul auto du sous-total ligne
        total_ligne_ht = (self.quantite * self.prix_unitaire_ht) - self.remise
        self.sous_total_ttc = total_ligne_ht + self.tva_montant
        super().save(*args, **kwargs)

class FactureProforma(models.Model):
    STATUTS_PROFORMA = [
        ('EN_ATTENTE', 'En attente'),
        ('ACCEPTEE', 'Acceptée / Convertie'),
        ('EXPIREE', 'Expirée'),
        ('ANNULEE', 'Annulée'),
    ]

    # Identification
    numero_proforma = models.CharField(max_length=50, unique=True, editable=False)
    branche = models.ForeignKey(Branche, on_delete=models.CASCADE)
    vendeur = models.ForeignKey(Profil, on_delete=models.PROTECT)
    client = models.ForeignKey(Client, on_delete=models.PROTECT)
    
    # Dates
    date_emission = models.DateTimeField(auto_now_add=True)
    date_validite = models.DateField(help_text="Date limite de validité de l'offre")
    
    # Finance
    devise = models.ForeignKey(Devise, on_delete=models.PROTECT)
    total_ht = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    total_tva = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    total_ttc = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    
    statut = models.CharField(max_length=20, choices=STATUTS_PROFORMA, default='EN_ATTENTE')
    
    # Lien vers la facture finale (si convertie)
    facture_definitive = models.OneToOneField(Facture, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"PROFORMA {self.numero_proforma} - {self.client.nom}"


class LigneProforma(models.Model):
    proforma = models.ForeignKey(FactureProforma, on_delete=models.CASCADE, related_name='lignes')
    produit = models.ForeignKey(Produit, on_delete=models.PROTECT)
    
    quantite = models.DecimalField(max_digits=15, decimal_places=2)
    prix_unitaire_ht = models.DecimalField(max_digits=15, decimal_places=2)
    tva_montant = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    remise = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    
    sous_total_ttc = models.DecimalField(max_digits=15, decimal_places=2, editable=False)

    def save(self, *args, **kwargs):
        total_ligne_ht = (self.quantite * self.prix_unitaire_ht) - self.remise
        self.sous_total_ttc = total_ligne_ht + self.tva_montant
        super().save(*args, **kwargs)



