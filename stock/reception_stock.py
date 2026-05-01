"""Application d'un bon de réception validé vers Stock et MouvementStock."""

from decimal import Decimal

from django.db import transaction

from stock.models import MouvementStock, Stock, MouvementOrigine


def _produit_et_prix_br(ligne):
    from decimal import Decimal as D

    if ligne.ligne_ordre_achat_id:
        loa = ligne.ligne_ordre_achat
        return loa.produit, loa.prix_unitaire_ht, (loa.unite or '').strip() or loa.produit.unite_mesure
    if not ligne.produit_id:
        raise ValueError('Ligne sans produit.')
    prix = ligne.prix_unitaire_ht
    if prix is None:
        prix = ligne.produit.prix_achat_ht
    unite = ligne.produit.unite_mesure
    return ligne.produit, D(str(prix)), unite


def appliquer_bon_reception_au_stock(reception, effectue_par):
    """
    Crée les mouvements de stock et met à jour les quantités (Stock).
    Appeler dans une transaction atomique avant de passer le bon au statut VALIDE.

    Raises:
        ValueError: destination incohérente ou point de vente sans dépôt source.
    """
    depot_dest = reception.depot_destination_id
    pv_dest = reception.point_destination_id

    if bool(depot_dest) == bool(pv_dest):
        raise ValueError(
            'Le bon doit cibler exactement une destination : un dépôt ou un point de vente.'
        )

    if depot_dest:
        mouv_depot = reception.depot_destination
        mouv_pv = None
        stock_depot = reception.depot_destination
        stock_pv = None
    else:
        pv = reception.point_destination
        if not pv.depot_source_id:
            raise ValueError(
                "Ce point de vente n'a pas de dépôt source : impossible de constituer le stock."
            )
        mouv_depot = pv.depot_source
        mouv_pv = pv
        stock_depot = pv.depot_source
        stock_pv = pv

    lignes_qs = reception.lignes.select_related(
        'ligne_ordre_achat__produit',
        'produit',
        'location',
    )

    with transaction.atomic():
        for ligne in lignes_qs:
            qte = ligne.quantite_recue_effective or Decimal('0')
            if qte <= 0:
                continue

            ecarter = ligne.quantite_ecarter or Decimal('0')
            if ecarter < 0:
                raise ValueError("La quantité à l'écart ne peut pas être négative.")
            if ecarter > qte:
                raise ValueError(
                    "La quantité à l'écart ne peut pas dépasser la quantité reçue sur une ligne de bon de réception."
                )
            q_active = qte - ecarter

            produit, prix_unitaire, unite = _produit_et_prix_br(ligne)

            dprod = ligne.dateproduction
            dexp = ligne.dateexpiration
            if ligne.ligne_ordre_achat_id:
                loa = ligne.ligne_ordre_achat
                if dprod is None:
                    dprod = loa.dateproduction
                if dexp is None:
                    dexp = loa.dateexpiration

            lot = (ligne.lot_batch or '').strip()
            if ligne.ligne_ordre_achat_id and not lot:
                lot = (ligne.ligne_ordre_achat.lot_batch or '').strip()

            loc = ligne.location
            loc_code = loc.code if ligne.location_id else ''

            marque = (ligne.marque or '').strip()
            cond = (ligne.conditionnement or '').strip()

            MouvementStock.objects.create(
                produit=produit,
                depot=mouv_depot,
                pointvente=mouv_pv,
                location=loc,
                quantite_recu=qte,
                quantite_affectee=Decimal('0'),
                quantite_ecarter=ecarter,
                quantite_active=q_active,
                prix_unitaire=prix_unitaire,
                dateproduction=dprod,
                dateexpiration=dexp,
                lot_batch=lot[:20] if lot else '',
                unite=(unite or '')[:20],
                location_code=(loc_code or '')[:20],
                marque=marque[:100] if marque else '',
                conditionnement=(cond[:100] if cond else ''),
                ligneordreachat=ligne.ligne_ordre_achat if ligne.ligne_ordre_achat_id else None,
                origine=MouvementOrigine.BR,
                effectue_par=effectue_par,
            )

            stock, _ = Stock.objects.get_or_create(
                produit=produit,
                depot=stock_depot,
                pointdevente=stock_pv,
                defaults={'quantite_reelle': Decimal('0')},
            )
            stock.quantite_reelle = (stock.quantite_reelle or Decimal('0')) + qte
            stock.save(update_fields=['quantite_reelle', 'derniere_mise_a_jour'])
