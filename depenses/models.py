from decimal import Decimal

from django.db import models, transaction, IntegrityError

from entreprise.models import PointVente, Devise
from utilisateur.models import Profil


class TypeDepense(models.Model):
    """Catégorie de dépense configurable par le manager / admin."""
    entreprise  = models.ForeignKey(
        'entreprise.Entreprise', on_delete=models.CASCADE, related_name='types_depense'
    )
    nom         = models.CharField(max_length=100)
    description = models.TextField(blank=True, default='')
    icone       = models.CharField(max_length=60, blank=True, default='ti-cash',
                                   help_text='Classe Tabler Icons, ex : ti-truck')
    couleur     = models.CharField(max_length=20, blank=True, default='#4c6ef5',
                                   help_text='Couleur hex, ex : #e65100')
    est_actif   = models.BooleanField(default=True)
    est_systeme = models.BooleanField(default=False,
                                      help_text='Type créé automatiquement, non supprimable.')
    ordre       = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['ordre', 'nom']
        unique_together = [('entreprise', 'nom')]

    def __str__(self):
        return self.nom


class Depense(models.Model):
    TYPES = [
        ('RETOUR_CLIENT',        'Remboursement client (retour vente)'),
        ('CHARGE_OPERATIONNELLE','Charge opérationnelle'),
        ('FOURNITURES',          'Fournitures & consommables'),
        ('TRANSPORT',            'Transport & livraison'),
        ('AUTRE',                'Autre dépense'),
    ]
    STATUTS = [
        ('BROUILLON', 'Brouillon'),
        ('VALIDEE',   'Validée'),
        ('ANNULEE',   'Annulée'),
    ]

    numero_depense  = models.CharField(max_length=50, unique=True, editable=False)
    point_vente     = models.ForeignKey(PointVente, on_delete=models.PROTECT, related_name='depenses')
    type_depense    = models.CharField(max_length=30, choices=TYPES, default='AUTRE')
    # Catégorie configurable (remplace progressivement type_depense pour les saisies manuelles)
    categorie       = models.ForeignKey(
        TypeDepense, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='depenses'
    )
    montant         = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    devise          = models.ForeignKey(Devise, on_delete=models.PROTECT)
    taux_echange    = models.DecimalField(max_digits=15, decimal_places=4, default=1)
    motif           = models.TextField(blank=True, default='')
    # Lien optionnel vers un retour vente (créé automatiquement lors de la validation)
    retour_vente    = models.OneToOneField(
        'facturation.RetourVente',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='depense_liee',
    )
    statut          = models.CharField(max_length=20, choices=STATUTS, default='BROUILLON')
    date_depense    = models.DateTimeField(auto_now_add=True)
    enregistre_par  = models.ForeignKey(
        Profil, on_delete=models.PROTECT, related_name='depenses_enregistrees'
    )
    valide_par      = models.ForeignKey(
        Profil, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='depenses_validees',
    )
    date_validation = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if kwargs.get('update_fields') is None and not self.numero_depense:
            prefix = 'DEP-'
            for _ in range(30):
                try:
                    with transaction.atomic():
                        max_num = 0
                        plen = len(prefix)
                        qs = (
                            Depense.objects.select_for_update()
                            .filter(numero_depense__startswith=prefix)
                            .only('numero_depense')
                        )
                        for row in qs:
                            tail = row.numero_depense[plen:]
                            try:
                                max_num = max(max_num, int(tail))
                            except ValueError:
                                continue
                        self.numero_depense = f'{prefix}{max_num + 1:06d}'
                        return super().save(*args, **kwargs)
                except IntegrityError:
                    self.numero_depense = ''
                    continue
            raise IntegrityError('Impossible de générer un numéro de dépense unique.')
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"DEP {self.numero_depense} — {self.get_type_depense_display()} ({self.montant})"
