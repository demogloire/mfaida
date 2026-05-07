from decimal import Decimal as _D

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
        ('EN_CAISSE', 'En attente caisse'),
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


class PaiementFacture(models.Model):
    """Encaissement (total ou partiel) d'une facture à crédit ou partiellement payée."""

    MODES_PAIEMENT = [
        ('CASH',         'Espèces'),
        ('MOBILE_MONEY', 'Mobile Money'),
        ('CARTE',        'Carte bancaire'),
        ('CHEQUE',       'Chèque'),
        ('VIREMENT',     'Virement bancaire'),
    ]

    numero          = models.CharField(max_length=50, unique=True, editable=False, db_index=True)
    facture         = models.ForeignKey(Facture, on_delete=models.PROTECT, related_name='paiements')
    montant         = models.DecimalField(max_digits=15, decimal_places=2)
    mode_paiement   = models.CharField(max_length=20, choices=MODES_PAIEMENT, default='CASH')
    date_paiement   = models.DateTimeField(auto_now_add=True)
    effectue_par    = models.ForeignKey(Profil, on_delete=models.PROTECT, related_name='paiements_factures')
    notes           = models.TextField(blank=True, default='')

    class Meta:
        verbose_name        = 'Paiement de facture'
        verbose_name_plural = 'Paiements de factures'
        ordering            = ['-date_paiement']

    def save(self, *args, **kwargs):
        if not self.numero:
            prefix = 'PAY-'
            for _ in range(30):
                try:
                    with transaction.atomic():
                        max_num = 0
                        for row in PaiementFacture.objects.select_for_update().filter(
                            numero__startswith=prefix
                        ).only('numero'):
                            try:
                                max_num = max(max_num, int(row.numero[len(prefix):]))
                            except ValueError:
                                pass
                        self.numero = f'{prefix}{max_num + 1:06d}'
                        return super().save(*args, **kwargs)
                except IntegrityError:
                    self.numero = ''
            raise IntegrityError('Impossible de générer un numéro de paiement unique.')
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.numero} — {self.facture.numero_facture} ({self.montant})"


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

    @property
    def sous_total_ht(self):
        """Montant HT de la ligne (qté × PU − remise), hors TVA."""
        from decimal import Decimal as D

        return D(str(self.quantite)) * D(str(self.prix_unitaire_ht)) - D(str(self.remise or '0'))

    def save(self, *args, **kwargs):
        from decimal import Decimal as D

        total_ligne_ht = (
            D(str(self.quantite)) * D(str(self.prix_unitaire_ht)) - D(str(self.remise or '0'))
        )
        self.sous_total_ttc = total_ligne_ht + D(str(self.tva_montant or '0'))
        super().save(*args, **kwargs)

class FactureProforma(models.Model):
    STATUTS_PROFORMA = [
        ('BROUILLON', 'Brouillon'),
        ('EN_ATTENTE', 'En attente d\'approbation'),
        ('ACCEPTEE', 'Acceptée / Convertie'),
        ('EXPIREE', 'Expirée'),
        ('ANNULEE', 'Annulée'),
    ]

    # Identification
    numero_proforma = models.CharField(max_length=50, unique=True, editable=False)
    branche = models.ForeignKey(Branche, on_delete=models.CASCADE)
    vendeur = models.ForeignKey(Profil, on_delete=models.PROTECT, related_name='proformas_crees')
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

    # Workflow d'approbation
    soumis_le = models.DateTimeField(null=True, blank=True)
    approuve_par = models.ForeignKey(
        Profil, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='proformas_approuvees',
    )
    date_approbation = models.DateTimeField(null=True, blank=True)
    commentaire_manager = models.TextField(blank=True, default='')

    # Lien vers la facture finale (si convertie)
    facture_definitive = models.OneToOneField(Facture, on_delete=models.SET_NULL, null=True, blank=True)

    def save(self, *args, **kwargs):
        if kwargs.get('update_fields') is None and not self.numero_proforma:
            prefix = 'PRO-'
            for _ in range(30):
                try:
                    with transaction.atomic():
                        max_num = 0
                        plen = len(prefix)
                        qs = (
                            FactureProforma.objects.select_for_update()
                            .filter(numero_proforma__startswith=prefix)
                            .only('numero_proforma')
                        )
                        for row in qs:
                            tail = row.numero_proforma[plen:]
                            try:
                                max_num = max(max_num, int(tail))
                            except ValueError:
                                continue
                        self.numero_proforma = f'{prefix}{max_num + 1:06d}'
                        return super().save(*args, **kwargs)
                except IntegrityError:
                    self.numero_proforma = ''
                    continue
            raise IntegrityError('Impossible de générer un numéro de proforma unique.')
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
        return tot_ttc

    def __str__(self):
        return f"PROFORMA {self.numero_proforma} - {self.client.nom}"


# ─────────────────────────────────────────────
# Ventes Retournées
# ─────────────────────────────────────────────

