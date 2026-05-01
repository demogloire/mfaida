from decimal import Decimal

from django import forms
from django.db.models import Q

from entreprise.models import Depot, Location, PointVente, Produit

from stock.models import BonAjustementStock, Inventaire, MouvementOrigine, MouvementStock

from utilisateur.permissions import peut_voir_prix_achat_ht

# Même filtre périmètre que la liste stock (lots actifs + constats inventaire).
_Q_MOUV_VISIBLE_LISTE_STOCK = Q(quantite_active__gt=0) | Q(
    origine=MouvementOrigine.INVENTAIRE,
    inventaire__isnull=False,
)


class AjustementStockForm(forms.Form):
    """Ajustement sur une ligne MouvementStock existante (lot encore active). lieu: depot | pv."""

    mouvement_stock_id = forms.IntegerField(
        widget=forms.HiddenInput,
        label='',
        required=False,
    )
    depot = forms.ModelChoiceField(queryset=Depot.objects.none(), label='Dépôt')
    point_vente = forms.ModelChoiceField(
        queryset=PointVente.objects.none(),
        required=False,
        label='Point de vente',
        help_text='Stock affecté à ce point de vente.',
    )
    sens = forms.TypedChoiceField(
        label='Sens',
        coerce=int,
        choices=[(1, 'Entrée de stock'), (-1, 'Sortie de stock')],
    )
    quantite = forms.DecimalField(
        min_value=Decimal('0.01'),
        max_digits=15,
        decimal_places=2,
        label='Quantité',
    )
    motif = forms.CharField(label='Motif', widget=forms.Textarea(attrs={'rows': 2}))
    bon_ajustement_id = forms.IntegerField(required=False, widget=forms.HiddenInput, label='')
    reference_piece = forms.CharField(
        required=False,
        label="Numéro d'ajustement (pièce)",
        max_length=80,
        help_text='Référencera toutes les lignes du même dossier ; laissé vide : numéro auto (ADJ-…).',
    )
    prix_unitaire_ht = forms.DecimalField(
        required=False,
        max_digits=15,
        decimal_places=2,
        label="Prix d'achat unitaire (HT)",
        help_text="Pour la valorisation ; par défaut : prix sur la ligne, sinon prix du produit.",
    )

    def __init__(
        self, *args, user=None, entreprise=None, admin=False, lieu='depot', bon_actif=None, **kwargs
    ):
        super().__init__(*args, **kwargs)
        from stock.access import queryset_depots_visibles, queryset_points_vente_visibles

        self.bon_actif = bon_actif
        self.lieu = lieu or 'depot'
        depots = queryset_depots_visibles(user, entreprise, admin)

        if self.lieu == 'depot':
            self.fields['depot'].queryset = depots.order_by('nom')
            self.fields['depot'].required = True
            del self.fields['point_vente']
        elif self.lieu == 'pv':
            del self.fields['depot']
            pvs = queryset_points_vente_visibles(user, entreprise, admin).filter(depot_source__isnull=False)
            self.fields['point_vente'].queryset = pvs.order_by('nom')
            self.fields['point_vente'].required = True
            self.fields['point_vente'].help_text = 'Le stock est sur le dépôt source du PDV.'
        self.user = user
        self.entreprise = entreprise
        self.admin_flag = admin

        if bon_actif is not None:
            self.fields.pop('reference_piece', None)
            if self.lieu == 'depot' and bon_actif.depot_id:
                self.fields['depot'].widget = forms.HiddenInput()
                self.fields['depot'].initial = bon_actif.depot_id
            elif self.lieu == 'pv' and bon_actif.pointvente_id:
                self.fields['point_vente'].widget = forms.HiddenInput()
                self.fields['point_vente'].initial = bon_actif.pointvente_id

        if user is not None and not peut_voir_prix_achat_ht(user):
            self.fields.pop('prix_unitaire_ht', None)

    def clean(self):
        cleaned = super().clean()
        if self.lieu == 'pv':
            pv = cleaned.get('point_vente')
            if not pv or not pv.depot_source_id:
                raise forms.ValidationError('Choisissez un point de vente avec dépôt source.')
            cleaned['depot_effet'] = pv.depot_source
            cleaned['point_vente'] = pv
        else:
            dep = cleaned.get('depot')
            if not dep:
                raise forms.ValidationError('Choisissez un dépôt.')
            cleaned['depot_effet'] = dep
            cleaned['point_vente'] = None

        mid = cleaned.get('mouvement_stock_id')
        if mid in (None, ''):
            raise forms.ValidationError('Choisissez une ligne de stock via « Parcourir les lignes ».')
        sens = cleaned.get('sens')
        q = cleaned.get('quantite')

        qs = MouvementStock.objects.select_related('produit', 'depot', 'pointvente').filter(
            pk=mid,
            produit__entreprise=self.entreprise,
            quantite_active__gt=0,
        )
        if self.lieu == 'depot':
            qs = qs.filter(depot=cleaned['depot_effet'], pointvente__isnull=True)
        else:
            qs = qs.filter(pointvente=cleaned['point_vente'], depot=cleaned['depot_effet'])

        mv = qs.first()
        if not mv:
            raise forms.ValidationError('Ligne de stock invalide ou non disponible sur ce périmètre.')

        from stock.access import (
            peut_modifier_stock_au_depot,
            peut_modifier_stock_au_point_vente,
            utilisateur_est_admin,
        )

        adm = utilisateur_est_admin(self.user)
        if mv.pointvente_id:
            if not peut_modifier_stock_au_point_vente(self.user, mv.pointvente, adm):
                raise forms.ValidationError('Droits insuffisants sur cette ligne.')
        elif not peut_modifier_stock_au_depot(self.user, mv.depot, adm):
            raise forms.ValidationError('Droits insuffisants sur cette ligne.')

        if sens == -1 and q is not None:
            dispo = mv.quantite_active or Decimal('0')
            if q > dispo:
                raise forms.ValidationError(
                    f'Sortie impossible : disponible sur la ligne {dispo}, vous demandez {q}.'
                )

        bon_id = cleaned.get('bon_ajustement_id')
        if bon_id not in (None, ''):
            bon = BonAjustementStock.objects.filter(pk=int(bon_id), entreprise=self.entreprise).first()
            if not bon:
                raise forms.ValidationError("Bon d'ajustement introuvable.")
            dep_eff = cleaned['depot_effet']
            pv_eff = cleaned.get('point_vente')
            if self.lieu == 'depot':
                if bon.pointvente_id is not None or bon.depot_id != dep_eff.pk:
                    raise forms.ValidationError('Le lieu ne correspond pas à ce bon d’ajustement.')
            elif bon.pointvente_id != pv_eff.pk or bon.depot_id != dep_eff.pk:
                raise forms.ValidationError('Le lieu ne correspond pas à ce bon d’ajustement.')
            cleaned['bon'] = bon
        else:
            ref = (cleaned.get('reference_piece') or '').strip()
            if ref and BonAjustementStock.objects.filter(entreprise=self.entreprise, numero=ref).exists():
                raise forms.ValidationError('Ce numéro d’ajustement existe déjà pour votre entreprise.')
            cleaned['bon'] = None

        cleaned['mouvement_stock'] = mv
        cleaned['produit'] = mv.produit
        return cleaned


