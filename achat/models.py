from django.db import models, transaction, IntegrityError
from django.conf import settings


class OrdreAchat(models.Model):
    STATUT_CHOICES = [
        ('BROUILLON', 'Brouillon'),
        ('ENVOYE', 'Envoyé au Fournisseur'),
        ('RECU_PARTIEL', 'Reçu Partiellement'),
        ('RECU_TOTAL', 'Reçu Totalement'),
        ('ANNULE', 'Annulé'),
    ]

    numero_commande = models.CharField(max_length=50, unique=True, editable=False)
    entreprise = models.ForeignKey(
        'entreprise.Entreprise', on_delete=models.CASCADE, related_name='ordres_achat'
    )
    fournisseur = models.ForeignKey(
        'tiers.Fournisseur', on_delete=models.PROTECT, related_name='ordres_achat'
    )

    depot_destination = models.ForeignKey(
        'entreprise.Depot', on_delete=models.SET_NULL, null=True, blank=True
    )
    pointdevente_destination = models.ForeignKey(
        'entreprise.PointVente', on_delete=models.SET_NULL, null=True, blank=True
    )

    date_commande = models.DateTimeField(auto_now_add=True)
    date_livraison_prevue = models.DateField(null=True, blank=True)
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='BROUILLON')

    devise = models.ForeignKey(
        'entreprise.Devise', on_delete=models.SET_NULL, null=True
    )
    total_ht = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    total_tva = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    total_ttc = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)

    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='ordres_achat'
    )
    notes = models.TextField(blank=True)

    class Meta:
        db_table = 'entreprise_ordreachat'
        verbose_name = "Ordre d'achat"
        verbose_name_plural = "Ordres d'achat"
        ordering = ['-date_commande']

    def __str__(self):
        return f"BC {self.numero_commande} - {self.fournisseur.nom_societe}"

    def _resolve_prefix_bd_commande(self):
        """Préfixe depuis Branche.init_bdcommande (dépôt concerné, sinon branche siège / première de l'entreprise)."""
        from entreprise.models import Branche

        branche = None
        if self.depot_destination_id:
            dep = self.depot_destination
            branche = dep.branche

        ent_id = self.entreprise_id
        if branche is None and ent_id:
            branche = (
                Branche.objects.filter(entreprise_id=ent_id, est_siege_social=True)
                .order_by('pk')
                .first()
            )
            if branche is None:
                branche = Branche.objects.filter(entreprise_id=ent_id).order_by('pk').first()

        raw = (branche.init_bdcommande if branche else None) or ''
        p = (raw or '').strip()
        return p if p else 'BC-'

    def save(self, *args, **kwargs):
        if not self.numero_commande:
            prefix = self._resolve_prefix_bd_commande()
            for _ in range(30):
                try:
                    with transaction.atomic():
                        max_num = 0
                        plen = len(prefix)
                        qs = (
                            OrdreAchat.objects.select_for_update()
                            .filter(numero_commande__startswith=prefix)
                            .only('numero_commande')
                        )
                        for row in qs:
                            tail = row.numero_commande[plen:]
                            try:
                                max_num = max(max_num, int(tail))
                            except ValueError:
                                continue
                        next_num = max_num + 1
                        self.numero_commande = f'{prefix}{next_num:06d}'
                        return super().save(*args, **kwargs)
                except IntegrityError:
                    self.numero_commande = ''
                    continue
            raise IntegrityError("Impossible de générer un numéro de commande unique.")
        return super().save(*args, **kwargs)

    def recalculer_totaux(self):
        lignes = self.lignes.all()
        self.total_ht = sum(l.sous_total_ht for l in lignes)
        self.total_tva = sum(l.sous_total_ht * (l.produit.tva_taux / 100) for l in lignes)
        self.total_ttc = self.total_ht + self.total_tva
        self.save(update_fields=['total_ht', 'total_tva', 'total_ttc'])


