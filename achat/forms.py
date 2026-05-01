from django import forms
from django.core.exceptions import ValidationError
from .models import OrdreAchat, LigneOrdreAchat, BonReception


class OrdreAchatForm(forms.ModelForm):
    class Meta:
        model = OrdreAchat
        fields = [
            'fournisseur', 'depot_destination', 'pointdevente_destination',
            'date_livraison_prevue', 'devise', 'notes',
        ]
        widgets = {
            # ISO obligatoire pour <input type="date"> ; sinon en fr_FR la valeur affichée peut être invalide
            # et le navigateur envoie vide → écrase la date existante à None lors de l'enregistrement.
            'date_livraison_prevue': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, entreprise=None, admin=False, **kwargs):
        self._entreprise_scope = entreprise
        self._admin = admin
        super().__init__(*args, **kwargs)
        from tiers.models import Fournisseur
        from entreprise.models import Depot, PointVente, Devise, Branche

        if admin:
            # Admin : tous les fournisseurs, dépôts, PDV actifs, toutes entreprises
            self.fields['fournisseur'].queryset = Fournisseur.objects.filter(est_actif=True).order_by('entreprise__nom', 'nom_societe')
            branches_actives = Branche.objects.filter(est_actif=True)
            self.fields['depot_destination'].queryset = Depot.objects.filter(branche__in=branches_actives, est_actif=True).order_by('branche__nom', 'nom')
            self.fields['pointdevente_destination'].queryset = PointVente.objects.filter(branche__in=branches_actives, est_actif=True).order_by('branche__nom', 'nom')
            self.fields['devise'].queryset = Devise.objects.all()
        elif entreprise:
            # Utilisateur normal : uniquement son entreprise
            self.fields['fournisseur'].queryset = Fournisseur.objects.filter(entreprise=entreprise, est_actif=True)
            branches = entreprise.branches.filter(est_actif=True)
            self.fields['depot_destination'].queryset = Depot.objects.filter(branche__in=branches, est_actif=True)
            self.fields['pointdevente_destination'].queryset = PointVente.objects.filter(branche__in=branches, est_actif=True)
            self.fields['devise'].queryset = Devise.objects.filter(entreprise=entreprise)
        else:
            self.fields['fournisseur'].queryset = Fournisseur.objects.none()
            self.fields['depot_destination'].queryset = Depot.objects.none()
            self.fields['pointdevente_destination'].queryset = PointVente.objects.none()
            self.fields['devise'].queryset = Devise.objects.none()

        self.fields['fournisseur'].label = "Fournisseur"
        self.fields['depot_destination'].label = "Dépôt de destination"
        self.fields['pointdevente_destination'].label = "Point de vente de destination"
        self.fields['date_livraison_prevue'].label = "Date de livraison prévue"
        self.fields['devise'].label = "Devise"
        self.fields['depot_destination'].required = False
        self.fields['pointdevente_destination'].required = False
        self.fields['devise'].required = False

        dl = self.fields['date_livraison_prevue']
        dl.input_formats = ['%Y-%m-%d']

    def clean(self):
        cleaned = super().clean()
        dep = cleaned.get('depot_destination')
        pv = cleaned.get('pointdevente_destination')
        if dep and pv and dep.branche.entreprise_id != pv.branche.entreprise_id:
            raise ValidationError(
                {
                    'pointdevente_destination': (
                        'Le point de vente doit appartenir à la même entreprise que le dépôt de destination.'
                    ),
                }
            )

        if self._admin:
            return cleaned
        ent = self._entreprise_scope
        if not ent:
            raise ValidationError("Aucune entreprise n'est associée à votre compte.")
        four = cleaned.get('fournisseur')
        if four and four.entreprise_id != ent.pk:
            raise ValidationError({"fournisseur": "Ce fournisseur n'appartient pas à votre entreprise."})
        if dep and dep.branche.entreprise_id != ent.pk:
            raise ValidationError({"depot_destination": "Ce dépôt n'appartient pas à votre entreprise."})
        if pv and pv.branche.entreprise_id != ent.pk:
            raise ValidationError({"pointdevente_destination": "Ce point de vente n'appartient pas à votre entreprise."})
        dev = cleaned.get('devise')
        if dev and dev.entreprise_id != ent.pk:
            raise ValidationError({"devise": "Cette devise n'appartient pas à votre entreprise."})
        return cleaned


