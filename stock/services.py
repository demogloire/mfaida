"""Mise à jour du stock agrégé et mouvements (ajustement, inventaire, ventes)."""

from decimal import Decimal

from django.db import transaction
from django.db.models import Case, IntegerField, Sum, Value, When

from stock.models import (
    BonAjustementStock,
    Inventaire,
    LigneBonAjustement,
    MouvementOrigine,
    MouvementStock,
    Stock,
    StockMiseAEcart,
)
def ajuster_stock_agrege(produit_id, depot_id, pointdevente_id, delta_qte, minimum_zero=True):
    """Applique un delta à la ligne Stock. pointdevente_id peut être None (stock dépôt seul)."""
    delta_qte = Decimal(str(delta_qte))
    if delta_qte == 0:
        return
    with transaction.atomic():
        row, _ = Stock.objects.select_for_update().get_or_create(
            produit_id=produit_id,
            depot_id=depot_id,
            pointdevente_id=pointdevente_id,
            defaults={'quantite_reelle': Decimal('0')},
        )
        nouveau = (row.quantite_reelle or Decimal('0')) + delta_qte
        if minimum_zero and nouveau < 0:
            raise ValueError('Stock insuffisant sur ce dépôt / point de vente.')
        row.quantite_reelle = nouveau
        row.save(update_fields=['quantite_reelle', 'derniere_mise_a_jour'])


def theorique_produit_lieu(produit_id, depot, pointvente):
    """
    « Théorique » inventaire : somme des quantités actives par lot (disponible réel au SKU,
    dépôt ou point de vente). Même périmètre que la consommation déficit (FIFO / FEFO / LIFO).

    L’agrégat Stock.quantite_reelle peut différer (ex. quantité reçue mise à l’écart, historique) ;
    l’inventaire s’aligne donc sur ce qui est encore sortable sur mouvements.
    """
    qs = MouvementStock.objects.filter(produit_id=produit_id, depot_id=depot.pk)
    if pointvente:
        qs = qs.filter(pointvente_id=pointvente.pk)
    else:
        qs = qs.filter(pointvente__isnull=True)
    agg = qs.aggregate(s=Sum('quantite_active'))
    val = agg.get('s')
    return val if val is not None else Decimal('0')


def enregistrer_ajustement_sur_ligne(
    *,
    utilisateur,
    mouvement_stock_id,
    sens,
    quantite,
    motif,
    reference_piece,
    prix_unitaire=None,
    bon: BonAjustementStock | None = None,
):
    """
    Entrée / sortie sur une ligne MouvementStock existante (lot) avec qté active > 0 dans le périmètre.
    Sync Stock agrégé comme pour les ventes (sortie) ou augmentations cohérentes (entrée).
    sens: +1 entrée, -1 sortie (ne peut pas excéder quantite_active du lot au moment du lock).
    """
    from stock.access import (
        peut_modifier_stock_au_depot,
        peut_modifier_stock_au_point_vente,
        utilisateur_est_admin,
    )

    q = Decimal(str(quantite))
    if q <= 0:
        raise ValueError('La quantité doit être strictement positive.')
    admin = utilisateur_est_admin(utilisateur)

    motif = (motif or '').strip()
    reference_piece = (reference_piece or '')[:80]

    with transaction.atomic():
        mv = (
            MouvementStock.objects.select_for_update()
            .select_related('produit', 'depot', 'pointvente')
            .get(pk=mouvement_stock_id)
        )
        pv_obj = mv.pointvente_id and mv.pointvente
        if pv_obj:
            if not peut_modifier_stock_au_point_vente(utilisateur, pv_obj, admin):
                raise ValueError('Droits insuffisants pour ajuster ce point de vente.')
        else:
            if not peut_modifier_stock_au_depot(utilisateur, mv.depot, admin):
                raise ValueError('Droits insuffisants pour ajuster ce dépôt.')

        depot_id = mv.depot_id
        pv_id = mv.pointvente_id if mv.pointvente_id else None
        prod_id = mv.produit_id

        pu = prix_unitaire
        if pu is None:
            pu = mv.prix_unitaire if mv.prix_unitaire else None
        if pu is None or pu == '':
            pu = mv.produit.prix_achat_ht or Decimal('0')
        else:
            pu = Decimal(str(pu))

        act = mv.quantite_active or Decimal('0')
        recv = mv.quantite_recu or Decimal('0')

        if sens == -1:
            if act < q:
                raise ValueError(
                    f'Quantité disponible sur cette ligne : {act} (vous demandez {q}).'
                )
            mv.quantite_active = act - q
            mv.save(update_fields=['quantite_active'])
            ajuster_stock_agrege(prod_id, depot_id, pv_id, -q)
        elif sens == 1:
            mv.quantite_recu = recv + q
            mv.quantite_active = act + q
            mv.save(update_fields=['quantite_recu', 'quantite_active'])
            ajuster_stock_agrege(prod_id, depot_id, pv_id, q)
        else:
            raise ValueError('Sens invalide.')

        ligne_trace = None
        if bon is not None:
            ligne_trace = LigneBonAjustement.objects.create(
                bon=bon,
                mouvement_stock=mv,
                sens=sens,
                quantite=q,
                prix_unitaire_ht=pu,
                motif=motif,
            )

    return mv, pu, ligne_trace


