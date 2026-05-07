from decimal import Decimal

from django.db import models, IntegrityError, transaction
from django.utils import timezone

from entreprise.models import PointVente, Devise
from utilisateur.models import Profil


class SessionCaisse(models.Model):
    STATUTS = [
        ('OUVERTE',            'Ouverte'),
        ('EN_ATTENTE_CLOTURE', 'En attente de clôture'),
        ('CLOSE',              'Clôturée'),
        ('REJETEE',            'Clôture rejetée'),
    ]

    point_vente             = models.ForeignKey(PointVente, on_delete=models.PROTECT, related_name='sessions_caisse')
    devise                  = models.ForeignKey(Devise, on_delete=models.PROTECT)
    ouvert_par              = models.ForeignKey(Profil, on_delete=models.PROTECT, related_name='sessions_ouvertes')
    fond_ouverture          = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    statut                  = models.CharField(max_length=25, choices=STATUTS, default='OUVERTE')
    date_ouverture          = models.DateTimeField(default=timezone.now)
    # Clôture (saisie par le caissier)
    fond_reel_cloture       = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    commentaire_cloture     = models.TextField(blank=True, default='')
    soumis_cloture_le       = models.DateTimeField(null=True, blank=True)
    # Approbation manager
    approuve_par            = models.ForeignKey(Profil, on_delete=models.SET_NULL, null=True, blank=True, related_name='sessions_approuvees')
    commentaire_manager     = models.TextField(blank=True, default='')
    date_approbation        = models.DateTimeField(null=True, blank=True)
    date_cloture            = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name        = 'Session de caisse'
        verbose_name_plural = 'Sessions de caisse'
        ordering            = ['-date_ouverture']

    # ── Propriétés calculées ──────────────────────────────────────────────

    @property
    def total_encaissements(self):
        return self.transactions.filter(
            type_transaction='ENCAISSEMENT'
        ).aggregate(t=models.Sum('montant'))['t'] or Decimal('0')

    @property
    def total_decaissements(self):
        return self.transactions.filter(
            type_transaction__in=['DECAISSEMENT', 'RETRAIT']
        ).aggregate(t=models.Sum('montant'))['t'] or Decimal('0')

    @property
    def total_depots(self):
        return self.transactions.filter(
            type_transaction='DEPOT'
        ).aggregate(t=models.Sum('montant'))['t'] or Decimal('0')

    @property
    def fond_theorique(self):
        return (
            (self.fond_ouverture or Decimal('0'))
            + self.total_encaissements
            + self.total_depots
            - self.total_decaissements
        )

    @property
    def ecart_cloture(self):
        if self.fond_reel_cloture is None:
            return None
        return self.fond_reel_cloture - self.fond_theorique

    def __str__(self):
        return f"Session {self.point_vente.nom} — {self.date_ouverture:%d/%m/%Y %H:%M}"


class TransactionCaisse(models.Model):
    TYPES = [
        ('ENCAISSEMENT', 'Encaissement'),
        ('DECAISSEMENT', 'Décaissement'),
        ('DEPOT',        'Dépôt de fonds'),
        ('RETRAIT',      'Retrait de fonds'),
    ]
    MODES = [
        ('ESPECES',      'Espèces'),
        ('MOBILE_MONEY', 'Mobile Money'),
        ('CARTE',        'Carte bancaire'),
        ('CHEQUE',       'Chèque'),
        ('VIREMENT',     'Virement bancaire'),
        ('CREDIT',       'Crédit client'),
        ('AUTRE',        'Autre'),
    ]

    numero            = models.CharField(max_length=50, unique=True, editable=False, db_index=True)
    session           = models.ForeignKey(SessionCaisse, on_delete=models.PROTECT, related_name='transactions')
    type_transaction  = models.CharField(max_length=20, choices=TYPES)
    mode_paiement     = models.CharField(max_length=20, choices=MODES, default='ESPECES')
    montant           = models.DecimalField(max_digits=15, decimal_places=2)
    devise            = models.ForeignKey(Devise, on_delete=models.PROTECT)
    taux_echange      = models.DecimalField(max_digits=15, decimal_places=4, default=1)
    motif             = models.TextField(blank=True, default='')
    # Liens vers les documents sources (optionnels)
    client            = models.ForeignKey(
        'tiers.Client', on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions_caisse'
    )
    facture           = models.ForeignKey(
        'facturation.Facture', on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions_caisse'
    )
    depense           = models.ForeignKey(
        'depenses.Depense', on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions_caisse'
    )
    retour_vente      = models.ForeignKey(
        'facturation.RetourVente', on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions_caisse'
    )
    effectue_par      = models.ForeignKey(Profil, on_delete=models.PROTECT, related_name='transactions_caisse')
    date_transaction  = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name        = 'Transaction de caisse'
        verbose_name_plural = 'Transactions de caisse'
        ordering            = ['-date_transaction']

    def save(self, *args, **kwargs):
        if kwargs.get('update_fields') is None and not self.numero:
            prefix = 'TXN-'
            for _ in range(30):
                try:
                    with transaction.atomic():
                        max_num = 0
                        for row in TransactionCaisse.objects.select_for_update().filter(
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
            raise IntegrityError('Impossible de générer un numéro de transaction unique.')
        return super().save(*args, **kwargs)

    @property
    def montant_base(self):
        """Montant converti dans la devise de la session."""
        return self.montant * self.taux_echange

    def __str__(self):
        return f"{self.numero} — {self.get_type_transaction_display()} {self.montant} {self.devise}"