class LigneOrdreAchat(models.Model):
    ordre_achat = models.ForeignKey(OrdreAchat, on_delete=models.CASCADE, related_name='lignes')
    produit = models.ForeignKey('entreprise.Produit', on_delete=models.CASCADE)

    quantite_commandee = models.DecimalField(max_digits=15, decimal_places=2)
    quantite_recue = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)

    dateproduction = models.DateField(null=True, blank=True)
    dateexpiration = models.DateField(null=True, blank=True)
    lot_batch = models.CharField(max_length=20, blank=True, default="")
    unite = models.CharField(max_length=20, blank=True, default="")
    location = models.ForeignKey(
        'entreprise.Location', on_delete=models.SET_NULL, null=True, blank=True
    )

    reception = models.BooleanField(default=False)
    prix_unitaire_ht = models.DecimalField(max_digits=15, decimal_places=2)
    sous_total_ht = models.DecimalField(max_digits=15, decimal_places=2, editable=False, default=0)

    class Meta:
        db_table = 'entreprise_ligneordreachat'
        verbose_name = "Ligne d'ordre d'achat"
        verbose_name_plural = "Lignes d'ordre d'achat"

    def __str__(self):
        return f"{self.produit.nom} × {self.quantite_commandee}"

    def save(self, *args, **kwargs):
        self.sous_total_ht = self.quantite_commandee * self.prix_unitaire_ht
        super().save(*args, **kwargs)

    @classmethod
    def trouver_ligne_identique(cls, ordre_achat, cleaned_data):
        """
        Ligne existante avec le même produit et les mêmes conditions commerciales /
        logistiques (hors quantité). Utilisé pour fusionner les ajouts au lieu de dupliquer.
        """
        produit = cleaned_data['produit']
        unite = (cleaned_data.get('unite') or '').strip()
        lot_batch = (cleaned_data.get('lot_batch') or '').strip()
        loc = cleaned_data.get('location')

        qs = cls.objects.filter(
            ordre_achat=ordre_achat,
            produit=produit,
            prix_unitaire_ht=cleaned_data['prix_unitaire_ht'],
            unite=unite,
            lot_batch=lot_batch,
            dateproduction=cleaned_data.get('dateproduction'),
            dateexpiration=cleaned_data.get('dateexpiration'),
        )
        if loc:
            qs = qs.filter(location=loc)
        else:
            qs = qs.filter(location__isnull=True)
        return qs.first()

    @classmethod
    def creer_ou_fusionner(cls, ordre_achat, cleaned_data):
        """Crée une ligne ou ajoute la quantité à une ligne identique existante."""
        existing = cls.trouver_ligne_identique(ordre_achat, cleaned_data)
        if existing:
            existing.quantite_commandee += cleaned_data['quantite_commandee']
            existing.save()
            return existing, 'merged'
        ligne = cls(
            ordre_achat=ordre_achat,
            produit=cleaned_data['produit'],
            quantite_commandee=cleaned_data['quantite_commandee'],
            prix_unitaire_ht=cleaned_data['prix_unitaire_ht'],
            unite=(cleaned_data.get('unite') or '').strip(),
            lot_batch=(cleaned_data.get('lot_batch') or '').strip(),
            dateproduction=cleaned_data.get('dateproduction'),
            dateexpiration=cleaned_data.get('dateexpiration'),
            location=cleaned_data.get('location'),
        )
        ligne.save()
        return ligne, 'created'


class BonReception(models.Model):
    STATUT_CHOICES = [
        ('EN_COURS', 'En cours'),
        ('VALIDE', 'Validé'),
        ('ANNULE', 'Annulé'),
    ]

    numero_reception = models.CharField(max_length=50, unique=True, editable=False)
    ordre_achat = models.ForeignKey(
        OrdreAchat, on_delete=models.PROTECT, related_name='receptions'
    )
    depot_destination = models.ForeignKey(
        'entreprise.Depot', on_delete=models.PROTECT, related_name='receptions'
    )

    date_reception = models.DateTimeField(auto_now_add=True)
    recu_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='receptions'
    )
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='EN_COURS')
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "Bon de réception"
        verbose_name_plural = "Bons de réception"
        ordering = ['-date_reception']

    def __str__(self):
        return f"BR {self.numero_reception}"

    def save(self, *args, **kwargs):
        if not self.numero_reception:
            prefix = "BR-"
            for _ in range(5):
                with transaction.atomic():
                    last = (
                        BonReception.objects.select_for_update()
                        .filter(numero_reception__startswith=prefix)
                        .order_by('-numero_reception')
                        .first()
                    )
                    next_num = 1
                    if last:
                        try:
                            next_num = int(last.numero_reception.split('-')[-1]) + 1
                        except (ValueError, IndexError):
                            next_num = 1
                    self.numero_reception = f"{prefix}{next_num:06d}"
                    try:
                        return super().save(*args, **kwargs)
                    except IntegrityError:
                        self.numero_reception = ""
                        continue
            raise IntegrityError("Impossible de générer un numéro de réception unique.")
        return super().save(*args, **kwargs)


class LigneBonReception(models.Model):
    bon_reception = models.ForeignKey(BonReception, on_delete=models.CASCADE, related_name='lignes')
    ligne_ordre_achat = models.ForeignKey(
        LigneOrdreAchat, on_delete=models.PROTECT, related_name='lignes_reception'
    )

    quantite_recue_effective = models.DecimalField(max_digits=15, decimal_places=2)
    quantite_ecartee = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    motif_ecart = models.CharField(max_length=255, blank=True)
    lot_batch = models.CharField(max_length=20, blank=True, default="")
    location = models.ForeignKey(
        'entreprise.Location', on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        verbose_name = "Ligne de bon de réception"
        verbose_name_plural = "Lignes de bon de réception"

    def __str__(self):
        return f"{self.ligne_ordre_achat.produit.nom} × {self.quantite_recue_effective}"
