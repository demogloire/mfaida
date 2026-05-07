import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models
from entreprise.models import Branche, Entreprise, Depot, PointVente


class Role(models.Model):
    class FamilleMetier(models.TextChoices):
        MANAGER = 'MANAGER', 'Manager entreprise'
        ASSISTANT_MANAGER = 'ASSISTANT_MANAGER', 'Assistant manager entreprise'
        CAISSIER = 'CAISSIER', 'Caissier (point de vente)'
        VENDEUR = 'VENDEUR', 'Vendeur (point de vente)'
        MAGASINIER = 'MAGASINIER', 'Magasinier (dépôt)'
        FINANCIER = 'FINANCIER', 'Financier'
        COMPTABLE = 'COMPTABLE', 'Comptable'
        LOGISTICIEN = 'LOGISTICIEN', 'Logisticien'
        RESSOURCES_HUMAINES = 'RESSOURCES_HUMAINES', 'Ressources humaines (entreprise)'

    entreprise = models.ForeignKey(Entreprise, on_delete=models.CASCADE, related_name='roles')
    nom = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    famille_metier = models.CharField(
        max_length=24,
        choices=FamilleMetier.choices,
        blank=True,
        default='',
        verbose_name='famille métier',
        help_text="Type de poste pour proposer les accès types ; peut être affine par les permissions du rôle.",
    )

    class Meta:
        verbose_name = "Rôle"
        unique_together = ('entreprise', 'nom')

    def __str__(self):
        return self.nom


class PermissionPersonnalisee(models.Model):
    code = models.CharField(max_length=100, unique=True)
    nom = models.CharField(max_length=255)

    class Meta:
        verbose_name = "Permission personnalisée"
        verbose_name_plural = "Permissions personnalisées"

    def __str__(self):
        return f"{self.nom} ({self.code})"


class RolePermission(models.Model):
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name='permissions')
    permission = models.ForeignKey(PermissionPersonnalisee, on_delete=models.CASCADE, related_name='roles')

    class Meta:
        unique_together = ('role', 'permission')
        verbose_name = "Permission du rôle"
        verbose_name_plural = "Permissions des rôles"

    def __str__(self):
        return f"{self.role.nom} → {self.permission.nom}"


class Profil(AbstractUser):
    """
    L'utilisateur principal de l'ERP.
    Hérite de username, password, email, last_name, first_name, etc.
    """
    branche = models.ForeignKey(
        Branche, on_delete=models.SET_NULL,
        related_name='personnel', null=True, blank=True
    )
    role = models.ForeignKey(
        Role, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='utilisateurs'
    )

    telephone = models.CharField(max_length=20, blank=True)
    photo = models.ImageField(upload_to='profils/', null=True, blank=True)
    signature = models.ImageField(upload_to='signatures/', null=True, blank=True,
                                  help_text="Signature utilisée sur les documents (factures, bons de commande…)")
    adresse = models.TextField(blank=True)
    admin = models.BooleanField(default=False)

    date_creation = models.DateTimeField(auto_now_add=True, null=True)
    derniere_modification = models.DateTimeField(auto_now=True, null=True)

    profil_id = models.UUIDField(default=uuid.uuid4, editable=False)

    REQUIRED_FIELDS = ['email', 'first_name', 'last_name']

    class Meta:
        verbose_name = "Profil utilisateur"
        verbose_name_plural = "Profils utilisateurs"

    def __str__(self):
        return f"{self.get_full_name()} ({self.username})"

    def a_la_permission(self, code_permission):
        """Vérifie si l'utilisateur possède une permission via son rôle."""
        from utilisateur.acces_metier import utilisateur_peut_permission
        return utilisateur_peut_permission(self, code_permission)

    def a_acces_depot(self, depot_id, permission='peut_voir'):
        """Vérifie si l'utilisateur a une permission donnée sur un dépôt."""
        if self.admin or self.is_superuser:
            return True
        return self.acces_depots.filter(depot_id=depot_id, **{permission: True}).exists()

    def a_acces_point_vente(self, pv_id, permission='peut_voir'):
        """Vérifie si l'utilisateur a une permission donnée sur un point de vente."""
        if self.admin or self.is_superuser:
            return True
        return self.acces_points_vente.filter(point_vente_id=pv_id, **{permission: True}).exists()


