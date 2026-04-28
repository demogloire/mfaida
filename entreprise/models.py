from django.db import models
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
    entreprise = models.ForeignKey(
        Entreprise,
        on_delete=models.CASCADE,
        related_name='produits',
        verbose_name='Entreprise',
        help_text='Renseigné automatiquement selon la sous-catégorie ; sert à l’unicité du SKU.',
    )
    nom = models.CharField(max_length=255)
    code_barre = models.CharField(max_length=50, unique=True, blank=True, null=True)
    sku = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='SKU',
        help_text='Référence interne / unité de stock (unique par entreprise si renseignée).',
        db_index=True,
    )
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

    def libelle_ligne_achat(self):
        """Affichage BC / réceptions : SKU - nom - unité (code PCS, KG…)."""
        sku_txt = (self.sku or '').strip() or '-'
        return f'{sku_txt} - {self.nom} - {self.unite_mesure}'

    def save(self, *args, **kwargs):
        if self.sous_categorie_id:
            self.entreprise_id = self.sous_categorie.categorie.entreprise_id
        super().save(*args, **kwargs)

    @property
    def prix_vente_ttc(self):
        """ Calcule automatiquement le prix TTC """
        return self.prix_vente_ht * (1 + self.tva_taux / 100)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['entreprise', 'sku'],
                name='uniq_produit_sku_par_entreprise',
            ),
        ]

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
    




    