class LigneOrdreAchatForm(forms.ModelForm):
    class Meta:
        model = LigneOrdreAchat
        fields = [
            'produit', 'quantite_commandee', 'prix_unitaire_ht',
            'unite', 'dateproduction', 'dateexpiration', 'lot_batch', 'location',
        ]
        widgets = {
            'dateproduction': forms.DateInput(attrs={'type': 'date'}),
            'dateexpiration': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, commande=None, **kwargs):
        self._commande = commande
        super().__init__(*args, **kwargs)
        from entreprise.models import Produit, Location

        self._entreprise_catalogue = None
        if commande:
            bid = None
            if commande.depot_destination_id:
                bid = commande.depot_destination.branche_id
            elif commande.pointdevente_destination_id:
                bid = commande.pointdevente_destination.branche_id
            self._entreprise_catalogue = commande.entreprise
            if bid is not None:
                self.fields['location'].queryset = Location.objects.filter(branche_id=bid).order_by('code')
            else:
                branches = commande.entreprise.branches.filter(est_actif=True)
                self.fields['location'].queryset = Location.objects.filter(
                    branche__in=branches,
                ).order_by('branche__nom', 'code')

            ent = self._entreprise_catalogue
            if ent:
                self.fields['produit'].queryset = Produit.objects.filter(
                    sous_categorie__categorie__entreprise=ent,
                    est_actif=True,
                ).select_related('sous_categorie__categorie').order_by('nom')
                self.fields['produit'].label_from_instance = (
                    lambda p: p.libelle_ligne_achat
                )
                if commande.depot_destination_id:
                    self.fields['produit'].help_text = (
                        f'Produits actifs du catalogue « {ent.nom} » (entreprise du dépôt de destination).'
                    )
                else:
                    self.fields['produit'].help_text = (
                        f'Produits actifs du catalogue « {ent.nom} » (entreprise du bon de commande).'
                    )
            else:
                self.fields['produit'].queryset = Produit.objects.none()
                self.fields['location'].queryset = Location.objects.none()
        else:
            self.fields['produit'].queryset = Produit.objects.none()
            self.fields['location'].queryset = Location.objects.none()

        self.fields['produit'].label = "Produit"
        self.fields['quantite_commandee'].label = "Quantité commandée"
        self.fields['prix_unitaire_ht'].label = "Prix unitaire HT"
        self.fields['location'].required = False
        self.fields['dateproduction'].required = False
        self.fields['dateexpiration'].required = False
        self.fields['lot_batch'].required = False

    def clean(self):
        cleaned = super().clean()
        ent = getattr(self, '_entreprise_catalogue', None)
        produit = cleaned.get('produit')
        if ent and produit and produit.sous_categorie.categorie.entreprise_id != ent.pk:
            self.add_error('produit', "Ce produit n'appartient pas au catalogue de l'entreprise de cette commande.")
        cmd = getattr(self, '_commande', None)
        loc = cleaned.get('location')
        if cmd and loc:
            if cmd.depot_destination_id:
                if loc.branche_id != cmd.depot_destination.branche_id:
                    self.add_error(
                        'location',
                        "Cet emplacement n'appartient pas à la branche du dépôt de destination.",
                    )
            elif cmd.pointdevente_destination_id:
                if loc.branche_id != cmd.pointdevente_destination.branche_id:
                    self.add_error(
                        'location',
                        "Cet emplacement n'appartient pas à la branche du point de vente de destination.",
                    )
            elif loc.branche.entreprise_id != cmd.entreprise_id:
                self.add_error('location', "Cet emplacement n'appartient pas à l'entreprise de la commande.")
        return cleaned