def _appliquer_deficit_inventaire_sur_lots(
    *,
    produit_id: int,
    methode_gestion: str | None,
    pv_stock,
    q_sortie: Decimal,
    depot_id,
    pv_id,
) -> None:
    """
    Déficit physique (physique < disponible lots) : retire q_sortie sur les lots encore actifs,
    dans l’ordre FIFO / FEFO / LIFO. Chaque tranche décrémente l’agrégé Stock (−chunk).
    Une ligne MouvementStock « constat » avec la quantité physique est créée par l’appelant.
    """
    q_sortie = Decimal(str(q_sortie))
    if q_sortie <= 0:
        return

    methode = (methode_gestion or 'FEFO').strip().upper()
    if methode not in ('FIFO', 'FEFO', 'LIFO'):
        methode = 'FEFO'

    qs = (
        MouvementStock.objects.select_for_update()
        .filter(
            produit_id=produit_id,
            depot_id=depot_id,
            quantite_active__gt=0,
        )
    )
    if pv_stock:
        qs = qs.filter(pointvente_id=pv_id)
    else:
        qs = qs.filter(pointvente__isnull=True)

    if methode == 'LIFO':
        qs = qs.order_by('-date_creation', '-pk')
    elif methode == 'FIFO':
        qs = qs.order_by('date_creation', 'pk')
    else:
        qs = qs.annotate(
            _fefo_null_last=Case(
                When(dateexpiration__isnull=True, then=Value(1)),
                default=Value(0),
                output_field=IntegerField(),
            ),
        ).order_by('_fefo_null_last', 'dateexpiration', 'date_creation', 'pk')

    mvs = list(qs)
    remaining = q_sortie
    for mv in mvs:
        if remaining <= 0:
            break
        act = mv.quantite_active or Decimal('0')
        if act <= 0:
            continue
        chunk = min(act, remaining)
        mv.quantite_active = act - chunk
        mv.save(update_fields=['quantite_active'])
        ajuster_stock_agrege(produit_id, depot_id, pv_id, -chunk)
        remaining -= chunk

    if remaining > Decimal('0.000001'):
        raise ValueError(
            f'Inventaire : il reste {remaining} unité(s) à sortir alors que '
            'le stock disponible par lot est insuffisant (méthode ' + methode + ').'
        )


