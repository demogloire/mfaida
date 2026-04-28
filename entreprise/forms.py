from django import forms
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from .models import Entreprise, Branche, Location, Depot, PointVente, Devise
from django.core.validators import FileExtensionValidator
from django.core.exceptions import ValidationError




class EntrepriseForm(forms.ModelForm):
    nom=forms.CharField(required=True)
    rccm=forms.CharField()
    idnat=forms.CharField()
    numero_impot=forms.CharField()
    adresse_siege=forms.CharField( required=True) 
    telephone=forms.CharField(required=True)
    email=forms.EmailField(required=True)
    logo=forms.ImageField() 

    class Meta:
        model = Entreprise
        fields = ['nom', 'rccm', 'idnat','numero_impot','adresse_siege','telephone','email','logo']

        widgets = {
            # On force l'utilisation de FileInput (qui n'affiche pas l'URL)
            'logo': forms.FileInput(attrs={
                'class': 'form-control',
                'id': 'id_logo',
                'accept': 'image/*'
            }),
        }

class BrancheForm(forms.ModelForm):
    class Meta:
        model = Branche
        fields=["code_branche","entreprise","init_facture","init_proforma","init_bdcommande","init_location",
                "nom","ville","est_siege_social","sans_etagere_ordonne"]

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super(BrancheForm, self).__init__(*args, **kwargs)

        if 'entreprise' in self.fields:
            self.fields['entreprise'].empty_label = "--- Choisissez une entreprise ---"
            if self.request:
                self.fields['entreprise'].queryset = Entreprise.objects.filter(user=self.request.user)

class EtagereForm(forms.ModelForm):
    entreprise=forms.CharField(required=False, widget=forms.TextInput(attrs={'readonly': 'readonly'}))
    branche_un=forms.CharField(required=False, widget=forms.TextInput(attrs={'readonly': 'readonly'}))
    class Meta:
        model=Location
        fields=["initiale","reference","ramassage","capacite"]

        widgets = {
            'initiale': forms.TextInput(attrs={'readonly': 'readonly'}),
        }
    
    def __init__(self, *args, **kwargs):
        branche_id = kwargs.pop('branche_id', None)
        super(EtagereForm, self).__init__(*args, **kwargs)

        if 'initiale' in self.fields:
            branche=Branche.objects.filter(pk=branche_id).first()
            if branche_id:
                self.fields['initiale'].initial  = branche.init_location
                self.fields['branche_un'].initial  = branche.code_branche
                self.fields['entreprise'].initial  = branche.entreprise.nom


def validate_file_size(value):
    limit = 5 * 1024 * 1024  # Limite à 5 Mo (en octets)
    if value.size > limit:
        raise ValidationError("Le fichier est trop volumineux (max 5 Mo).")

class UploadFile(forms.Form ):
    file_excel = forms.FileField(validators=[
            FileExtensionValidator(allowed_extensions=['csv']),
            validate_file_size
        ])

class DepotForm(forms.ModelForm):
    class Meta:
        model = Depot
        fields = ["code_depot", "nom", "adresse", "est_principal", "est_actif"]

    def __init__(self, *args, branche_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._branche_id = branche_id

    def clean_code_depot(self):
        code = self.cleaned_data.get('code_depot', '').strip().upper()
        if self._branche_id:
            qs = Depot.objects.filter(branche_id=self._branche_id, code_depot__iexact=code)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(
                    "Un dépôt avec ce code existe déjà dans cette branche."
                )
        return code



class PoinDeVenteForm(forms.ModelForm):
    class Meta:
        model = PointVente
        fields = ["code_pointvente", "depot_source", "nom", "est_actif", "adresse"]

    def __init__(self, *args, **kwargs):
        params = kwargs.pop('params', None)
        user_id = params.get('user_id')
        branche_id = params.get('branche')
        super(PoinDeVenteForm, self).__init__(*args, **kwargs)
        self._branche_id = branche_id

        if 'depot_source' in self.fields:
            self.fields['depot_source'].empty_label = "--- Choisissez le dépôt ---"
            if branche_id:
                self.fields['depot_source'].queryset = Depot.objects.filter(
                    branche_id=branche_id, branche__entreprise__user=user_id
                )

    def clean_code_pointvente(self):
        code = self.cleaned_data.get('code_pointvente', '').strip().upper()
        if self._branche_id:
            qs = PointVente.objects.filter(branche_id=self._branche_id, code_pointvente__iexact=code)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(
                    "Un point de vente avec ce code existe déjà dans cette branche."
                )
        return code



class MajPoinDeVenteForm(forms.ModelForm):
    class Meta:
        model = PointVente
        fields = ["code_pointvente", "depot_source", "nom", "est_actif", "adresse"]

    def __init__(self, *args, **kwargs):
        params = kwargs.pop('params', None)
        user_id = params.get('user_id')
        branche_id = params.get('branche')
        super(MajPoinDeVenteForm, self).__init__(*args, **kwargs)
        self._branche_id = branche_id

        if 'code_pointvente' in self.fields:
            self.fields['code_pointvente'].disabled = True
            self.fields['code_pointvente'].required = False

        if 'depot_source' in self.fields:
            self.fields['depot_source'].empty_label = "--- Choisissez le dépôt ---"
            if branche_id:
                self.fields['depot_source'].queryset = Depot.objects.filter(
                    branche_id=branche_id, branche__entreprise__user=user_id
                )

class DeviseForm(forms.ModelForm):
    class Meta:
        model = Devise
        fields = ["entreprise", "code", "symbole", "taux_echange", "est_principale"]

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)
        if "entreprise" in self.fields:
            self.fields["entreprise"].empty_label = "--- Choisissez une entreprise ---"
            if self.request:
                self.fields["entreprise"].queryset = Entreprise.objects.filter(user=self.request.user)

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip().upper()
        if len(code) != 3:
            raise ValidationError("Le code devise doit contenir 3 lettres (ex: USD, CDF).")
        return code


