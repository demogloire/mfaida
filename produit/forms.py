from django import forms
from django.core.exceptions import ValidationError
from entreprise.models import Categorie, SousCategorie, Produit, Entreprise
from utilisateur.permissions import peut_voir_prix_achat_ht


class CategorieForm(forms.ModelForm):
    class Meta:
        model = Categorie
        fields = ['entreprise', 'nom', 'description']
        widgets = {
            'entreprise': forms.Select(attrs={'class': 'form-select'}),
            'nom': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Alimentation, Hygiène…'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Description (optionnel)'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields['entreprise'].queryset = Entreprise.objects.filter(user=user)
        self.fields['entreprise'].empty_label = "— Choisir une entreprise —"


class SousCategorieForm(forms.ModelForm):
    class Meta:
        model = SousCategorie
        fields = ['categorie', 'nom']
        widgets = {
            'categorie': forms.Select(attrs={'class': 'form-select'}),
            'nom': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Produits laitiers…'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields['categorie'].queryset = Categorie.objects.filter(
                entreprise__user=user
            ).select_related('entreprise').order_by('entreprise__nom', 'nom')
        self.fields['categorie'].empty_label = "— Choisir une catégorie —"


class ProduitForm(forms.ModelForm):
    class Meta:
        model = Produit
        fields = [
            'sous_categorie', 'nom', 'code_barre', 'sku', 'description',
            'prix_achat_ht', 'prix_vente_ht', 'tva_taux',
            'unite_mesure', 'stock_alerte', 'image', 'est_actif',
            'methode_gestion', 'vie',
        ]
        widgets = {
            'sous_categorie': forms.Select(attrs={'class': 'form-select'}),
            'nom': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nom du produit'}),
            'code_barre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: 6901234567890 (optionnel)'}),
            'sku': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: CAT-REF-001 (optionnel)'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'prix_achat_ht': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'id': 'id_prix_achat_ht'}),
            'prix_vente_ht': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'id': 'id_prix_vente_ht'}),
            'tva_taux': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '100', 'id': 'id_tva_taux'}),
            'unite_mesure': forms.Select(attrs={'class': 'form-select'}),
            'stock_alerte': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'image': forms.FileInput(attrs={'class': 'form-control'}),
            'methode_gestion': forms.Select(attrs={'class': 'form-select'}),
            'vie': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'placeholder': 'Jours'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields['sous_categorie'].queryset = SousCategorie.objects.filter(
                categorie__entreprise__user=user
            ).select_related('categorie', 'categorie__entreprise').order_by('categorie__entreprise__nom', 'categorie__nom', 'nom')
        self.fields['sous_categorie'].empty_label = "— Choisir une sous-catégorie —"
        if user is not None and not peut_voir_prix_achat_ht(user):
            self.fields.pop('prix_achat_ht', None)

    def clean_sku(self):
        raw = self.cleaned_data.get('sku')
        sku = raw.strip() if raw else ''
        sku = sku or None
        sc = self.cleaned_data.get('sous_categorie')
        if sku and sc:
            ent_id = sc.categorie.entreprise_id
            qs = Produit.objects.filter(entreprise_id=ent_id, sku=sku)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError(
                    'Un produit avec ce SKU existe déjà pour cette entreprise.'
                )
        return sku


class ImportExcelForm(forms.Form):
    fichier = forms.FileField(
        label="Fichier Excel (.xlsx)",
        help_text="Téléchargez d'abord le modèle, remplissez-le, puis importez-le ici.",
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.xlsx'}),
    )

    def clean_fichier(self):
        fichier = self.cleaned_data['fichier']
        if not fichier.name.lower().endswith('.xlsx'):
            raise forms.ValidationError("Seuls les fichiers .xlsx sont acceptés.")
        if fichier.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Le fichier ne doit pas dépasser 5 Mo.")
        return fichier