def appliquer_ecarts_inventaire(inventaire: Inventaire, utilisateur):
    """
    Clôture : compare la quantité physique à la disponibilité par lots (somme des qtés actives),
    aligne l’agrégé Stock et enregistre des lignes Inventaire avec la quantité physique constatée
    (entrée Δ sur excédent ; sortie FIFO/FEFO/LIFO sur manquant + ligne constat physique active = 0).
    """
    from stock.access import (
        peut_modifier_stock_au_depot,
        peut_modifier_stock_au_point_vente,
        utilisateur_est_admin,
    )

    admin = utilisateur_est_admin(utilisateur)
    lieu_depot = inventaire.depot_id
    lieu_pv = inventaire.pointdevente_id

    pv_obj = inventaire.pointdevente if lieu_pv else None
    depot_obj = inventaire.depot if lieu_depot else None
    if bool(lieu_depot) ^ bool(lieu_pv):
        pass
    else:
        raise ValueError('Choisissez exactement un dépôt OU un point de vente.')

    if pv_obj:
        if not pv_obj.depot_source_id:
            raise ValueError("Ce point de vente n'a pas de dépôt source.")
        depot_cible = pv_obj.depot_source
        pv_stock = pv_obj
        if not peut_modifier_stock_au_point_vente(utilisateur, pv_obj, admin):
            raise ValueError('Droits insuffisants sur ce point de vente.')
    else:
        depot_cible = depot_obj
        pv_stock = None
        if not peut_modifier_stock_au_depot(utilisateur, depot_cible, admin):
            raise ValueError('Droits insuffisants sur ce dépôt.')

    lignes = list(inventaire.lignes.select_related('produit').all())
    montant_augment_val = Decimal('0')
    montant_dimin_val = Decimal('0')

    with transaction.atomic():
        locked = Inventaire.objects.select_for_update().get(pk=inventaire.pk)
        if locked.cloture:
            raise ValueError('Cet inventaire est déjà clôturé.')
        depot_id = depot_cible.pk
        pv_id = pv_stock.pk if pv_stock else None

        for li in lignes:
            theor = theorique_produit_lieu(li.produit_id, depot_cible, pv_stock)
            phys = Decimal(str(li.quantite_physique))
            li.quantite_theorique = theor
            ecart = phys - theor

            pu = li.produit.prix_achat_ht or Decimal('0')
            if ecart != 0:
                v = abs(ecart) * Decimal(str(pu))
                if ecart > 0:
                    montant_augment_val += v
                else:
                    montant_dimin_val += v

            li.save(update_fields=['quantite_theorique'])

            if ecart == 0:
                continue

            if ecart > 0:
                ajuster_stock_agrege(li.produit_id, depot_id, pv_id, ecart)
                MouvementStock.objects.create(
                    produit_id=li.produit_id,
                    depot=depot_cible,
                    pointvente=pv_stock,
                    quantite_recu=phys,
                    quantite_ecarter=Decimal('0'),
                    quantite_affectee=Decimal('0'),
                    quantite_active=ecart,
                    prix_unitaire=pu,
                    origine=MouvementOrigine.INVENTAIRE,
                    motif=(
                        f"Écart inventaire {locked.lot or locked.pk} / ligne #{li.pk} : "
                        f"physique={phys}, dispo. avant clôture={theor}, entrée nette Δ={ecart}."
                    ),
                    reference_piece=(locked.lot or '')[:80],
                    inventaire=locked,
                    effectue_par=utilisateur,
                )
            else:
                q_abs = abs(ecart)
                _appliquer_deficit_inventaire_sur_lots(
                    produit_id=li.produit_id,
                    methode_gestion=getattr(li.produit, 'methode_gestion', None),
                    pv_stock=pv_stock,
                    q_sortie=q_abs,
                    depot_id=depot_id,
                    pv_id=pv_id,
                )
                MouvementStock.objects.create(
                    produit_id=li.produit_id,
                    depot=depot_cible,
                    pointvente=pv_stock,
                    quantite_recu=phys,
                    quantite_ecarter=Decimal('0'),
                    quantite_affectee=Decimal('0'),
                    quantite_active=Decimal('0'),
                    prix_unitaire=pu,
                    origine=MouvementOrigine.INVENTAIRE,
                    motif=(
                        f"Constat inventaire {locked.lot or locked.pk} / ligne #{li.pk} : "
                        f"physique={phys}, dispo. avant clôture={theor}, sortie des lots Δ=−{q_abs} "
                        f"({getattr(li.produit, 'methode_gestion', None) or 'FEFO'})."
                    ),
                    reference_piece=(locked.lot or '')[:80],
                    inventaire=locked,
                    effectue_par=utilisateur,
                )

        locked.cloture = True
        locked.valide_par = utilisateur
        locked.save(update_fields=['cloture', 'valide_par'])

    return montant_augment_val, montant_dimin_val


