"""Calculs TVA conditionnels pour la vente au détail."""

from decimal import Decimal, InvalidOperation


def taux_tva_actif(taux_tva) -> bool:
    """True si une TVA doit être calculée (taux défini et strictement supérieur à 0)."""
    if taux_tva is None:
        return False
    try:
        t = Decimal(str(taux_tva))
    except (InvalidOperation, TypeError, ValueError):
        return False
    return t > 0


def montant_tva_sur_ht(ht, taux_tva) -> Decimal:
    """Montant TVA sur une base HT ; 0 si pas de taux actif."""
    ht = Decimal(str(ht))
    if not taux_tva_actif(taux_tva):
        return Decimal('0')
    taux = Decimal(str(taux_tva))
    return (ht * taux / Decimal('100')).quantize(Decimal('0.01'))
