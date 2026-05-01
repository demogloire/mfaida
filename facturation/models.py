from django.db import models, transaction, IntegrityError
from stock.models import MouvementStock
from entreprise.models import Produit, PointVente, Devise, Branche
from tiers.models import Client
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

    def save(self, *args, **kwargs):
        if kwargs.get('update_fields') is None and not self.numero_facture:
            br = self.point_vente.branche
            prefix = (br.init_facture or '').strip() or 'FACT-'
            for _ in range(30):
                try:
                    with transaction.atomic():
                        max_num = 0
                        plen = len(prefix)
                        qs = (
                            Facture.objects.select_for_update()
                            .filter(numero_facture__startswith=prefix)
                            .only('numero_facture')
                        )
                        for row in qs:
                            tail = row.numero_facture[plen:]
                            try:
                                max_num = max(max_num, int(tail))
                            except ValueError:
                                continue
                        self.numero_facture = f'{prefix}{max_num + 1:06d}'
                        return super().save(*args, **kwargs)
                except IntegrityError:
                    self.numero_facture = ''
                    continue
            raise IntegrityError('Impossible de générer un numéro de facture unique.')
        return super().save(*args, **kwargs)

    def recalcul_totaux(self):
        from decimal import Decimal as D
        tot_ht = D('0')
        tot_tva = D('0')
        tot_ttc = D('0')
        for lig in self.lignes.all():
            ligne_ht = D(str(lig.quantite)) * D(str(lig.prix_unitaire_ht)) - D(str(lig.remise or '0'))
            tot_ht += ligne_ht
            tot_tva += D(str(lig.tva_montant or '0'))
            tot_ttc += ligne_ht + D(str(lig.tva_montant or '0'))
        self.total_ht = tot_ht
        self.total_tva = tot_tva
        self.total_ttc = tot_ttc
        self.reste_a_payer = tot_ttc - (self.montant_paye or D('0'))
        return self.total_ttc

    def __str__(self):
        return f"FACT {self.numero_facture} - {self.client.nom}"

class LigneFacture(models.Model):
    facture = models.ForeignKey(Facture, on_delete=models.CASCADE, related_name='lignes')
    mouvement_stock = models.ForeignKey(MouvementStock, on_delete=models.PROTECT, related_name='lignes_factures')
    produit = models.ForeignKey(
        Produit, on_delete=models.PROTECT, related_name='facture_ligne_produit'
    ) 

    
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



