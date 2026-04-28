from django import forms
from django.core.exceptions import ValidationError

from .models import Client, Fournisseur
from entreprise.models import Branche, Entreprise


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = [
            'branche', 'nom', 'type_client',
            'telephone', 'email', 'adresse',
            'limite_credit', 'notes', 'est_actif',
        ]
        widgets = {
            'adresse': forms.Textarea(attrs={'rows': 2}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, entreprise=None, admin=False, **kwargs):
        super().__init__(*args, **kwargs)
        self._entreprise = entreprise
        self._admin = admin

        if admin:
            # Administrateur applicatif : toutes les branches actives (toutes entreprises)
            qs = (
                Branche.objects.filter(est_actif=True)
                .select_related('entreprise')
                .order_by('entreprise__nom', 'nom')
            )
        elif entreprise is not None:
            # Utilisateur standard : uniquement les branches actives de son entreprise
            qs = Branche.objects.filter(entreprise=entreprise, est_actif=True).order_by('nom')
        else:
            qs = Branche.objects.none()

        branche_field = self.fields['branche']
        branche_field.queryset = qs
        if admin:

            def _label_branche(obj):
                return f'{obj.entreprise.nom} — {obj.nom}'

            branche_field.label_from_instance = _label_branche
        else:

            def _label_branche_user(obj):
                return obj.nom

            branche_field.label_from_instance = _label_branche_user

        branche_field.label = "Branche"
        self.fields['nom'].label = "Nom / Raison sociale"
        self.fields['type_client'].label = "Type de client"
        self.fields['limite_credit'].label = "Limite de crédit"
        self.fields['est_actif'].label = "Compte actif"

    def clean_branche(self):
        branche = self.cleaned_data.get('branche')
        if branche is None:
            return branche
        if self._admin:
            return branche
        ent = self._entreprise
        if ent is None:
            raise ValidationError('Aucune entreprise n\'est associée à votre compte.')
        if branche.entreprise_id != ent.pk:
            raise ValidationError(
                'Vous ne pouvez rattacher un client qu\'à une branche de votre entreprise.'
            )
        return branche


class FournisseurForm(forms.ModelForm):
    class Meta:
        model = Fournisseur
        fields = [
            'nom_societe', 'rccm_id', 'contact_nom',
            'telephone', 'email', 'adresse', 'ville',
            'notes', 'est_actif',
        ]
        widgets = {
            'adresse': forms.Textarea(attrs={'rows': 2}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, entreprise=None, admin=False, **kwargs):
        super().__init__(*args, **kwargs)
        self._entreprise = entreprise
        self._admin = admin
        if admin:
            self.fields['entreprise'] = forms.ModelChoiceField(
                label='Entreprise',
                queryset=Entreprise.objects.order_by('nom'),
                required=True,
                help_text='Rattaché à cette entreprise (bons de commande, achats).',
            )
            if self.instance.pk:
                self.fields['entreprise'].initial = self.instance.entreprise_id
        self.fields['nom_societe'].label = "Nom de la société"
        self.fields['rccm_id'].label = "ID Fiscal / RCCM"
        self.fields['contact_nom'].label = "Nom du contact"
        self.fields['est_actif'].label = "Fournisseur actif"