class MiseAEcartStockForm(forms.Form):
    """Mise à l'écart sur une ligne MouvementStock (quantité active > 0)."""

    mouvement_stock_id = forms.IntegerField(required=False, widget=forms.HiddenInput, label='')
    depot = forms.ModelChoiceField(queryset=Depot.objects.none(), label='Dépôt')
    point_vente = forms.ModelChoiceField(
        queryset=PointVente.objects.none(),
        required=False,
        label='Point de vente',
    )
    quantite = forms.DecimalField(
        min_value=Decimal('0.01'),
        max_digits=15,
        decimal_places=2,
        label="Quantité à mettre à l'écart",
    )
    motif = forms.CharField(
        label='Motif / raison',
        widget=forms.Textarea(attrs={'rows': 2}),
        min_length=3,
    )

    def __init__(self, *args, user=None, entreprise=None, admin=False, lieu='depot', **kwargs):
        super().__init__(*args, **kwargs)
        from stock.access import queryset_depots_visibles, queryset_points_vente_visibles

        self.user = user
        self.entreprise = entreprise
        self.admin_flag = admin
        self.lieu = lieu or 'depot'
        depots = queryset_depots_visibles(user, entreprise, admin)

        if self.lieu == 'depot':
            self.fields['depot'].queryset = depots.order_by('nom')
            self.fields['depot'].required = True
            del self.fields['point_vente']
        else:
            del self.fields['depot']
            pvs = queryset_points_vente_visibles(user, entreprise, admin).filter(depot_source__isnull=False)
            self.fields['point_vente'].queryset = pvs.order_by('nom')
            self.fields['point_vente'].required = True

    def clean(self):
        cleaned = super().clean()
        if self.lieu == 'pv':
            pv = cleaned.get('point_vente')
            if not pv or not pv.depot_source_id:
                raise forms.ValidationError('Choisissez un point de vente avec dépôt source.')
            cleaned['depot_effet'] = pv.depot_source
            cleaned['point_vente'] = pv
        else:
            dep = cleaned.get('depot')
            if not dep:
                raise forms.ValidationError('Choisissez un dépôt.')
            cleaned['depot_effet'] = dep
            cleaned['point_vente'] = None

        mid = cleaned.get('mouvement_stock_id')
        if mid in (None, ''):
            raise forms.ValidationError('Choisissez une ligne de lot via « Parcourir les lignes ».')

        qte = cleaned.get('quantite')

        qs = MouvementStock.objects.select_related('produit', 'depot', 'pointvente').filter(
            pk=mid,
            produit__entreprise=self.entreprise,
            quantite_active__gt=0,
        )
        if self.lieu == 'depot':
            qs = qs.filter(depot=cleaned['depot_effet'], pointvente__isnull=True)
        else:
            qs = qs.filter(pointvente=cleaned['point_vente'], depot=cleaned['depot_effet'])

        mv = qs.first()
        if not mv:
            raise forms.ValidationError('Ligne de stock invalide ou plus de quantité active sur ce périmètre.')

        from stock.access import (
            peut_modifier_stock_au_depot,
            peut_modifier_stock_au_point_vente,
            utilisateur_est_admin,
        )

        adm = utilisateur_est_admin(self.user)
        if mv.pointvente_id:
            if not peut_modifier_stock_au_point_vente(self.user, mv.pointvente, adm):
                raise forms.ValidationError('Droits insuffisants sur cette ligne.')
        elif not peut_modifier_stock_au_depot(self.user, mv.depot, adm):
            raise forms.ValidationError('Droits insuffisants sur cette ligne.')

        if qte is not None:
            dispo = mv.quantite_active or Decimal('0')
            if qte > dispo:
                raise forms.ValidationError(
                    f'Impossible : disponible sur la ligne {dispo}, vous demandez {qte}.'
                )

        cleaned['mouvement_stock'] = mv
        return cleaned


