from django.db import models, IntegrityError, transaction
from django.conf import settings
from django.db.models import Q
from entreprise.models import Devise, Branche
from utilisateur.models import Profil

class Employe(models.Model):
    SEXE_CHOICES = [('M', 'Masculin'), ('F', 'Féminin')]
    ETAT_CIVIL = [('C', 'Célibataire'), ('M', 'Marié'), ('D', 'Divorcé'), ('V', 'Veuf')]

    # Liens
    branche = models.ForeignKey(Branche, on_delete=models.CASCADE)
    user_compte = models.OneToOneField(Profil, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Infos Personnelles
    matricule = models.CharField(max_length=20, unique=True)
    nom = models.CharField(max_length=100)
    postnom = models.CharField(max_length=100, blank=True)
    prenom = models.CharField(max_length=100)
    sexe = models.CharField(max_length=1, choices=SEXE_CHOICES)
    etat_civil = models.CharField(max_length=1, choices=ETAT_CIVIL)
    date_naissance = models.DateField()
    telephone = models.CharField(max_length=20)
    adresse = models.TextField()
    nombre_enfants = models.IntegerField(default=0)
    
    photo = models.ImageField(upload_to='rh/employes/', null=True, blank=True)
    est_actif = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.matricule} - {self.nom} {self.prenom}"


class Departement(models.Model):
    branche      = models.ForeignKey(Branche, on_delete=models.CASCADE, null=True, blank=True,
                                     related_name='departements')
    nom          = models.CharField(max_length=100)
    responsable  = models.ForeignKey(Employe, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='dirige_departement')

    class Meta:
        verbose_name        = 'Département'
        verbose_name_plural = 'Départements'
        ordering            = ['nom']

    def __str__(self):
        return self.nom

class Contrat(models.Model):
    TYPES_CONTRAT = [('CDI', 'Durable'), ('CDD', 'Durée Déterminée'), ('STAGE', 'Stage')]

    employe      = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name='contrats')
    departement  = models.ForeignKey(Departement, on_delete=models.PROTECT)
    type_contrat = models.CharField(max_length=10, choices=TYPES_CONTRAT)
    titre_poste  = models.CharField(max_length=100)

    date_debut   = models.DateField()
    date_fin     = models.DateField(null=True, blank=True)
    salaire_base = models.DecimalField(max_digits=15, decimal_places=2)
    devise       = models.ForeignKey(Devise, on_delete=models.PROTECT)

    est_actuel   = models.BooleanField(default=True)

    class Meta:
        verbose_name        = 'Contrat'
        verbose_name_plural = 'Contrats'
        ordering            = ['-date_debut']

    def __str__(self):
        return f"{self.titre_poste} ({self.get_type_contrat_display()}) — {self.employe}"


class Presence(models.Model):
    STATUTS = [
        ('PRESENT', 'Présent'),
        ('RETARD',  'Retard'),
        ('ABSENT',  'Absent'),
        ('CONGE',   'En congé'),
        ('FERIE',   'Jour férié'),
    ]

    employe       = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name='presences')
    date          = models.DateField()
    heure_arrivee = models.TimeField(null=True, blank=True)
    heure_depart  = models.TimeField(null=True, blank=True)
    statut        = models.CharField(max_length=20, choices=STATUTS, default='PRESENT')
    note          = models.CharField(max_length=200, blank=True, default='')

    class Meta:
        verbose_name        = 'Présence'
        verbose_name_plural = 'Présences'
        unique_together     = [('employe', 'date')]
        ordering            = ['-date', 'employe__nom']

    def __str__(self):
        return f"{self.employe} — {self.date} — {self.get_statut_display()}"


