from decimal import Decimal

from django import forms

from entreprise.models import PointVente, Devise
from facturation.models import Facture
from tiers.models import Client
from stock.models import MouvementStock


class FactureBrouillonForm(forms.ModelForm):
    class Meta:
        model = Facture
        fields = (
            'point_vente',
            'client',
            'devise',
            'taux_echange_appliqué',
            'mode_paiement',
        )

    def __init__(self, *args, entreprise=None, **kwargs):
        super().__init__(*args, **kwargs)
        if entreprise:
            self.fields['point_vente'].queryset = PointVente.objects.filter(
                branche__entreprise=entreprise,
                est_actif=True,
                depot_source__isnull=False,
            ).order_by('nom')
            self.fields['client'].queryset = Client.objects.filter(
                entreprise=entreprise, est_actif=True
            ).order_by('nom')
            self.fields['devise'].queryset = Devise.objects.filter(entreprise=entreprise).order_by('code')
        else:
            self.fields['point_vente'].queryset = PointVente.objects.filter(
                est_actif=True,
                depot_source__isnull=False,
            ).order_by('nom')
            self.fields['client'].queryset = Client.objects.filter(est_actif=True).order_by('nom')
            self.fields['devise'].queryset = Devise.objects.all().order_by('code')


class AjoutLigneFactureForm(forms.Form):
    mouvement_stock = forms.ModelChoiceField(
        queryset=MouvementStock.objects.none(),
        label='Lot / mouvement',
    )
    quantite = forms.DecimalField(min_value=Decimal('0.01'), max_digits=15, decimal_places=2)
    prix_unitaire_ht = forms.DecimalField(
        required=False,
        max_digits=15,
        decimal_places=2,
        label='Prix HT (ligne)',
        help_text='Par défaut : prix de vente catalogue du produit.',
    )

    def __init__(self, *args, point_vente=None, **kwargs):
        super().__init__(*args, **kwargs)
        if point_vente:
            from stock.access import mouvements_disponibles_pour_point_vente

            self.fields['mouvement_stock'].queryset = mouvements_disponibles_pour_point_vente(
                point_vente
            ).select_related('produit')