def consommer_mouvements_facture(facture, utilisateur):
    """Validation facture : consomme la quantité active sur chaque mouvement cité."""
    lignes_qs = facture.lignes.select_related('mouvement_stock', 'produit')
    montant_cos = Decimal('0')
    with transaction.atomic():
        for lig in lignes_qs:
            mv = MouvementStock.objects.select_for_update().get(pk=lig.mouvement_stock_id)
            q = Decimal(str(lig.quantite))
            if mv.quantite_active < q:
                raise ValueError(
                    f"Mouvement #{mv.pk} : quantité active insuffisante pour '{lig.produit.nom}'."
                )
            cout = Decimal(str(lig.quantite)) * Decimal(str(mv.prix_unitaire or '0'))
            montant_cos += cout
            mv.quantite_active -= q
            mv.quantite_affectee += q
            mv.save(update_fields=['quantite_active', 'quantite_affectee'])

            depot_id = mv.depot_id
            pv_id = mv.pointvente_id if mv.pointvente_id else None
            ajuster_stock_agrege(lig.produit_id, depot_id, pv_id, -q)

    return montant_cos


def total_mise_a_ecart_actif(produit_id, depot_id, pointdevente_id):
    qs = StockMiseAEcart.objects.filter(
        produit_id=produit_id,
        depot_id=depot_id,
        actif=True,
    )
    if pointdevente_id:
        qs = qs.filter(pointdevente_id=pointdevente_id)
    else:
        qs = qs.filter(pointdevente__isnull=True)
    r = qs.aggregate(s=Sum('quantite'))
    return r['s'] or Decimal('0')


def enregistrer_mise_a_ecart_stock(
    utilisateur,
    *,
    entreprise,
    mouvement_stock_id,
    quantite,
    motif,
):
    """Retire qté du disponible du lot : active −, quantite_ecarter + ; enregistre StockMiseAEcart liée à la ligne."""
    from stock.access import (
        peut_modifier_stock_au_depot,
        peut_modifier_stock_au_point_vente,
        utilisateur_est_admin,
    )

    admin = utilisateur_est_admin(utilisateur)
    q = Decimal(str(quantite))
    if q <= 0:
        raise ValueError('Quantité invalide.')
    motif = (motif or '').strip()
    if len(motif) < 3:
        raise ValueError('Motif trop court.')

    with transaction.atomic():
        mv = (
            MouvementStock.objects.select_for_update()
            .select_related('produit', 'depot', 'pointvente')
            .get(pk=mouvement_stock_id, produit__entreprise=entreprise)
        )
        pv_obj = mv.pointvente_id and mv.pointvente
        if pv_obj:
            if not peut_modifier_stock_au_point_vente(utilisateur, pv_obj, admin):
                raise ValueError('Droits insuffisants pour ce point de vente.')
        else:
            if not peut_modifier_stock_au_depot(utilisateur, mv.depot, admin):
                raise ValueError('Droits insuffisants pour ce dépôt.')

        act = mv.quantite_active or Decimal('0')
        if q > act:
            raise ValueError(
                f'Disponible sur cette ligne : {act}. Impossible de mettre {q} à l’écart.'
            )

        mv.quantite_active = act - q
        mv.quantite_ecarter = (mv.quantite_ecarter or Decimal('0')) + q
        mv.save(update_fields=['quantite_active', 'quantite_ecarter'])

        StockMiseAEcart.objects.create(
            produit_id=mv.produit_id,
            mouvement_stock=mv,
            depot=mv.depot,
            pointdevente=mv.pointvente,
            quantite=q,
            motif=motif,
            cree_par=utilisateur,
        )


