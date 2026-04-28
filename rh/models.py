from django.db import models
from django.conf import settings
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
    nom = models.CharField(max_length=100) # ex: Finance, Logistique, Vente
    responsable = models.ForeignKey(Employe, on_delete=models.SET_NULL, null=True, related_name='dirige_departement')

class Contrat(models.Model):
    TYPES_CONTRAT = [('CDI', 'Durable'), ('CDD', 'Durée Déterminée'), ('STAGE', 'Stage')]
    
    employe = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name='contrats')
    departement = models.ForeignKey(Departement, on_delete=models.PROTECT)
    type_contrat = models.CharField(max_length=10, choices=TYPES_CONTRAT)
    titre_poste = models.CharField(max_length=100)
    
    date_debut = models.DateField()
    date_fin = models.DateField(null=True, blank=True)
    salaire_base = models.DecimalField(max_digits=15, decimal_places=2)
    devise = models.ForeignKey(Devise, on_delete=models.PROTECT)
    
    est_actuel = models.BooleanField(default=True)


class Presence(models.Model):
    employe = models.ForeignKey(Employe, on_delete=models.CASCADE)
    date = models.DateField()
    heure_arrivee = models.TimeField(null=True)
    heure_depart = models.TimeField(null=True)
    statut = models.CharField(max_length=20, default='PRESENT') # Present, Retard, Absent

class Conge(models.Model):
    TYPE_CONGE = [('ANNUEL', 'Annuel'), ('MALADIE', 'Maladie'), ('MATERNITE', 'Maternité')]
    employe = models.ForeignKey(Employe, on_delete=models.CASCADE)
    type_conge = models.CharField(max_length=20, choices=TYPE_CONGE)
    date_debut = models.DateField()
    date_fin = models.DateField()
    approuve = models.BooleanField(default=False)

class BulletinPaie(models.Model):
    employe = models.ForeignKey(Employe, on_delete=models.CASCADE)
    periode_mois = models.IntegerField() # 1 à 12
    periode_annee = models.IntegerField()
    
    salaire_brut = models.DecimalField(max_digits=15, decimal_places=2)
    allocations = models.DecimalField(max_digits=15, decimal_places=2, default=0) # Primes, transport
    retenues = models.DecimalField(max_digits=15, decimal_places=2, default=0)    # Taxes, Avances
    salaire_net = models.DecimalField(max_digits=15, decimal_places=2)
    
    date_paiement = models.DateField(null=True, blank=True)
    est_paye = models.BooleanField(default=False)

