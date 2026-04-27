from django.db import models, transaction, IntegrityError
from django.conf import settings

class Entreprise(models.Model):
    nom = models.CharField(max_length=100)
    rccm = models.CharField(max_length=100, verbose_name="RCCM ", blank=True)
    idnat = models.CharField(max_length=100, verbose_name="ID National", blank=True)
    numero_impot = models.CharField(max_length=100, verbose_name="Numero Impôt", blank=True)
    adresse_siege = models.TextField()
    telephone = models.CharField(max_length=20)
    email = models.EmailField(max_length=100)
    logo = models.ImageField(upload_to='logos/', null=True, blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="entreprises")
    nepas_actif = models.BooleanField(default=False)

    def __str__(self):
        return self.nom

class Devise(models.Model):
    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='devises')
    code = models.CharField(max_length=3) # ex: USD, CDF
    symbole = models.CharField(max_length=5)
    taux_echange = models.DecimalField(max_digits=15, decimal_places=4, default=1.0)
    est_principale = models.BooleanField(default=False)

    def __str__(self):
        return self.code

class Branche(models.Model):
    code_branche = models.CharField(max_length=5, unique=True)
    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='branches')
    init_facture=models.CharField(max_length=255,null=True)
    init_proforma=models.CharField(max_length=255,null=True)
    init_bdcommande=models.CharField(max_length=255,null=True)
    init_location=models.CharField(max_length=255,null=True)
    nom = models.CharField(max_length=255)
    ville = models.CharField(max_length=100)
    est_siege_social = models.BooleanField(default=False)
    est_actif = models.BooleanField(default=False)
    sans_etagere_ordonne = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.nom} ({self.ville})"

class Depot(models.Model):
    """ Stockage physique des marchandises """
    code_depot = models.CharField(max_length=5, null=False)
    branche = models.ForeignKey(Branche, on_delete=models.CASCADE, related_name='depots')
    nom = models.CharField(max_length=255)
    adresse = models.CharField(blank=True, max_length=255)
    est_principal = models.BooleanField(default=False)
    est_actif = models.BooleanField(default=True)

    class Meta:
        unique_together = ('branche', 'code_depot')
        verbose_name = "Dépôt"
        verbose_name_plural = "Dépôts"

    def __str__(self):
        return f"Dépôt: {self.nom} ({self.branche.nom})"

class PointVente(models.Model):
    """ Lieu de transaction (Caisse, Boutique) """
    code_pointvente = models.CharField(max_length=5, null=False)
    branche = models.ForeignKey(Branche, on_delete=models.CASCADE, related_name='points_de_vente')
    depot_source = models.ForeignKey(Depot, on_delete=models.SET_NULL, null=True, help_text="Dépôt d'où proviennent les articles vendus")
    nom = models.CharField(max_length=255)
    adresse = models.CharField(blank=True, max_length=255)
    est_actif = models.BooleanField(default=True)

    class Meta:
        unique_together = ('branche', 'code_pointvente')
        verbose_name = "Point de vente"
        verbose_name_plural = "Points de vente"

    def __str__(self):
        return self.nom


class Categorie(models.Model):
    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='categories')
    nom = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.nom

class SousCategorie(models.Model):
    categorie = models.ForeignKey(Categorie, on_delete=models.CASCADE, related_name='sous_categories')
    nom = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.categorie.nom} > {self.nom}"

class Produit(models.Model):
    # Unités de mesure courantes
    UNITES = [
        ('PCS', 'Pièce'),
        ('KG', 'Kilogramme'),
        ('L', 'Litre'),
        ('M', 'Mètre'),
        ('BOX', 'Carton/Boîte'),
    ]

    METHODES = [
        ('FIFO', 'First In First Out'),
        ('FEFO', 'First Expire First Out'),
        ('LIFO', 'Last In First Out'),
    ]

    sous_categorie = models.ForeignKey(SousCategorie, on_delete=models.CASCADE, related_name='produits')
    nom = models.CharField(max_length=255)
    code_barre = models.CharField(max_length=50, unique=True, blank=True, null=True)
    description = models.TextField(blank=True)
    
    # Prix et Taxes
    prix_achat_ht = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    prix_vente_ht = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    tva_taux = models.DecimalField(max_digits=5, decimal_places=2, default=16.00) # ex: 16%
    
    # Stockage
    unite_mesure = models.CharField(max_length=10, choices=UNITES, default='PCS')
    stock_alerte = models.DecimalField(max_digits=10, decimal_places=2, default=5.00) # Seuil pour notification
    
    image = models.ImageField(upload_to='produits/', null=True, blank=True)
    est_actif = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    #Methode de gestion
    methode_gestion = models.CharField(max_length=30, choices=METHODES, default='FEFO')
    vie =  models.IntegerField(default=30)

    def __str__(self):
        return self.nom

    @property
    def prix_vente_ttc(self):
        """ Calcule automatiquement le prix TTC """
        return self.prix_vente_ht * (1 + self.tva_taux / 100)

class Location(models.Model):
    initiale = models.CharField(max_length=4)
    reference = models.CharField(max_length=6, null= False)  # pas unique
    code = models.CharField(max_length=10)
    capacite = models.PositiveIntegerField(default=1, null= False)
    branche = models.ForeignKey(Branche,on_delete=models.CASCADE,related_name='locations')
    ramassage = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.code} ({self.initiale})"

    class Meta:
        pass
        #ordering = ['code']
    


## FOURNISSEUR CLIENT

