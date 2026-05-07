from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Exists, OuterRef

from entreprise.models import Branche, PointVente, Devise, Produit
from facturation.models import Facture, FactureProforma
from tiers.models import Client
from stock.access import queryset_points_vente_pour_vente
from stock.models import MouvementStock


def label_client_facture(c: Client) -> str:
    """Libellé court pour liste / autocomplete facturation."""
    tag = ' · Passager' if getattr(c, 'est_client_passager', False) else ''
    tel = (c.telephone or '').strip()
    parts = [c.nom, (c.code_client or '').strip()]
    if tel:
        parts.append(tel)
    return ' — '.join(p for p in parts if p) + tag


class FactureBrouillonForm(forms.ModelForm):
    """Brouillon : client choisi via autocomplétion (liste des clients actifs entreprise)."""

    client_selection = forms.TypedChoiceField(
        coerce=int,
        label='Client',
        required=True,
        help_text='Tapez quelques lettres ou le code client : suggestions parmi les clients enregistrés.',
    )

    class Meta:
        model = Facture
        fields = (
            'point_vente',
            'client_selection',
            'devise',
            'taux_echange_appliqué',
            'mode_paiement',
        )
        labels = {'point_vente': 'Point de vente'}

    def __init__(self, *args, entreprise=None, user=None, admin=False, **kwargs):
        self._entreprise = entreprise
        self._user = user
        self._admin = admin
        super().__init__(*args, **kwargs)

        sel = forms.Select(
            attrs={
                'class': 'form-select',
                'id': 'id_client_selection',
            }
        )
        self.fields['client_selection'].widget = sel

        choices = [
            ('', '— Rechercher un client (nom, code ou téléphone) —'),
        ]

        cid = None
        if self.is_bound:
            raw = (self.data.get('client_selection') or '').strip()
            if raw.isdigit():
                cid = int(raw)

        if cid is not None:
            c = Client.objects.filter(pk=cid, est_actif=True).select_related('entreprise').first()
            if c:
                ok = not entreprise or c.entreprise_id == entreprise.pk
                if ok:
                    choices.append((str(c.pk), label_client_facture(c)))

        self.fields['client_selection'].choices = choices

        u = user
        if u is None or not getattr(u, 'is_authenticated', False):
            self.fields['point_vente'].queryset = PointVente.objects.none()
        elif entreprise:
            self.fields['point_vente'].queryset = queryset_points_vente_pour_vente(
                u, entreprise, admin
            )
            self.fields['devise'].queryset = Devise.objects.filter(entreprise=entreprise).order_by('code')
        else:
            self.fields['point_vente'].queryset = queryset_points_vente_pour_vente(u, None, admin)
            self.fields['devise'].queryset = Devise.objects.all().order_by('code')

        fx = self.fields['taux_echange_appliqué']
        fx.widget.attrs['readonly'] = 'readonly'
        fx.widget.attrs['tabindex'] = '-1'
        fx.help_text = (
            'Taux pris automatiquement sur la devise sélectionnée ; non modifiable sur cet écran.'
        )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('devise') is not None:
            cleaned['taux_echange_appliqué'] = Decimal(str(cleaned['devise'].taux_echange))
        return cleaned

    def clean_client_selection(self):
        cid = self.cleaned_data['client_selection']
        qs = Client.objects.filter(pk=cid, est_actif=True)
        if self._entreprise:
            qs = qs.filter(entreprise=self._entreprise)
        if not qs.exists():
            raise ValidationError('Ce client est introuvable ou inactif pour votre périmètre.')
        return cid


def point_vente_nouvelle_facture_queryset(entreprise, user, admin):
    """Même périmètre que le choix PV sur `FactureBrouillonForm` (ventes = droit peut_vendre)."""
    return queryset_points_vente_pour_vente(user, entreprise, admin)


class ClientRapideFactureForm(forms.Form):
    """Création minimale d’un client depuis l’écran nouvelle facture (branche = PV choisi)."""

    point_vente_id = forms.IntegerField(min_value=1, label='Point de vente')
    nom = forms.CharField(
        max_length=255,
        min_length=2,
        label='Nom ou raison sociale',
    )
    telephone = forms.CharField(max_length=20, label='Téléphone')
    email = forms.EmailField(required=False, label='E-mail')
    est_client_passager = forms.BooleanField(
        required=False,
        initial=True,
        label='Client passager / comptoir',
    )

    def clean_nom(self):
        n = (self.cleaned_data.get('nom') or '').strip()
        if len(n) < 2:
            raise ValidationError('Au moins 2 caractères.')
        return n

    def clean_telephone(self):
        t = (self.cleaned_data.get('telephone') or '').strip()
        if not t:
            raise ValidationError('Ce champ est obligatoire.')
        return t