class Conge(models.Model):
    TYPE_CONGE = [
        ('ANNUEL',    'Congé annuel'),
        ('MALADIE',   'Maladie'),
        ('MATERNITE', 'Maternité / Paternité'),
        ('SANS_SOLDE','Sans solde'),
        ('AUTRE',     'Autre'),
    ]
    STATUTS = [
        ('DEMANDE',   'Demandé'),
        ('APPROUVEE', 'Approuvé'),
        ('REJETEE',   'Rejeté'),
        ('ANNULEE',   'Annulé'),
    ]

    employe          = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name='conges')
    type_conge       = models.CharField(max_length=20, choices=TYPE_CONGE)
    date_debut       = models.DateField()
    date_fin         = models.DateField()
    motif            = models.TextField(blank=True, default='')
    statut           = models.CharField(max_length=12, choices=STATUTS, default='DEMANDE')

    demande_par      = models.ForeignKey(
        Profil, on_delete=models.PROTECT, related_name='conges_demandes'
    )
    date_demande     = models.DateTimeField(auto_now_add=True)

    approuve_par     = models.ForeignKey(
        Profil, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='conges_traites'
    )
    date_approbation = models.DateTimeField(null=True, blank=True)
    note_approbation = models.TextField(blank=True, default='')

    class Meta:
        verbose_name        = 'Congé'
        verbose_name_plural = 'Congés'
        ordering            = ['-date_demande']

    def __str__(self):
        return f"{self.employe} — {self.get_type_conge_display()} ({self.date_debut} → {self.date_fin})"

    @property
    def nb_jours(self):
        if self.date_debut and self.date_fin:
            return (self.date_fin - self.date_debut).days + 1
        return 0