class CorrectionInterneLigneForm(forms.Form):
    """Correction des métadonnées d’une ligne de lot (sans modification des quantités)."""

    mouvement_stock_id = forms.IntegerField(required=False, widget=forms.HiddenInput, label='')
    depot = forms.ModelChoiceField(queryset=Depot.objects.none(), label='Dépôt')
    point_vente = forms.ModelChoiceField(
        queryset=PointVente.objects.none(),
        required=False,
        label='Point de vente',
    )
    lot_batch = forms.CharField(
        label='Lot / n° de lot',
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={'maxlength': 20}),
    )
    dateproduction = forms.DateField(
        label='Date de production',
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
    )
    dateexpiration = forms.DateField(
        label="Date d’expiration",
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
    )
    location = forms.ModelChoiceField(
        queryset=Location.objects.none(),
        required=False,
        label='Emplacement (référentiel)',
        help_text='Lieux de la branche du dépôt / du point de vente ; laisser vide pour n’utiliser que le code libre ci-dessous.',
    )
    location_code = forms.CharField(
        label='Code emplacement (libre)',
        max_length=20,
        required=False,
    )
    marque = forms.CharField(label='Marque', max_length=100, required=False)
    conditionnement = forms.CharField(
        label='Conditionnement',
        max_length=100,
        required=False,
        help_text='Ex. carton 12 pcs…',
    )
    motif = forms.CharField(
        label='Motif de la correction interne',
        widget=forms.Textarea(attrs={'rows': 2}),
        min_length=3,
    )

    def __init__(self, *args, user=None, entreprise=None, admin=False, lieu='depot', **kwargs):
        super().__init__(*args, **kwargs)
        from stock.access import queryset_depots_visibles, queryset_points_vente_visibles

        self.user = user
        self.entreprise = entreprise
        self.admin_flag = admin
        self.lieu = lieu or 'depot'
        depots = queryset_depots_visibles(user, entreprise, admin)

        dp = self.fields.get('dateproduction')
        de = self.fields.get('dateexpiration')
        for f in (dp, de):
            if f:
                f.input_formats = ['%Y-%m-%d']

        if self.lieu == 'depot':
            self.fields['depot'].queryset = depots.order_by('nom')
            self.fields['depot'].required = True
            del self.fields['point_vente']
            branche_ids = list(depots.values_list('branche_id', flat=True).distinct())
        else:
            del self.fields['depot']
            pvs = queryset_points_vente_visibles(user, entreprise, admin).filter(
                depot_source__isnull=False
            )
            self.fields['point_vente'].queryset = pvs.order_by('nom')
            self.fields['point_vente'].required = True
            branche_ids = list(pvs.values_list('branche_id', flat=True).distinct())

        loc_qs = Location.objects.filter(branche_id__in=branche_ids).order_by('code')
        if not branche_ids:
            loc_qs = Location.objects.none()
        self.fields['location'].queryset = loc_qs

    def clean(self):
        cleaned = super().clean()
        if self.lieu == 'pv':
            pv = cleaned.get('point_vente')
            if not pv or not pv.depot_source_id:
                raise forms.ValidationError('Choisissez un point de vente avec dépôt source.')
            cleaned['depot_effet'] = pv.depot_source
            cleaned['point_vente'] = pv
        else:
            dep = cleaned.get('depot')
            if not dep:
                raise forms.ValidationError('Choisissez un dépôt.')
            cleaned['depot_effet'] = dep
            cleaned['point_vente'] = None

        mid = cleaned.get('mouvement_stock_id')
        if mid in (None, ''):
            raise forms.ValidationError('Choisissez une ligne de lot via « Choisir une ligne ».')

        loc = cleaned.get('location')
        if loc and not self.fields['location'].queryset.filter(pk=loc.pk).exists():
            raise forms.ValidationError('Emplacement invalide pour ce périmètre.')

        qs = MouvementStock.objects.select_related('produit', 'depot', 'pointvente').filter(
            pk=mid,
            produit__entreprise=self.entreprise,
        ).filter(_Q_MOUV_VISIBLE_LISTE_STOCK)
        if self.lieu == 'depot':
            qs = qs.filter(depot=cleaned['depot_effet'], pointvente__isnull=True)
        else:
            qs = qs.filter(pointvente=cleaned['point_vente'], depot=cleaned['depot_effet'])

        mv = qs.first()
        if not mv:
            raise forms.ValidationError(
                'Ligne invalide ou hors périmètre (seules les lignes visibles en stock / constat inventaire).'
            )

        from stock.access import (
            peut_modifier_stock_au_depot,
            peut_modifier_stock_au_point_vente,
            utilisateur_est_admin,
        )

        adm = utilisateur_est_admin(self.user)
        if mv.pointvente_id:
            if not peut_modifier_stock_au_point_vente(self.user, mv.pointvente, adm):
                raise forms.ValidationError('Droits insuffisants sur cette ligne.')
        elif not peut_modifier_stock_au_depot(self.user, mv.depot, adm):
            raise forms.ValidationError('Droits insuffisants sur cette ligne.')

        dp = cleaned.get('dateproduction')
        de = cleaned.get('dateexpiration')
        if dp and de and de < dp:
            raise forms.ValidationError(
                'La date d’expiration doit être égale ou postérieure à la date de production.'
            )

        cleaned['mouvement_stock'] = mv
        return cleaned