def retirer_mise_a_ecart_stock(utilisateur, mise_pk, entreprise):
    """Désactive la mise ; restaure active / quantite_ecarter sur la ligne de lot si elle est encore liée."""
    from stock.access import (
        peut_modifier_stock_au_depot,
        peut_modifier_stock_au_point_vente,
        utilisateur_est_admin,
    )

    admin = utilisateur_est_admin(utilisateur)

    with transaction.atomic():
        mi = (
            StockMiseAEcart.objects.select_for_update()
            .select_related('depot', 'pointdevente', 'mouvement_stock')
            .get(pk=mise_pk, actif=True, produit__entreprise=entreprise)
        )
        if mi.pointdevente_id:
            if not peut_modifier_stock_au_point_vente(utilisateur, mi.pointdevente, admin):
                raise ValueError('Droits insuffisants.')
        else:
            if not peut_modifier_stock_au_depot(utilisateur, mi.depot, admin):
                raise ValueError('Droits insuffisants.')

        if mi.mouvement_stock_id:
            mv = MouvementStock.objects.select_for_update().get(pk=mi.mouvement_stock_id)
            q = Decimal(str(mi.quantite))
            ec = mv.quantite_ecarter or Decimal('0')
            if ec < q:
                raise ValueError(
                    'Incohérence : la quantité à l’écart sur la ligne est insuffisante pour annuler cette mise.'
                )
            mv.quantite_ecarter = ec - q
            mv.quantite_active = (mv.quantite_active or Decimal('0')) + q
            mv.save(update_fields=['quantite_active', 'quantite_ecarter'])

        mi.actif = False
        mi.save(update_fields=['actif'])


def enregistrer_correction_interne_ligne(
    utilisateur,
    *,
    entreprise,
    mouvement_stock_id: int,
    lot_batch: str,
    dateproduction,
    dateexpiration,
    location,
    location_code: str,
    marque: str,
    conditionnement: str,
    motif: str,
) -> MouvementStock:
    """
    Met à jour les métadonnées de traçabilité d’une ligne de lot (sans toucher aux quantités ni au stock agrégé).
    """
    from django.utils import timezone

    from stock.access import (
        peut_modifier_stock_au_depot,
        peut_modifier_stock_au_point_vente,
        utilisateur_est_admin,
    )

    motif = (motif or '').strip()
    if len(motif) < 3:
        raise ValueError('Le motif de correction est trop court.')

    admin = utilisateur_est_admin(utilisateur)
    lot_batch = (lot_batch or '').strip()[:20]
    location_code = (location_code or '').strip()[:20]
    marque = (marque or '').strip()[:100]
    conditionnement = (conditionnement or '').strip()[:100]

    with transaction.atomic():
        mv = (
            MouvementStock.objects.select_for_update()
            .select_related('produit', 'depot', 'pointvente')
            .get(pk=mouvement_stock_id, produit__entreprise=entreprise)
        )
        pv_obj = mv.pointvente_id and mv.pointvente
        if pv_obj:
            if not peut_modifier_stock_au_point_vente(utilisateur, pv_obj, admin):
                raise ValueError('Droits insuffisants pour ce point de vente.')
        else:
            if not mv.depot_id:
                raise ValueError('Ligne sans dépôt — correction impossible.')
            if not peut_modifier_stock_au_depot(utilisateur, mv.depot, admin):
                raise ValueError('Droits insuffisants pour ce dépôt.')

        mv.lot_batch = lot_batch
        mv.dateproduction = dateproduction
        mv.dateexpiration = dateexpiration
        mv.location = location
        if location:
            if not location_code:
                mv.location_code = (location.code or '')[:20]
            else:
                mv.location_code = location_code
        else:
            mv.location_code = location_code

        mv.marque = marque
        mv.conditionnement = conditionnement
        stamp = timezone.localtime().strftime('%d/%m/%Y %H:%M')
        mv.motif = (mv.motif or '').strip() + (
            f"\n\n[Correction interne — {stamp}] {motif}"
        )
        mv.effectue_par = utilisateur
        mv.save(
            update_fields=[
                'lot_batch',
                'dateproduction',
                'dateexpiration',
                'location',
                'location_code',
                'marque',
                'conditionnement',
                'motif',
                'effectue_par',
            ]
        )
    return mv