class BulletinPaie(models.Model):
    STATUTS = [
        ('BROUILLON', 'Brouillon'),
        ('VALIDE',    'Validé'),
        ('PAYE',      'Payé'),
    ]

    # Identification
    numero        = models.CharField(max_length=50, unique=True, editable=False, db_index=True)
    employe       = models.ForeignKey(Employe, on_delete=models.CASCADE,   related_name='bulletins')
    contrat       = models.ForeignKey('Contrat', on_delete=models.PROTECT, null=True, blank=True,
                                      related_name='bulletins')
    devise        = models.ForeignKey(Devise, on_delete=models.PROTECT,    null=True, blank=True)

    # Période
    periode_mois  = models.IntegerField()
    periode_annee = models.IntegerField()

    # Jours
    jours_ouvrables  = models.IntegerField(default=26,
                           help_text="Nombre de jours ouvrables du mois (base de calcul)")
    jours_prestes    = models.IntegerField(default=0,
                           help_text="Jours réellement travaillés (présent + retard)")
    jours_conges     = models.IntegerField(default=0)
    jours_absences   = models.IntegerField(default=0)

    # Montants
    salaire_base_ref = models.DecimalField(max_digits=15, decimal_places=2, default=0,
                           help_text="Salaire de base du contrat au moment de la génération")
    salaire_brut     = models.DecimalField(max_digits=15, decimal_places=2)
    allocations      = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    retenues         = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    retenues_avances = models.DecimalField(max_digits=15, decimal_places=2, default=0,
                           help_text="Total des avances sur salaire à déduire ce mois")
    salaire_net      = models.DecimalField(max_digits=15, decimal_places=2)

    # Statut & traçabilité
    statut           = models.CharField(max_length=12, choices=STATUTS, default='BROUILLON')
    note             = models.TextField(blank=True, default='')

    cree_par         = models.ForeignKey(Profil, on_delete=models.PROTECT,
                           related_name='bulletins_crees')
    date_creation    = models.DateTimeField(auto_now_add=True)

    valide_par       = models.ForeignKey(Profil, on_delete=models.SET_NULL,
                           null=True, blank=True, related_name='bulletins_valides')
    date_validation  = models.DateTimeField(null=True, blank=True)

    paye_par         = models.ForeignKey(Profil, on_delete=models.SET_NULL,
                           null=True, blank=True, related_name='bulletins_payes')
    date_paiement    = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name        = 'Bulletin de paie'
        verbose_name_plural = 'Bulletins de paie'
        unique_together     = [('employe', 'periode_mois', 'periode_annee')]
        ordering            = ['-periode_annee', '-periode_mois', 'employe__nom']

    def __str__(self):
        return f"{self.numero} — {self.employe} ({self.periode_mois:02d}/{self.periode_annee})"

    @property
    def total_retenues(self):
        return (self.retenues or 0) + (self.retenues_avances or 0)

    @property
    def nom_mois(self):
        noms = ['', 'Janvier','Février','Mars','Avril','Mai','Juin',
                'Juillet','Août','Septembre','Octobre','Novembre','Décembre']
        try:
            return noms[self.periode_mois]
        except IndexError:
            return str(self.periode_mois)

    def save(self, *args, **kwargs):
        if kwargs.get('update_fields') is None and not self.numero:
            prefix = 'BP-'
            for _ in range(30):
                try:
                    with transaction.atomic():
                        max_num = 0
                        for row in BulletinPaie.objects.select_for_update().filter(
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
            raise IntegrityError("Impossible de générer un numéro de bulletin unique.")
        return super().save(*args, **kwargs)


class LigneBulletin(models.Model):
    TYPES = [
        ('AVANTAGE', 'Avantage / Allocation'),
        ('RETENUE',  'Retenue'),
    ]

    bulletin = models.ForeignKey(BulletinPaie, on_delete=models.CASCADE, related_name='lignes')
    type     = models.CharField(max_length=10, choices=TYPES)
    libelle  = models.CharField(max_length=200)
    montant  = models.DecimalField(max_digits=15, decimal_places=2)
    avance   = models.ForeignKey('AvanceSalaire', on_delete=models.SET_NULL,
                   null=True, blank=True, related_name='ligne_bulletin')

    class Meta:
        ordering = ['type', 'libelle']

    def __str__(self):
        return f"{self.get_type_display()} — {self.libelle} — {self.montant}"


class AvanceSalaire(models.Model):
    STATUTS = [
        ('DEMANDE',    'Demandée'),
        ('APPROUVEE',  'Approuvée'),
        ('DECAISSEE',  'Décaissée'),
        ('REMBOURSEE', 'Remboursée'),
        ('REJETEE',    'Rejetée'),
    ]

    numero          = models.CharField(max_length=50, unique=True, editable=False, db_index=True)
    employe         = models.ForeignKey(Employe, on_delete=models.PROTECT, related_name='avances_salaire')
    point_vente     = models.ForeignKey(
        'entreprise.PointVente', on_delete=models.PROTECT,
        help_text="Point de vente dont la caisse sera débitée lors du décaissement."
    )
    montant         = models.DecimalField(max_digits=15, decimal_places=2)
    devise          = models.ForeignKey(Devise, on_delete=models.PROTECT)
    motif           = models.TextField(blank=True, default='')
    statut          = models.CharField(max_length=12, choices=STATUTS, default='DEMANDE')

    # Traçabilité
    demande_par     = models.ForeignKey(
        Profil, on_delete=models.PROTECT, related_name='avances_demandees'
    )
    date_demande    = models.DateTimeField(auto_now_add=True)

    approuve_par    = models.ForeignKey(
        Profil, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='avances_approuvees'
    )
    date_approbation = models.DateTimeField(null=True, blank=True)
    note_approbation = models.TextField(blank=True, default='')

    decaisse_par    = models.ForeignKey(
        Profil, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='avances_decaissees'
    )
    date_decaissement = models.DateTimeField(null=True, blank=True)
    transaction_caisse = models.OneToOneField(
        'caisse.TransactionCaisse', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='avance_salaire'
    )

    class Meta:
        verbose_name        = 'Avance sur salaire'
        verbose_name_plural = 'Avances sur salaire'
        ordering            = ['-date_demande']

    def __str__(self):
        return f"{self.numero} — {self.employe} — {self.montant} {self.devise}"

    def save(self, *args, **kwargs):
        if kwargs.get('update_fields') is None and not self.numero:
            prefix = 'AVS-'
            for _ in range(30):
                try:
                    with transaction.atomic():
                        max_num = 0
                        for row in AvanceSalaire.objects.select_for_update().filter(
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
            raise IntegrityError('Impossible de générer un numéro d\'avance unique.')
        return super().save(*args, **kwargs)