class RetourVente(models.Model):
    STATUTS = [
        ('BROUILLON',  'Brouillon'),
        ('EN_ATTENTE', 'En attente d\'approbation'),
        ('APPROUVE',   'Approuvé — stock réintégré'),
        ('REJETE',     'Rejeté'),
        ('ANNULE',     'Annulé'),
    ]

    numero_retour    = models.CharField(max_length=50, unique=True, editable=False)
    facture_origine  = models.ForeignKey(
        Facture, on_delete=models.PROTECT, related_name='retours'
    )
    point_vente      = models.ForeignKey(PointVente, on_delete=models.PROTECT)
    vendeur          = models.ForeignKey(
        Profil, on_delete=models.PROTECT, related_name='retours_saisis'
    )
    client           = models.ForeignKey(Client, on_delete=models.PROTECT)
    devise           = models.ForeignKey(Devise, on_delete=models.PROTECT)
    taux_echange     = models.DecimalField(max_digits=15, decimal_places=4, default=1)
    motif               = models.TextField(blank=True, default='')
    statut              = models.CharField(max_length=20, choices=STATUTS, default='BROUILLON')
    date_retour         = models.DateTimeField(auto_now_add=True)
    soumis_le           = models.DateTimeField(null=True, blank=True)
    approuve_par        = models.ForeignKey(
        Profil, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='retours_approuves',
    )
    date_approbation    = models.DateTimeField(null=True, blank=True)
    commentaire_manager = models.TextField(blank=True, default='')
    total_ht         = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_tva        = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_ttc        = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    def save(self, *args, **kwargs):
        if kwargs.get('update_fields') is None and not self.numero_retour:
            prefix = 'RETOUR-'
            for _ in range(30):
                try:
                    with transaction.atomic():
                        max_num = 0
                        plen = len(prefix)
                        qs = (
                            RetourVente.objects.select_for_update()
                            .filter(numero_retour__startswith=prefix)
                            .only('numero_retour')
                        )
                        for row in qs:
                            tail = row.numero_retour[plen:]
                            try:
                                max_num = max(max_num, int(tail))
                            except ValueError:
                                continue
                        self.numero_retour = f'{prefix}{max_num + 1:06d}'
                        return super().save(*args, **kwargs)
                except IntegrityError:
                    self.numero_retour = ''
                    continue
            raise IntegrityError('Impossible de générer un numéro de retour unique.')
        return super().save(*args, **kwargs)

    def recalcul_totaux(self):
        tot_ht = _D('0')
        tot_tva = _D('0')
        tot_ttc = _D('0')
        for lig in self.lignes.all():
            ht = _D(str(lig.quantite_retournee)) * _D(str(lig.prix_unitaire_ht))
            tot_ht += ht
            tot_tva += _D(str(lig.tva_montant or '0'))
            tot_ttc += ht + _D(str(lig.tva_montant or '0'))
        self.total_ht  = tot_ht
        self.total_tva = tot_tva
        self.total_ttc = tot_ttc
        return tot_ttc

    def __str__(self):
        return f"RETOUR {self.numero_retour} — {self.client.nom}"


class LigneRetour(models.Model):
    retour               = models.ForeignKey(RetourVente, on_delete=models.CASCADE, related_name='lignes')
    ligne_facture_origine = models.ForeignKey(
        LigneFacture, on_delete=models.PROTECT, related_name='lignes_retour'
    )
    mouvement_stock      = models.ForeignKey(
        MouvementStock, on_delete=models.PROTECT, related_name='lignes_retour'
    )
    produit              = models.ForeignKey(Produit, on_delete=models.PROTECT)
    quantite_retournee   = models.DecimalField(max_digits=15, decimal_places=2)
    prix_unitaire_ht     = models.DecimalField(max_digits=15, decimal_places=2)
    tva_montant          = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    sous_total_ttc       = models.DecimalField(max_digits=15, decimal_places=2, editable=False)

    @property
    def sous_total_ht(self):
        return _D(str(self.quantite_retournee)) * _D(str(self.prix_unitaire_ht))

    def save(self, *args, **kwargs):
        ht = _D(str(self.quantite_retournee)) * _D(str(self.prix_unitaire_ht))
        self.sous_total_ttc = ht + _D(str(self.tva_montant or '0'))
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Retour {self.retour.numero_retour} — {self.produit.nom} × {self.quantite_retournee}"


class LigneProforma(models.Model):
    proforma = models.ForeignKey(FactureProforma, on_delete=models.CASCADE, related_name='lignes')
    produit = models.ForeignKey(Produit, on_delete=models.PROTECT)

    quantite = models.DecimalField(max_digits=15, decimal_places=2)
    prix_unitaire_ht = models.DecimalField(max_digits=15, decimal_places=2)
    tva_montant = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    remise = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)

    sous_total_ttc = models.DecimalField(max_digits=15, decimal_places=2, editable=False)

    @property
    def sous_total_ht(self):
        from decimal import Decimal as D
        return D(str(self.quantite)) * D(str(self.prix_unitaire_ht)) - D(str(self.remise or '0'))

    def save(self, *args, **kwargs):
        from decimal import Decimal as D
        total_ligne_ht = D(str(self.quantite)) * D(str(self.prix_unitaire_ht)) - D(str(self.remise or '0'))
        self.sous_total_ttc = total_ligne_ht + D(str(self.tva_montant or '0'))
        super().save(*args, **kwargs)



