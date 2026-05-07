from django import forms
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm, PasswordChangeForm as DjangoPasswordChangeForm
from entreprise.models import Branche, Entreprise
from .models import Role, PermissionPersonnalisee, AccesDepot, AccesPointVente

User = get_user_model()


# ── Authentification ──────────────────────────────────────────────────────────

class CreationSuperUser(UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(required=True)
    last_name = forms.CharField(required=True)
    password1 = forms.CharField(widget=forms.PasswordInput(), required=True)
    password2 = forms.CharField(widget=forms.PasswordInput(), required=True)
    acceptez = forms.BooleanField(required=True, error_messages={'required': "Acceptez les CGU"})

    class Meta:
        model = User
        fields = ['email', 'first_name', 'last_name', 'password1', 'password2']

    def clean_password2(self):
        p1 = self.cleaned_data.get("password1")
        p2 = self.cleaned_data.get("password2")
        if p1 and p2 and p1 != p2:
            raise ValidationError("Les mots de passe doivent être identiques.")
        return p2


class LoginForm(forms.Form):
    username = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'placeholder': 'Adresse e-mail'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'Mot de passe'})
    )
    remember_me = forms.BooleanField(required=False)


class MotDePasseOublieForm(forms.Form):
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'placeholder': 'Votre adresse e-mail'})
    )

    def clean_email(self):
        email = self.cleaned_data['email']
        if not User.objects.filter(email=email, is_active=True).exists():
            raise ValidationError("Aucun compte actif trouvé avec cette adresse e-mail.")
        return email


# ── Profil personnel ──────────────────────────────────────────────────────────

class ModificationProfilForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'telephone', 'adresse', 'photo']
        widgets = {
            'adresse': forms.Textarea(attrs={'rows': 3}),
        }

    def clean_email(self):
        email = self.cleaned_data['email']
        qs = User.objects.filter(email=email).exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("Cette adresse e-mail est déjà utilisée.")
        return email


class ChangerMotDePasseForm(DjangoPasswordChangeForm):
    """Réutilise le formulaire Django standard, juste renommé."""
    pass


class SecuriteForm(forms.ModelForm):
    """
    Paramètres de sécurité : e-mail + confirmation du mot de passe actuel.
    Le mot de passe actuel est demandé pour valider tout changement d'e-mail.
    """
    mot_de_passe_actuel = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'Mot de passe actuel'}),
        required=True,
        label="Mot de passe actuel",
        help_text="Requis pour confirmer toute modification.",
    )

    class Meta:
        model = User
        fields = ['email']
        labels = {'email': "Adresse e-mail"}

    def __init__(self, *args, **kwargs):
        self.utilisateur = kwargs.pop('utilisateur', None)
        super().__init__(*args, **kwargs)

    def clean_email(self):
        email = self.cleaned_data['email']
        qs = User.objects.filter(email=email)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("Cette adresse e-mail est déjà utilisée par un autre compte.")
        return email

    def clean_mot_de_passe_actuel(self):
        mdp = self.cleaned_data.get('mot_de_passe_actuel')
        if self.utilisateur and not self.utilisateur.check_password(mdp):
            raise ValidationError("Mot de passe incorrect.")
        return mdp


class SignatureForm(forms.ModelForm):
    """Permet à l'utilisateur de téléverser ou supprimer sa signature."""
    supprimer_signature = forms.BooleanField(
        required=False,
        label="Supprimer la signature actuelle",
    )

    class Meta:
        model = User
        fields = ['signature']
        labels = {'signature': "Fichier de signature (image PNG/JPG recommandée)"}
        help_texts = {
            'signature': "Fond transparent (PNG) conseillé. Dimensions recommandées : 400 × 150 px.",
        }

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.cleaned_data.get('supprimer_signature'):
            if instance.signature:
                instance.signature.delete(save=False)
            instance.signature = None
        if commit:
            instance.save()
        return instance


# ── CRUD Utilisateurs (réservé aux admins) ────────────────────────────────────

