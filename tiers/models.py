from django.db import models, transaction, IntegrityError


class Fournisseur(models.Model):
    entreprise = models.ForeignKey(
        'entreprise.Entreprise', on_delete=models.CASCADE, related_name='fournisseurs'
    )

    intial = models.CharField(max_length=255, blank=True, default="")
    reference = models.CharField(max_length=255, blank=True, default="")
    code_fournisseur = models.CharField(max_length=255)

    nom_societe = models.CharField(max_length=255)
    rccm_id = models.CharField(max_length=100, blank=True, verbose_name="ID Fiscal / RCCM")
    contact_nom = models.CharField(max_length=100, blank=True)

    telephone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    adresse = models.TextField()
    ville = models.CharField(max_length=100, blank=True)

    solde_du = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    notes = models.TextField(blank=True)
    est_actif = models.BooleanField(default=True)
    date_enregistrement = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'entreprise_fournisseur'
        verbose_name = "Fournisseur"
        verbose_name_plural = "Fournisseurs"
        constraints = [
            models.UniqueConstraint(
                fields=["entreprise", "code_fournisseur"],
                name="uniq_fournisseur_code_par_entreprise",
            ),
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

    CODE_PREFIX = 'CLI-'

    intial = models.CharField(max_length=255, blank=True, default='')
    reference = models.CharField(max_length=255, blank=True, default='')
    code_client = models.CharField(max_length=64, db_index=True)

    entreprise = models.ForeignKey(
        'entreprise.Entreprise',
        on_delete=models.CASCADE,
        related_name='clients_societe',
        help_text='Redondant avec la branche ; utilisé pour garantir un code client unique par société.',
    )

    branche = models.ForeignKey(
        'entreprise.Branche', on_delete=models.CASCADE, related_name='clients'
    )

    nom = models.CharField(max_length=255)
    type_client = models.CharField(max_length=10, choices=TYPES_CLIENT, default='DETAIL')
    telephone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    adresse = models.TextField(blank=True)

    limite_credit = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    solde_compte = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    points_fidelite = models.IntegerField(default=0)
    notes = models.TextField(blank=True)

    est_actif = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'entreprise_client'
        verbose_name = "Client"
        verbose_name_plural = "Clients"
        constraints = [
            models.UniqueConstraint(
                fields=('entreprise', 'code_client'),
                name='uniq_client_code_par_entreprise',
            ),
        ]

    def __str__(self):
        return f"{self.nom} ({self.get_type_client_display()})"

    def save(self, *args, **kwargs):
        if kwargs.get('update_fields') is not None:
            if self.branche_id:
                self.entreprise_id = self.branche.entreprise_id
            return super().save(*args, **kwargs)

        if self.branche_id:
            self.entreprise_id = self.branche.entreprise_id

        old_entreprise_id = None
        if self.pk:
            old_entreprise_id = (
                Client.objects.filter(pk=self.pk).values_list('entreprise_id', flat=True).first()
            )

        needs_generated_code = (
            not self.pk
            or not (self.code_client or '').strip()
            or (
                old_entreprise_id is not None
                and self.entreprise_id
                and old_entreprise_id != self.entreprise_id
            )
        )

        if needs_generated_code:
            for _ in range(25):
                try:
                    with transaction.atomic():
                        self._assign_next_code_client_locked()
                        super().save(*args, **kwargs)
                    return
                except IntegrityError:
                    continue
            raise IntegrityError('Impossible de générer un code client unique.')

        fusion = f'{self.intial}{self.reference}'.strip()
        if fusion:
            self.code_client = fusion
        super().save(*args, **kwargs)

    def _assign_next_code_client_locked(self):
        """Attribue CLI-NNNNNN en tenant compte du max numérique pour l'entreprise (lock inclus)."""
        ent_id = self.entreprise_id
        if not ent_id:
            raise IntegrityError('Impossible de générer le code client sans entreprise (branche manquante).')
        prefix = self.CODE_PREFIX
        qs = Client.objects.select_for_update().filter(entreprise_id=ent_id, code_client__startswith=prefix)
        max_num = 0
        self_pk = self.pk
        for row in qs.only('pk', 'code_client'):
            if self_pk and row.pk == self_pk:
                continue
            tail = row.code_client[len(prefix) :]
            try:
                max_num = max(max_num, int(tail))
            except ValueError:
                continue
        next_num = max_num + 1
        self.intial = prefix
        self.reference = f'{next_num:06d}'
        self.code_client = f'{self.intial}{self.reference}'