class Fournisseur(models.Model):
    # Lien avec l'organisation
    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='fournisseurs')
    
    # Informations Générales
    intial = models.CharField(max_length=255, blank=True, default="")
    reference = models.CharField(max_length=255, blank=True, default="")
    code_fournisseur = models.CharField(max_length=255)

    nom_societe = models.CharField(max_length=255)
    rccm_id = models.CharField(max_length=100, blank=True, verbose_name="ID Fiscal / RCCM")
    contact_nom = models.CharField(max_length=100, blank=True) # Nom de la personne de contact
    
    # Coordonnées
    telephone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    adresse = models.TextField()
    ville = models.CharField(max_length=100, blank=True)
    
    # Finance
    solde_du = models.DecimalField(max_digits=15, decimal_places=2, default=0.00) # Ce que l'entreprise doit au fournisseur
    est_actif = models.BooleanField(default=True)
    date_enregistrement = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["entreprise", "code_fournisseur"], name="uniq_fournisseur_code_par_entreprise"),
        ]

    def __str__(self):
        return self.nom_societe
    
    def save(self, *args, **kwargs):
        if not self.code_fournisseur:
            prefix = "FOU-"
            for _ in range(5):
                with transaction.atomic():
                    last = (
                        Fournisseur.objects.select_for_update()
                        .filter(entreprise=self.entreprise, code_fournisseur__startswith=prefix)
                        .order_by("-code_fournisseur")
                        .first()
                    )
                    next_number = 1
                    if last and last.code_fournisseur:
                        try:
                            next_number = int(last.code_fournisseur.replace(prefix, "")) + 1
                        except ValueError:
                            next_number = 1
                    self.code_fournisseur = f"{prefix}{next_number:06d}"
                    try:
                        return super().save(*args, **kwargs)
                    except IntegrityError:
                        self.code_fournisseur = ""
                        continue
            raise IntegrityError("Impossible de générer un code fournisseur unique.")

        return super().save(*args, **kwargs)


class Client(models.Model):
    TYPES_CLIENT = [
        ('AUTRE', 'Autre type client'),
        ('DETAIL', 'Particulier / Détail'),
        ('GROS', 'Grossiste / Entreprise'),
    ]

    # Informations Générales
    intial = models.CharField(max_length=255)
    reference = models.CharField(max_length=255)
    code_client=models.CharField(max_length=255)

    # Lien avec l'organisation
    branche = models.ForeignKey(Branche, on_delete=models.CASCADE, related_name='clients')
    
    # Profil Client
    nom = models.CharField(max_length=255) # Nom complet ou Raison sociale
    type_client = models.CharField(max_length=10, choices=TYPES_CLIENT, default='DETAIL')
    telephone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    adresse = models.TextField(blank=True)
    
    # Gestion de la Fidélité et Crédit
    limite_credit = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    solde_compte = models.DecimalField(max_digits=15, decimal_places=2, default=0.00) # Crédit client ou dette
    points_fidelite = models.IntegerField(default=0)
    
    date_creation = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.nom} - {self.type_client}"
    
    def save(self, *args, **kwargs):
        self.code_client = f"{self.intial}{self.reference}"
        super().save(*args, **kwargs)


class OrdreAchat(models.Model):
    STATUT_CHOICES = [
        ('BROUILLON', 'Brouillon'),
        ('ENVOYE', 'Envoyé au Fournisseur'),
        ('RECU_PARTIEL', 'Reçu Partiellement'),
        ('RECU_TOTAL', 'Reçu Totalement'),
        ('ANNULE', 'Annulé'),
    ]

    # Identification
    numero_commande = models.CharField(max_length=50, unique=True, editable=False)
    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE)
    fournisseur = models.ForeignKey(Fournisseur, on_delete=models.PROTECT) # Table à créer
    
    # Destination
    depot_destination = models.ForeignKey(Depot, on_delete=models.SET_NULL, null=True)
    pointdevente_destination = models.ForeignKey(PointVente, on_delete=models.SET_NULL, null=True)
    
    # Dates et Statut
    date_commande = models.DateTimeField(auto_now_add=True)
    date_livraison_prevue = models.DateField(null=True, blank=True)
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='BROUILLON')
    
    # Finance (Valeurs calculées ou stockées)
    devise = models.ForeignKey(Devise, on_delete=models.SET_NULL, null=True)
    total_ht = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    total_tva = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    total_ttc = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    
    # Tracking
    cree_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"BC {self.numero_commande} - {self.fournisseur.nom_societe}"

class LigneOrdreAchat(models.Model):
    ordre_achat = models.ForeignKey(OrdreAchat, on_delete=models.CASCADE, related_name='lignes')
    produit = models.ForeignKey(Produit, on_delete=models.CASCADE)
    
    # Quantités
    quantite_commandee = models.DecimalField(max_digits=15, decimal_places=2)
    quantite_recue = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)

    dateproduction = models.DateField(null=True, blank=True)
    dateexpiration = models.DateField(null=True, blank=True)
    lot_batch=models.CharField(max_length=20)
    unite=models.CharField(max_length=20)
    location = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True)

    reception = models.BooleanField(default=False)
    # Prix au moment de l'achat
    prix_unitaire_ht = models.DecimalField(max_digits=15, decimal_places=2)
    sous_total_ht = models.DecimalField(max_digits=15, decimal_places=2, editable=False)

    def save(self, *args, **kwargs):
        self.sous_total_ht = self.quantite_commandee * self.prix_unitaire_ht
        super().save(*args, **kwargs)



    