class BonReceptionForm(forms.ModelForm):
    class Meta:
        model = BonReception
        fields = ['depot_destination', 'point_destination', 'fournisseur']

    def __init__(self, *args, commande=None, entreprise=None, admin=False, **kwargs):
        self.commande = commande
        self._entreprise_scope = entreprise
        self._admin = admin
        super().__init__(*args, **kwargs)

        from entreprise.models import Depot, PointVente, Branche
        from tiers.models import Fournisseur

        if admin:
            branches_actives = Branche.objects.filter(est_actif=True)
            self.fields['depot_destination'].queryset = (
                Depot.objects.filter(branche__in=branches_actives, est_actif=True).order_by('branche__nom', 'nom')
            )
            self.fields['point_destination'].queryset = (
                PointVente.objects.filter(branche__in=branches_actives, est_actif=True).order_by('branche__nom', 'nom')
            )
            self.fields['fournisseur'].queryset = (
                Fournisseur.objects.filter(est_actif=True).order_by('entreprise__nom', 'nom_societe')
            )
        elif entreprise:
            branches = entreprise.branches.filter(est_actif=True)
            self.fields['depot_destination'].queryset = Depot.objects.filter(branche__in=branches, est_actif=True).order_by('nom')
            self.fields['point_destination'].queryset = PointVente.objects.filter(branche__in=branches, est_actif=True).order_by('nom')
            self.fields['fournisseur'].queryset = Fournisseur.objects.filter(entreprise=entreprise, est_actif=True).order_by('nom_societe')
        else:
            self.fields['depot_destination'].queryset = Depot.objects.none()
            self.fields['point_destination'].queryset = PointVente.objects.none()
            self.fields['fournisseur'].queryset = Fournisseur.objects.none()

        self.fields['depot_destination'].required = False
        self.fields['point_destination'].required = False

        self.fields['depot_destination'].label = 'Dépôt de réception'
        self.fields['point_destination'].label = 'Ou boutique (point de vente)'
        self.fields['fournisseur'].label = 'Fournisseur (optionnel)'

        if commande:
            if 'fournisseur' in self.fields:
                del self.fields['fournisseur']
            # Uniquement les dépôts / PDV figurant sur ce bon de commande
            if commande.depot_destination_id:
                self.fields['depot_destination'].queryset = Depot.objects.filter(
                    pk=commande.depot_destination_id,
                    est_actif=True,
                ).select_related('branche').order_by('nom')
            else:
                self.fields['depot_destination'].queryset = Depot.objects.none()
            if commande.pointdevente_destination_id:
                self.fields['point_destination'].queryset = PointVente.objects.filter(
                    pk=commande.pointdevente_destination_id,
                    est_actif=True,
                ).select_related('branche').order_by('nom')
            else:
                self.fields['point_destination'].queryset = PointVente.objects.none()
            # Pré-remplissage depuis le BC : si dépôt + PDV sont tous deux sur la commande, on propose le dépôt par défaut
            # (l’utilisateur peut basculer sur la boutique avant enregistrement).
            if commande.depot_destination_id:
                self.initial.setdefault('depot_destination', commande.depot_destination_id)
                if commande.pointdevente_destination_id:
                    hint = (
                        'Le bon de commande prévoit aussi un point de vente : vous pouvez réceptionner '
                        ' soit dans le dépôt indiqué, soit dans cette boutique (choix exclusif ci-dessous).'
                    )
                    self.fields['point_destination'].help_text = hint
                    self.fields['depot_destination'].help_text = hint
            elif commande.pointdevente_destination_id:
                self.initial.setdefault('point_destination', commande.pointdevente_destination_id)
        elif 'fournisseur' in self.fields:
            self.fields['fournisseur'].required = False

    def clean(self):
        cleaned = super().clean()
        dep = cleaned.get('depot_destination')
        pv = cleaned.get('point_destination')
        xor_ok = bool(dep) ^ bool(pv)
        if not xor_ok:
            raise ValidationError(
                'Indiquez soit un dépôt, soit une boutique — une seule destination à la fois.'
            )

        ent = self._entreprise_scope
        admin = self._admin

        if not admin and ent:
            if dep and dep.branche.entreprise_id != ent.pk:
                raise ValidationError({'depot_destination': "Ce dépôt n'est pas dans votre entreprise."})
            if pv and pv.branche.entreprise_id != ent.pk:
                raise ValidationError({'point_destination': "Ce point de vente n'est pas dans votre entreprise."})
            four = cleaned.get('fournisseur')
            if four and four.entreprise_id != ent.pk:
                raise ValidationError({'fournisseur': 'Ce fournisseur ne correspond pas à votre entreprise.'})
        elif not admin and not ent and self.commande is None:
            raise ValidationError("Aucune entreprise pour valider cette réception.")

        cmd = self.commande
        if cmd:
            branches_prevues = set()
            if cmd.depot_destination_id:
                branches_prevues.add(cmd.depot_destination.branche_id)
            if cmd.pointdevente_destination_id:
                branches_prevues.add(cmd.pointdevente_destination.branche_id)
            if branches_prevues:
                br_choix = None
                if dep:
                    br_choix = dep.branche_id
                elif pv:
                    br_choix = pv.branche_id
                if br_choix is not None and br_choix not in branches_prevues:
                    raise ValidationError(
                        'Réceptionnez dans un dépôt ou une boutique dont la branche fait partie des '
                        'destinations prévues sur ce bon de commande (voir dépôt / point de vente du BC).'
                    )

        return cleaned


class ImportLignesBcForm(forms.Form):
    fichier = forms.FileField(
        label='Fichier Excel (.xlsx)',
        help_text='Modèle : même ordre de colonnes que le fichier téléchargé depuis cette page.',
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.xlsx'}),
    )

    def clean_fichier(self):
        fichier = self.cleaned_data['fichier']
        if not fichier.name.lower().endswith('.xlsx'):
            raise forms.ValidationError('Seuls les fichiers .xlsx sont acceptés.')
        if fichier.size > 5 * 1024 * 1024:
            raise forms.ValidationError('Le fichier ne doit pas dépasser 5 Mo.')
        return fichier


# Formset inline pour les lignes de bon de réception (utilisé côté template manuellement)
LigneBonReceptionFormSet = None