def label_produit_facture(p: Produit) -> str:
    """Libellé produit pour Select2 facturation."""
    nom = (p.nom or '').strip()
    sku = (p.sku or '').strip()
    sku_part = f'SKU {sku}' if sku else ''
    cb = (p.code_barre or '').strip()
    parts = [nom, sku_part]
    if cb:
        parts.append(cb)
    return ' — '.join(x for x in parts if x) or str(p.pk)


def queryset_produits_facture_pv(point_vente):
    """Produits avec stock actif sur le point de vente (même périmètre que la répartition lots)."""
    if not point_vente or not point_vente.depot_source_id:
        return Produit.objects.none()
    mouv_exists = MouvementStock.objects.filter(
        produit_id=OuterRef('pk'),
        depot_id=point_vente.depot_source_id,
        pointvente_id=point_vente.pk,
        quantite_active__gt=0,
    )
    return (
        Produit.objects.filter(
            entreprise_id=point_vente.branche.entreprise_id,
            est_actif=True,
        )
        .annotate(_dispo=Exists(mouv_exists))
        .filter(_dispo=True)
        .order_by('nom')
    )


# ─────────────────────────────────────────────
# Formulaires Facture Proforma
# ─────────────────────────────────────────────

class ProformaEnteteForm(forms.ModelForm):
    """
    Entête d'une facture proforma.
    - Utilisateur normal (branche_forcee renseignée) : branche fixée, champ masqué.
    - Admin / approuveur (branche_forcee=None) : libre choix de la branche.
    """

    client_selection = forms.TypedChoiceField(
        coerce=int,
        label='Client',
        required=True,
        help_text='Tapez quelques lettres ou le code client pour rechercher.',
    )

    class Meta:
        model = FactureProforma
        fields = ('branche', 'client_selection', 'devise', 'date_validite')
        widgets = {
            'date_validite': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        }
        labels = {
            'branche': 'Branche',
            'date_validite': 'Date de validité',
        }

    def __init__(self, *args, entreprise=None, user=None, admin=False, branche_forcee=None, **kwargs):
        self._entreprise = entreprise
        self._user = user
        self._admin = admin
        self._branche_forcee = branche_forcee
        super().__init__(*args, **kwargs)

        sel = forms.Select(attrs={'class': 'form-select', 'id': 'id_client_selection_proforma'})
        self.fields['client_selection'].widget = sel

        choices = [('', '— Rechercher un client (nom, code ou téléphone) —')]
        cid = None
        if self.is_bound:
            raw = (self.data.get('client_selection') or '').strip()
            if raw.isdigit():
                cid = int(raw)
        if cid is not None:
            c = Client.objects.filter(pk=cid, est_actif=True).first()
            if c:
                ok = not entreprise or c.entreprise_id == entreprise.pk
                if ok:
                    choices.append((str(c.pk), label_client_facture(c)))
        self.fields['client_selection'].choices = choices

        # ── Branche ──────────────────────────────────────────────────────────
        if branche_forcee:
            # Branche verrouillée à celle de l'utilisateur
            self.fields['branche'].queryset = Branche.objects.filter(pk=branche_forcee.pk)
            self.fields['branche'].initial = branche_forcee.pk
            self.fields['branche'].widget = forms.HiddenInput()
            self.fields['branche'].label = ''
        elif entreprise:
            self.fields['branche'].queryset = Branche.objects.filter(
                entreprise=entreprise
            ).order_by('nom')
        elif admin:
            self.fields['branche'].queryset = Branche.objects.all().order_by('nom')
        else:
            self.fields['branche'].queryset = Branche.objects.none()

        # ── Devise ───────────────────────────────────────────────────────────
        if entreprise:
            self.fields['devise'].queryset = Devise.objects.filter(
                entreprise=entreprise
            ).order_by('code')
        elif admin:
            self.fields['devise'].queryset = Devise.objects.all().order_by('code')
        else:
            self.fields['devise'].queryset = Devise.objects.none()

    def clean_branche(self):
        branche = self.cleaned_data.get('branche')
        if self._branche_forcee:
            # Toujours imposer la branche de l'utilisateur, même si quelqu'un falsifie le POST
            return self._branche_forcee
        return branche

    def clean_client_selection(self):
        cid = self.cleaned_data['client_selection']
        qs = Client.objects.filter(pk=cid, est_actif=True)
        if self._entreprise:
            qs = qs.filter(entreprise=self._entreprise)
        if not qs.exists():
            raise ValidationError('Ce client est introuvable ou inactif.')
        return cid


