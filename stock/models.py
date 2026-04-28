from django.db import models
from entreprise.models import Produit, PointVente, Depot, Location
from achat.models import LigneOrdreAchat
from utilisateur.models import Profil



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
    quantite_ecartee = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    quantite_active = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    # Référence au dernier achat pour traçabilité du coût
    prix_unitaire = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)

    dateproduction = models.DateField(null=True, blank=True)
    dateexpiration = models.DateField(null=True, blank=True)
    lot_batch = models.CharField(max_length=20, blank=True, default="")
    unite = models.CharField(max_length=20, blank=True, default="")
    location_code = models.CharField(max_length=20, blank=True, default="")

    ligneordreachat = models.ForeignKey(LigneOrdreAchat, on_delete=models.SET_NULL, null=True, blank=True)
    effectue_par = models.ForeignKey(Profil, on_delete=models.SET_NULL, null=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        place = self.depot.nom if self.depot_id else (self.pointvente.nom if self.pointvente_id else "N/A")
        return f"Mouvement {self.produit.nom} @ {place}"

class Inventaire(models.Model):
    lot=models.CharField(max_length=20)
    depot = models.ForeignKey(Depot, on_delete=models.CASCADE,null=True,blank=True)
    pointdevente = models.ForeignKey(PointVente, on_delete=models.CASCADE,null=True,blank=True)
    date_inventaire = models.DateField()
    cloture = models.BooleanField(default=False) # Si True, on ne peut plus modifier
    valide_par = models.ForeignKey(Profil, on_delete=models.SET_NULL, null=True)

class LigneInventaire(models.Model):
    inventaire = models.ForeignKey(Inventaire, on_delete=models.CASCADE, related_name='lignes')
    produit = models.ForeignKey(Produit, on_delete=models.CASCADE)
    quantite_theorique = models.DecimalField(max_digits=15, decimal_places=2) # Ce que l'ERP dit
    quantite_physique = models.DecimalField(max_digits=15, decimal_places=2)  # Ce que l'agent compte
    ecart = models.DecimalField(max_digits=15, decimal_places=2, editable=False)

    def save(self, *args, **kwargs):
        self.ecart = self.quantite_physique - self.quantite_theorique
        super().save(*args, **kwargs)