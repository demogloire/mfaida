from django.db import models
from entreprise.models import Produit, PointVente, Depot, Location
from achat.models import LigneOrdreAchat
from utilisateur.models import Profil


class MouvementOrigine(models.TextChoices):
    BR = 'BR', 'Bon de réception'
    AJUSTEMENT = 'AJUSTEMENT', 'Ajustement manuel'
    INVENTAIRE = 'INVENTAIRE', 'Inventaire (écart physique)'
    VENTE = 'VENTE', 'Sortie vente (facture)'


class Stock(models.Model):
    produit = models.ForeignKey(Produit, on_delete=models.CASCADE, related_name='niveaux_stock')
    depot = models.ForeignKey(Depot, on_delete=models.CASCADE, related_name='stockdepot')
    pointdevente = models.ForeignKey(PointVente, on_delete=models.CASCADE, related_name='stockpoint', null=True, blank=True)
    quantite_reelle = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    derniere_mise_a_jour = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.produit.nom} - {self.depot.nom} ({self.quantite_reelle})"


class MouvementStock(models.Model):
    # Précision de l'emplacement (Rayon/Étagère)
    produit = models.ForeignKey(Produit, on_delete=models.CASCADE)
    depot = models.ForeignKey(Depot, on_delete=models.CASCADE, null=True, blank=True)
    location = models.ForeignKey(Location, on_delete=models.CASCADE, null=True, blank=True)
    pointvente = models.ForeignKey(PointVente, on_delete=models.CASCADE, null=True, blank=True)


    quantite_recu = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    quantite_affectee = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    quantite_ecarter = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0.00,
        verbose_name='Quantité à l’écart',
        help_text='Mis à l’écart à la réception ou par opération : augmente cette valeur → disponible active diminue '
        '(distinct de l’écart de campagne d’inventaire sur une ligne inventaire).',
    )
    quantite_active = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    # Référence au dernier achat pour traçabilité du coût
    prix_unitaire = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)

    dateproduction = models.DateField(null=True, blank=True)
    dateexpiration = models.DateField(null=True, blank=True)
    lot_batch = models.CharField(max_length=20, blank=True, default="")
    unite = models.CharField(max_length=20, blank=True, default="")
    location_code = models.CharField(max_length=20, blank=True, default="")

    marque = models.CharField(max_length=100, blank=True, default="", verbose_name="Marque")
    conditionnement = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="Taille du conditionnement / emballage",
        help_text="Ex. carton 12 pcs, bidon 5 L…",
    )

    ligneordreachat = models.ForeignKey(LigneOrdreAchat, on_delete=models.SET_NULL, null=True, blank=True)
    origine = models.CharField(
        max_length=20,
        choices=MouvementOrigine.choices,
        default=MouvementOrigine.BR,
        verbose_name='Origine du mouvement',
    )
    motif = models.TextField(blank=True, default='', verbose_name='Motif / commentaire')
    reference_piece = models.CharField(max_length=80, blank=True, default='', verbose_name='Référence pièce')
    inventaire = models.ForeignKey(
        'Inventaire',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='mouvements_correction',
        verbose_name='Inventaire lié',
    )
    sens_adjustement = models.IntegerField(
        null=True,
        blank=True,
        verbose_name='Sens ajustement',
        choices=[(1, 'Entrée'), (-1, 'Sortie interne')],
        help_text="Rempli uniquement pour les lignes d'ajustement manuel (+ entrée stock, − sortie).",
    )
    effectue_par = models.ForeignKey(Profil, on_delete=models.SET_NULL, null=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        place = self.depot.nom if self.depot_id else (self.pointvente.nom if self.pointvente_id else "N/A")
        return f"Mouvement {self.produit.nom} @ {place}"

class StockMiseAEcart(models.Model):
    """
    Quantité retirée de la disponibilité sur une ligne de lot : active diminue et `MouvementStock.quantite_ecarter` augmente.
    Trace complémentaire pour motif / historique. Stock physique agrégé (Stock.quantité_reelle) inchangé.
    L’« écart » de campagne d’inventaire reste sur `LigneInventaire.ecart`.
    """

    produit = models.ForeignKey(
        Produit,
        on_delete=models.CASCADE,
        related_name='stock_mises_a_ecart',
    )
    mouvement_stock = models.ForeignKey(
        'MouvementStock',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='mises_a_ecart',
    )
    depot = models.ForeignKey(Depot, on_delete=models.CASCADE)
    pointdevente = models.ForeignKey(PointVente, on_delete=models.CASCADE, null=True, blank=True)
    quantite = models.DecimalField(max_digits=15, decimal_places=2)
    motif = models.TextField(verbose_name='Motif / raison')
    actif = models.BooleanField(default=True)
    cree_par = models.ForeignKey(Profil, on_delete=models.SET_NULL, null=True, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Mise à l'écart stock"
        verbose_name_plural = "Mises à l'écart stock"
        indexes = [
            models.Index(fields=['produit', 'depot', 'pointdevente', 'actif']),
        ]

    def __str__(self):
        lieu = (
            self.pointdevente.nom
            if self.pointdevente_id
            else f"Dépôt {self.depot.nom}"
        )
        return f"{self.produit} @ {lieu}: {self.quantite}"

class Inventaire(models.Model):
    lot = models.CharField(max_length=20, blank=True, default='')
    depot = models.ForeignKey(Depot, on_delete=models.CASCADE,null=True,blank=True)
    pointdevente = models.ForeignKey(PointVente, on_delete=models.CASCADE,null=True,blank=True)
    date_inventaire = models.DateField()
    cloture = models.BooleanField(default=False) # Si True, on ne peut plus modifier
    valide_par = models.ForeignKey(Profil, on_delete=models.SET_NULL, null=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not (self.lot or '').strip():
            ref = f'INV-{self.pk:06d}'
            type(self).objects.filter(pk=self.pk).update(lot=ref)
            self.lot = ref

    def __str__(self):
        return f"{self.lot} ({self.date_inventaire})"


class LigneInventaire(models.Model):
    inventaire = models.ForeignKey(Inventaire, on_delete=models.CASCADE, related_name='lignes')
    produit = models.ForeignKey(Produit, on_delete=models.CASCADE)
    quantite_theorique = models.DecimalField(max_digits=15, decimal_places=2)  # Ce que l'ERP dit
    quantite_physique = models.DecimalField(max_digits=15, decimal_places=2)  # Ce que l'agent compte
    # Écart réservé à la campagne d’inventaire (physique − théorique), pas aux mises à l’écart opérationnelles.
    ecart = models.DecimalField(max_digits=15, decimal_places=2, editable=False)

    def save(self, *args, **kwargs):
        self.ecart = self.quantite_physique - self.quantite_theorique
        super().save(*args, **kwargs)


class BonAjustementStock(models.Model):
    """Regroupe plusieurs ajustements manuels pour une même pièce / traçabilité."""

    numero = models.CharField(
        max_length=80,
        blank=True,
        default='',
        db_index=True,
        verbose_name="Numéro d'ajustement",
    )
    entreprise = models.ForeignKey(
        'entreprise.Entreprise',
        on_delete=models.CASCADE,
        related_name='bons_ajustement_stock',
    )
    depot = models.ForeignKey(Depot, on_delete=models.CASCADE, null=True, blank=True)
    pointvente = models.ForeignKey(PointVente, on_delete=models.CASCADE, null=True, blank=True)
    cree_par = models.ForeignKey(
        Profil,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bons_ajustement_crees',
    )
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Bon d'ajustement stock"
        verbose_name_plural = "Bons d'ajustement stock"
        ordering = ['-date_creation']

    def save(self, *args, **kwargs):
        first = self._state.adding
        super().save(*args, **kwargs)
        if first and not (self.numero or '').strip():
            new_num = f'ADJ-{self.pk:06d}'
            type(self).objects.filter(pk=self.pk).update(numero=new_num)
            self.numero = new_num

    def __str__(self):
        return self.numero or f'Bon #{self.pk}'


class LigneBonAjustement(models.Model):
    """Une ligne physique d'ajustement rattachée à un bon."""

    bon = models.ForeignKey(BonAjustementStock, on_delete=models.CASCADE, related_name='lignes')
    mouvement_stock = models.ForeignKey(
        MouvementStock,
        on_delete=models.PROTECT,
        related_name='ajustements_bon_trace',
    )
    sens = models.SmallIntegerField(choices=[(1, 'Entrée'), (-1, 'Sortie')])
    quantite = models.DecimalField(max_digits=15, decimal_places=2)
    prix_unitaire_ht = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    motif = models.TextField(blank=True, default='')
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Ligne de bon d'ajustement"
        verbose_name_plural = "Lignes de bon d'ajustement"
        ordering = ['date_creation']

    def __str__(self):
        pn = getattr(self.mouvement_stock, 'produit', None)
        lib = pn.nom if pn else '?'
        return f"{self.bon} — {lib} (ligne trace #{self.pk})"