class CreationUtilisateurForm(UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(required=True, label="Prénom")
    last_name = forms.CharField(required=True, label="Nom")
    telephone = forms.CharField(required=False, max_length=20)
    adresse = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 2}))
    admin = forms.BooleanField(required=False, label="Administrateur ERP")

    class Meta:
        model = User
        fields = [
            'email', 'first_name', 'last_name',
            'telephone', 'adresse', 'photo',
            'branche', 'role', 'admin',
            'is_active',
        ]

    def __init__(self, *args, entreprise=None, choix_entreprise=False, htmx_entreprise_url='', **kwargs):
        self.choix_entreprise = choix_entreprise
        self._entreprise_fixe = entreprise
        self._peut_promouvoir_admin = kwargs.pop('peut_promouvoir_admin', True)
        super().__init__(*args, **kwargs)

        if not self._peut_promouvoir_admin:
            self.fields.pop('admin', None)

        if choix_entreprise:
            self.fields['entreprise_cible'] = forms.ModelChoiceField(
                queryset=Entreprise.objects.order_by('nom'),
                label='Entreprise',
                required=True,
                help_text='Sélectionnez l\'entreprise : les branches et rôles affichés correspondent à ce choix.',
            )
            if entreprise:
                self.fields['entreprise_cible'].initial = entreprise.pk
            w = self.fields['entreprise_cible'].widget
            w.attrs.setdefault('class', 'form-select')
            if htmx_entreprise_url:
                w.attrs.update({
                    'hx-post': htmx_entreprise_url,
                    'hx-trigger': 'change',
                    'hx-target': '#form-container',
                    'hx-swap': 'innerHTML',
                    'hx-include': 'closest form',
                    'hx-vals': '{"entreprise_refresh": "1"}',
                })

        eff = None
        if choix_entreprise:
            if self.is_bound and self.data.get('entreprise_cible'):
                eff = Entreprise.objects.filter(pk=self.data.get('entreprise_cible')).first()
            elif not self.is_bound and entreprise:
                eff = entreprise
        else:
            eff = entreprise

        if eff:
            self.fields['role'].queryset = Role.objects.filter(entreprise=eff).order_by('nom')
            self.fields['branche'].queryset = Branche.objects.filter(
                entreprise=eff, est_actif=True,
            ).order_by('nom')
        else:
            self.fields['role'].queryset = Role.objects.none()
            self.fields['branche'].queryset = Branche.objects.none()

        self.fields['is_active'].initial = True
        self.fields['is_active'].label = "Compte actif"
        if 'admin' in self.fields:
            self.fields['admin'].label = "Administrateur ERP"

    def clean(self):
        cleaned = super().clean()
        if self.choix_entreprise:
            eff = cleaned.get('entreprise_cible')
        else:
            eff = self._entreprise_fixe
        if not eff:
            if self.choix_entreprise:
                raise ValidationError({'entreprise_cible': 'Sélectionnez une entreprise.'})
            raise ValidationError("Impossible de déterminer l'entreprise cible.")
        branche = cleaned.get('branche')
        role = cleaned.get('role')
        if branche and branche.entreprise_id != eff.pk:
            self.add_error('branche', "Cette branche n'appartient pas à l'entreprise choisie.")
        if role and role.entreprise_id != eff.pk:
            self.add_error('role', "Ce rôle n'appartient pas à l'entreprise choisie.")
        return cleaned

    def clean_email(self):
        email = self.cleaned_data['email']
        if User.objects.filter(email=email).exists():
            raise ValidationError("Un compte avec cette adresse e-mail existe déjà.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data['email']
        if commit:
            user.save()
        return user


class ModificationUtilisateurForm(forms.ModelForm):
    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'email',
            'telephone', 'adresse', 'photo',
            'branche', 'role', 'admin', 'is_active',
        ]
        widgets = {
            'adresse': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, entreprise=None, choix_entreprise=False, htmx_entreprise_url='', **kwargs):
        self.choix_entreprise = choix_entreprise
        self._entreprise_fixe = entreprise
        self._peut_promouvoir_admin = kwargs.pop('peut_promouvoir_admin', True)
        super().__init__(*args, **kwargs)

        if not self._peut_promouvoir_admin:
            self.fields.pop('admin', None)

        if choix_entreprise:
            self.fields['entreprise_cible'] = forms.ModelChoiceField(
                queryset=Entreprise.objects.order_by('nom'),
                label='Entreprise',
                required=True,
                help_text='Les branches et rôles listés correspondent à cette entreprise.',
            )
            if entreprise:
                self.fields['entreprise_cible'].initial = entreprise.pk
            w = self.fields['entreprise_cible'].widget
            w.attrs.setdefault('class', 'form-select')
            if htmx_entreprise_url:
                w.attrs.update({
                    'hx-post': htmx_entreprise_url,
                    'hx-trigger': 'change',
                    'hx-target': '#form-container',
                    'hx-swap': 'innerHTML',
                    'hx-include': 'closest form',
                    'hx-vals': '{"entreprise_refresh": "1"}',
                })

        eff = None
        if choix_entreprise:
            if self.is_bound and self.data.get('entreprise_cible'):
                eff = Entreprise.objects.filter(pk=self.data.get('entreprise_cible')).first()
            elif not self.is_bound and entreprise:
                eff = entreprise
        else:
            eff = entreprise

        if eff:
            role_qs = Role.objects.filter(entreprise=eff).order_by('nom')
            if self.instance and self.instance.pk and self.instance.role_id:
                role_qs = (role_qs | Role.objects.filter(pk=self.instance.role_id)).distinct()
            self.fields['role'].queryset = role_qs
            self.fields['branche'].queryset = Branche.objects.filter(
                entreprise=eff, est_actif=True,
            ).order_by('nom')
        else:
            self.fields['role'].queryset = Role.objects.none()
            self.fields['branche'].queryset = Branche.objects.none()

        self.fields['is_active'].label = "Compte actif"
        if 'admin' in self.fields:
            self.fields['admin'].label = "Administrateur ERP"

    def clean(self):
        cleaned = super().clean()
        if self.choix_entreprise:
            eff = cleaned.get('entreprise_cible')
        else:
            eff = self._entreprise_fixe
        if not eff:
            if self.choix_entreprise:
                raise ValidationError({'entreprise_cible': 'Sélectionnez une entreprise.'})
            raise ValidationError("Impossible de déterminer l'entreprise cible.")
        branche = cleaned.get('branche')
        role = cleaned.get('role')
        if branche and branche.entreprise_id != eff.pk:
            self.add_error('branche', "Cette branche n'appartient pas à l'entreprise choisie.")
        if role and role.entreprise_id != eff.pk:
            self.add_error('role', "Ce rôle n'appartient pas à l'entreprise choisie.")
        return cleaned

    def clean_email(self):
        email = self.cleaned_data['email']
        qs = User.objects.filter(email=email).exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("Cette adresse e-mail est déjà utilisée.")
        return email