class JournalAction(models.Model):
    """Trace toutes les actions significatives effectuées par un utilisateur."""

    VERBE_CHOICES = [
        ('creation', 'Création'),
        ('modification', 'Modification'),
        ('suppression', 'Suppression'),
        ('consultation', 'Consultation'),
        ('connexion', 'Connexion'),
        ('deconnexion', 'Déconnexion'),
        ('autre', 'Autre'),
    ]

    utilisateur = models.ForeignKey(
        'Profil', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='journal_actions'
    )
    verbe = models.CharField(max_length=20, choices=VERBE_CHOICES, default='autre')
    module = models.CharField(max_length=100, blank=True,
                              help_text="ex : utilisateurs, facturation, stock")
    description = models.TextField(blank=True)
    date_heure = models.DateTimeField(auto_now_add=True)
    adresse_ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        verbose_name = "Journal d'action"
        verbose_name_plural = "Journal des actions"
        ordering = ['-date_heure']

    def __str__(self):
        nom = self.utilisateur or "Inconnu"
        return f"[{self.get_verbe_display()}] {nom} — {self.module} — {self.date_heure:%d/%m/%Y %H:%M}"


class AccesDepot(models.Model):
    """Permissions granulaires d'un utilisateur sur un dépôt de sa branche."""
    utilisateur = models.ForeignKey(
        'Profil', on_delete=models.CASCADE,
        related_name='acces_depots'
    )
    depot = models.ForeignKey(
        Depot, on_delete=models.CASCADE,
        related_name='acces_utilisateurs'
    )
    peut_voir        = models.BooleanField(default=True,  verbose_name="Voir le stock")
    peut_recevoir    = models.BooleanField(default=False, verbose_name="Réceptionner des marchandises")
    peut_expedier    = models.BooleanField(default=False, verbose_name="Expédier / Transférer")
    peut_inventorier = models.BooleanField(default=False, verbose_name="Faire un inventaire")
    peut_administrer = models.BooleanField(default=False, verbose_name="Administrer le dépôt")

    class Meta:
        unique_together = ('utilisateur', 'depot')
        verbose_name = "Accès dépôt"
        verbose_name_plural = "Accès dépôts"

    def __str__(self):
        return f"{self.utilisateur} → {self.depot}"


class AccesPointVente(models.Model):
    """Permissions granulaires d'un utilisateur sur un point de vente de sa branche."""
    utilisateur = models.ForeignKey(
        'Profil', on_delete=models.CASCADE,
        related_name='acces_points_vente'
    )
    point_vente = models.ForeignKey(
        PointVente, on_delete=models.CASCADE,
        related_name='acces_utilisateurs'
    )
    peut_voir           = models.BooleanField(default=True,  verbose_name="Voir le point de vente")
    peut_vendre         = models.BooleanField(default=False, verbose_name="Créer des ventes")
    peut_faire_avoir    = models.BooleanField(default=False, verbose_name="Émettre des avoirs")
    peut_remise         = models.BooleanField(default=False, verbose_name="Accorder des remises")
    peut_gerer_caisse   = models.BooleanField(default=False, verbose_name="Gérer la caisse")
    peut_administrer    = models.BooleanField(default=False, verbose_name="Administrer le point de vente")

    class Meta:
        unique_together = ('utilisateur', 'point_vente')
        verbose_name = "Accès point de vente"
        verbose_name_plural = "Accès points de vente"

    def __str__(self):
        return f"{self.utilisateur} → {self.point_vente}"


class JournalConnexion(models.Model):
    utilisateur = models.ForeignKey(
        Profil, on_delete=models.CASCADE,
        related_name='journal_connexions', null=True, blank=True
    )
    username_tente = models.CharField(max_length=254, blank=True)
    date_heure = models.DateTimeField(auto_now_add=True)
    adresse_ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    succes = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Journal de connexion"
        verbose_name_plural = "Journal des connexions"
        ordering = ['-date_heure']

    def __str__(self):
        statut = "OK" if self.succes else "ECHEC"
        nom = self.utilisateur or self.username_tente
        return f"[{statut}] {nom} — {self.date_heure:%d/%m/%Y %H:%M}"