class LigneProformaForm(forms.Form):
    """Ligne proforma : produit + quantité + prix négocié + remise optionnelle."""

    produit_selection = forms.TypedChoiceField(
        coerce=int,
        label='Produit',
        required=True,
        help_text='Tapez le nom, le SKU ou le code-barres (au moins 2 caractères).',
    )
    quantite = forms.DecimalField(
        min_value=Decimal('0.01'),
        max_digits=15,
        decimal_places=2,
        label='Quantité',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0', 'step': '0.01'}),
    )
    prix_unitaire_ht = forms.DecimalField(
        min_value=Decimal('0'),
        max_digits=15,
        decimal_places=2,
        required=False,
        label='Prix HT unitaire',
        help_text='Laissez vide pour reprendre le prix catalogue.',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Prix catalogue', 'step': '0.01'}),
    )
    remise = forms.DecimalField(
        min_value=Decimal('0'),
        max_digits=15,
        decimal_places=2,
        required=False,
        initial=Decimal('0'),
        label='Remise (montant HT)',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0', 'step': '0.01'}),
    )

    def __init__(self, *args, entreprise=None, **kwargs):
        self._entreprise = entreprise
        super().__init__(*args, **kwargs)

        sel = forms.Select(attrs={'class': 'form-select', 'id': 'id_produit_selection_proforma'})
        self.fields['produit_selection'].widget = sel

        choices = [('', '— Rechercher un produit —')]
        if self.is_bound:
            raw = (self.data.get('produit_selection') or '').strip()
            if raw.isdigit():
                qs = Produit.objects.filter(pk=int(raw), est_actif=True)
                if entreprise:
                    qs = qs.filter(entreprise=entreprise)
                p = qs.first()
                if p:
                    choices.append((str(p.pk), label_produit_facture(p)))
        self.fields['produit_selection'].choices = choices

    def clean(self):
        cleaned = super().clean()
        if self.errors:
            return cleaned
        pid = cleaned.get('produit_selection')
        if pid is None:
            return cleaned
        # Toujours restreindre au catalogue de l'entreprise de la proforma
        qs = Produit.objects.filter(pk=pid, est_actif=True)
        if self._entreprise:
            qs = qs.filter(entreprise=self._entreprise)
        p = qs.first()
        if not p:
            self.add_error('produit_selection', 'Produit introuvable ou hors catalogue de cette entreprise.')
            return cleaned
        cleaned['produit'] = p
        if not cleaned.get('prix_unitaire_ht'):
            cleaned['prix_unitaire_ht'] = Decimal(str(p.prix_vente_ht))
        if not cleaned.get('remise'):
            cleaned['remise'] = Decimal('0')
        return cleaned


class DecisionProformaForm(forms.Form):
    """Formulaire de décision manager : commentaire optionnel."""

    commentaire_manager = forms.CharField(
        required=False,
        label='Commentaire (optionnel)',
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Motif de rejet ou note d\'approbation…',
        }),
    )


# ─────────────────────────────────────────────
# Formulaires Ajout Ligne Facture (existant)
# ─────────────────────────────────────────────

class AjoutLigneFactureForm(forms.Form):
    """
    Produit via autocomplétion ; quantité. Prix catalogue et lots (FIFO/FEFO/LIFO) côté serveur.
    """

    produit_selection = forms.TypedChoiceField(
        coerce=int,
        label='Produit',
        required=True,
        help_text='Tapez le nom, le SKU ou le code-barres (au moins 2 caractères).',
    )
    quantite = forms.DecimalField(
        min_value=Decimal('0.01'),
        max_digits=15,
        decimal_places=2,
        label='Quantité',
    )

    def __init__(self, *args, point_vente=None, **kwargs):
        self._point_vente = point_vente
        self._produit_qs = queryset_produits_facture_pv(point_vente)
        super().__init__(*args, **kwargs)

        sel = forms.Select(attrs={'class': 'form-select', 'id': 'id_produit_selection'})
        self.fields['produit_selection'].widget = sel

        choices = [
            ('', '— Rechercher un produit (nom, SKU, code-barres) —'),
        ]
        if self.is_bound:
            raw = (self.data.get('produit_selection') or '').strip()
            if raw.isdigit():
                p = self._produit_qs.filter(pk=int(raw)).first()
                if p:
                    choices.append((str(p.pk), label_produit_facture(p)))
        self.fields['produit_selection'].choices = choices

    def clean(self):
        cleaned = super().clean()
        if self.errors:
            return cleaned
        pid = cleaned.get('produit_selection')
        if pid is None:
            return cleaned
        p = self._produit_qs.filter(pk=pid).first()
        if not p:
            self.add_error(
                'produit_selection',
                'Produit introuvable ou sans stock disponible sur ce point de vente.',
            )
            return cleaned
        cleaned['produit'] = p
        return cleaned