# ── Rôles & Permissions ────────────────────────────────────────────────────────

class RoleForm(forms.ModelForm):
    class Meta:
        model = Role
        fields = ['nom', 'description', 'famille_metier']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'famille_metier': forms.Select(
                attrs={'class': 'form-select'},
            ),
        }
        labels = {'famille_metier': 'Famille métier (accès types)'}
        help_texts = {
            'famille_metier': (
                "Optionnel : en enregistrant, remplace les permissions du rôle par le jeu associé "
                "à ce poste. Laissez vide pour conserver un rôle entièrement personnalisé."
            ),
        }

    def __init__(self, *args, show_entreprise=False, entreprise_fixe=None, **kwargs):
        """
        show_entreprise : True pour un admin ERP / superuser — champ « Entreprise » (toutes les entreprises).
        entreprise_fixe : utilisé pour la validation d'unicité (nom + entreprise) quand le champ n'est pas affiché.
        """
        self._entreprise_fixe = entreprise_fixe
        self._show_entreprise = show_entreprise
        super().__init__(*args, **kwargs)
        if show_entreprise:
            self.fields['entreprise'] = forms.ModelChoiceField(
                label='Entreprise',
                queryset=Entreprise.objects.order_by('nom'),
                required=True,
                help_text='Le rôle sera rattaché à cette entreprise (branches et utilisateurs associés).',
            )
            if self.instance.pk:
                self.fields['entreprise'].initial = self.instance.entreprise_id

    def clean(self):
        cleaned = super().clean()
        ent = cleaned.get('entreprise')
        if ent is None:
            ent = self._entreprise_fixe
        if ent is None and self.instance.pk:
            ent = self.instance.entreprise
        nom = (cleaned.get('nom') or '').strip()
        if ent and nom:
            qs = Role.objects.filter(entreprise=ent, nom__iexact=nom)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('nom', 'Un rôle avec ce nom existe déjà pour cette entreprise.')
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        if 'entreprise' in self.cleaned_data:
            instance.entreprise = self.cleaned_data['entreprise']
        elif self._entreprise_fixe is not None:
            instance.entreprise = self._entreprise_fixe
        if commit:
            instance.save()
            from .metiers import synchroniser_permissions_role
            fm = (self.cleaned_data.get('famille_metier') or '').strip()
            if fm:
                synchroniser_permissions_role(instance, fm, remplacer=True)
        return instance


class PermissionForm(forms.ModelForm):
    class Meta:
        model = PermissionPersonnalisee
        fields = ['code', 'nom']
        help_texts = {
            'code': "Identifiant unique en minuscules, ex : voir_finance, modifier_stock",
        }

    def clean_code(self):
        code = self.cleaned_data['code'].strip().lower().replace(' ', '_')
        qs = PermissionPersonnalisee.objects.filter(code=code)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("Ce code de permission existe déjà.")
        return code


class GererPermissionsRoleForm(forms.Form):
    """Formulaire pour assigner/retirer des permissions à un rôle."""
    permissions = forms.ModelMultipleChoiceField(
        queryset=PermissionPersonnalisee.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Permissions actives",
    )


# ── Accès Dépôts & Points de vente ───────────────────────────────────────────

class AccesDepotForm(forms.ModelForm):
    class Meta:
        model = AccesDepot
        fields = [
            'peut_voir', 'peut_recevoir',
            'peut_expedier', 'peut_inventorier', 'peut_administrer',
        ]
        widgets = {f: forms.CheckboxInput() for f in fields}


class AccesPointVenteForm(forms.ModelForm):
    class Meta:
        model = AccesPointVente
        fields = [
            'peut_voir', 'peut_vendre', 'peut_faire_avoir',
            'peut_remise', 'peut_gerer_caisse', 'peut_administrer',
        ]
        widgets = {f: forms.CheckboxInput() for f in fields}
