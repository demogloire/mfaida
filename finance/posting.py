"""
Écritures comptables OHADA simplifiées liées aux stocks (OD).

Comptes types (créés à la demande) :
- 311000 : marchandises (classe 3)
- 603100 : variations de stocks (classe 6)
"""

from decimal import Decimal

from django.db import transaction

from finance.models import CompteComptable, EcritureComptable, Journal, LigneEcriture


def _ensure_journal_stock():
    j, _ = Journal.objects.get_or_create(
        code='OD-STK',
        defaults={'nom': 'Opérations diverses — stock', 'type_journal': 'OD'},
    )
    return j


def _ensure_compte(entreprise_id, numero, libelle, classe):
    obj, _ = CompteComptable.objects.get_or_create(
        entreprise_id=entreprise_id,
        numero=numero,
        defaults={'libelle': libelle, 'classe': classe, 'est_actif': True},
    )
    return obj


def classe_pour_numero(num):
    n = (num or '3')[:1]
    return n if n in '123456789' else '3'


def libelle_fallback(numero):
    num = (numero or '')[:10]
    m = {
        '311000': 'Marchandises',
        '603100': 'Variations des stocks marchandises',
    }
    return m.get(num, f'Compte {num}')


def _piece_equilibree(lignes):
    d = Decimal('0')
    c = Decimal('0')
    for _num, debit, credit in lignes:
        d += Decimal(str(debit or '0'))
        c += Decimal(str(credit or '0'))
    return d == c


@transaction.atomic
def poster_piece_od(entreprise, reference_piece: str, date_comptable, libelle: str, auteur, lignes):
    """
    lignes : liste de tuples (numero_compte_str, Decimal debit, Decimal credit).
    """
    specs = []
    for num, debit, credit in lignes:
        deb = Decimal(str(debit or '0'))
        cre = Decimal(str(credit or '0'))
        if deb == Decimal('0') and cre == Decimal('0'):
            continue
        specs.append((str(num)[:10], deb, cre))

    if len(specs) < 2:
        return None

    if not _piece_equilibree(specs):
        raise ValueError('Écriture non équilibrée.')

    journal = _ensure_journal_stock()
    ech = EcritureComptable.objects.create(
        journal=journal,
        reference_piece=(reference_piece or '')[:50],
        date_comptable=date_comptable,
        libelle=(libelle or '')[:255],
        auteur=auteur,
    )

    for num, deb, cre in specs:
        cls = classe_pour_numero(num)
        cpt = _ensure_compte(entreprise.pk, num[:10], libelle_fallback(num), cls)
        LigneEcriture.objects.create(ecriture=ech, compte=cpt, debit=deb, credit=cre)

    return ech


def poster_entree_stock_ohada(entreprise, montant_ht: Decimal, reference_piece, date_c, libelle, auteur):
    amt = Decimal(str(montant_ht))
    if amt <= 0:
        return None
    return poster_piece_od(
        entreprise,
        reference_piece[:50],
        date_c,
        libelle[:255],
        auteur,
        lignes=[
            ('311000', amt, Decimal('0')),
            ('603100', Decimal('0'), amt),
        ],
    )


def poster_variation_pure_ohada(entreprise, montant_ht: Decimal, augmentation_stock: bool,
                                reference_piece, date_c, libelle, auteur):
    amt = Decimal(str(montant_ht))
    if amt <= 0:
        return None
    if augmentation_stock:
        return poster_entree_stock_ohada(
            entreprise, amt, reference_piece[:50], date_c, libelle[:255], auteur
        )
    return poster_piece_od(
        entreprise,
        reference_piece[:50],
        date_c,
        libelle[:255],
        auteur,
        lignes=[
            ('603100', amt, Decimal('0')),
            ('311000', Decimal('0'), amt),
        ],
    )


def poster_cout_stock_vente(entreprise, montant_cos: Decimal,
                            reference_piece, date_c, libelle, auteur):
    amt = Decimal(str(montant_cos))
    if amt <= 0:
        return None
    return poster_piece_od(
        entreprise,
        reference_piece[:50],
        date_c,
        libelle[:255],
        auteur,
        lignes=[
            ('603100', amt, Decimal('0')),
            ('311000', Decimal('0'), amt),
        ],
    )


def montant_piece_reception(reception):
    """Valeur HT des quantités reçues sur le bon."""
    from decimal import Decimal as D

    tot = D('0')
    for ligne in reception.lignes.select_related(
        'ligne_ordre_achat',
        'produit',
        'ligne_ordre_achat__produit',
    ).all():
        q = ligne.quantite_recue_effective or D('0')
        if q <= 0:
            continue
        if ligne.ligne_ordre_achat_id:
            pu = ligne.ligne_ordre_achat.prix_unitaire_ht or D('0')
        elif ligne.produit_id:
            pu = ligne.prix_unitaire_ht or ligne.produit.prix_achat_ht or D('0')
        else:
            continue
        tot += q * D(str(pu))
    return tot