class InventaireCreerForm(forms.ModelForm):
    class Meta:
        model = Inventaire
        fields = ('depot', 'pointdevente', 'date_inventaire')
        widgets = {
            'date_inventaire': forms.DateInput(
                attrs={
                    'type': 'date',
                    'class': 'form-control',
                },
                format='%Y-%m-%d',
            ),
        }

    def __init__(self, *args, user=None, entreprise=None, admin=False, lieu='depot', **kwargs):
        super().__init__(*args, **kwargs)
        from stock.access import queryset_depots_visibles, queryset_points_vente_visibles

        self.lieu = lieu or 'depot'

        df = self.fields.get('date_inventaire')
        if df:
            df.input_formats = ['%Y-%m-%d']

        if self.lieu == 'depot':
            depots = queryset_depots_visibles(user, entreprise, admin)
            self.fields['depot'].queryset = depots.order_by('nom')
            self.fields['depot'].required = True
            del self.fields['pointdevente']
        else:
            del self.fields['depot']
            self.fields['pointdevente'].queryset = (
                queryset_points_vente_visibles(user, entreprise, admin)
                .filter(depot_source__isnull=False)
                .order_by('nom')
            )
            self.fields['pointdevente'].required = True

    def clean(self):
        d = super().clean()
        if self.lieu == 'depot':
            if not d.get('depot'):
                raise forms.ValidationError('Choisissez un dépôt.')
            return d
        if not d.get('pointdevente'):
            raise forms.ValidationError('Choisissez un point de vente.')
        return d


class LigneInventaireAjoutForm(forms.Form):
    produit = forms.ModelChoiceField(queryset=Produit.objects.none())
    quantite_physique = forms.DecimalField(min_value=Decimal('0'), max_digits=15, decimal_places=2)

    def __init__(self, *args, entreprise=None, **kwargs):
        super().__init__(*args, **kwargs)
        if entreprise:
            self.fields['produit'].queryset = Produit.objects.filter(
                entreprise=entreprise, est_actif=True
            ).order_by('nom')
