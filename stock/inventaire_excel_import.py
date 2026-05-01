"""Import Excel des lignes d'inventaire (SKU / code-barres + quantité physique)."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from django.db import transaction

from entreprise.models import Produit
from stock.models import LigneInventaire
from stock.services import theorique_produit_lieu


def _norm_header(val) -> str:
    s = str(val or '').strip().lower()
    s = ''.join(
        c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn'
    )
    out = []
    prev_us = False
    for ch in s:
        if ch.isalnum():
            out.append(ch)
            prev_us = False
        elif not prev_us:
            out.append('_')
            prev_us = True
    r = ''.join(out).strip('_')
    while '__' in r:
        r = r.replace('__', '_')
    return r


SKU_KEYS = frozenset({'sku', 'reference', 'ref', 'code_article', 'code_art'})
BAR_KEYS = frozenset({'code_barre', 'codebarre', 'ean', 'gtin'})
PHYS_KEYS = frozenset(
    {
        'qte_physique',
        'quantite_physique',
        'physique',
        'qty_physique',
        'qty_phys',
        'quant_physique',
        'compte',
        'denombre',
        'stock_physique',
    }
)


def _col_map(headers_norm: list[str]) -> tuple[int | None, int | None, int | None]:
    """Indices : (sku_col, barcode_col, phys_col)."""
    idx_sku = idx_bar = idx_phys = None
    for i, h in enumerate(headers_norm):
        if h in SKU_KEYS:
            idx_sku = i
        if h in BAR_KEYS:
            idx_bar = i
        if h in PHYS_KEYS:
            idx_phys = i if idx_phys is None else idx_phys
    for i, h in enumerate(headers_norm):
        if idx_phys is None and 'physique' in h.split('_'):
            idx_phys = i
    for i, h in enumerate(headers_norm):
        if idx_phys is None and 'physique' in h:
            idx_phys = i
    return idx_sku, idx_bar, idx_phys


@dataclass
class InventaireImportExcelResult:
    applied: int = 0
    errors: list[str] = field(default_factory=list)
    skipped_blank: int = 0


def importer_lignes_inventaire_excel(
    ws,
    *,
    entreprise_id: int,
    inventaire,
    depot_cible,
    pv_stock,
    max_rows: int = 8000,
) -> InventaireImportExcelResult:
    """
    Ligne 1 = en-têtes, données à partir de la ligne 2.
    Colonnes détectées automatiquement : quantité physique obligatoire ;
    association produit par SKU et/ou code-barres (une des deux suffit).
    Compatible avec l’export Excel du même inventaire.
    """
    result = InventaireImportExcelResult()
    headers = [c.value for c in ws[1]]
    headers_norm = [_norm_header(h) for h in headers]
    idx_sku, idx_bar, idx_phys = _col_map(headers_norm)

    if idx_phys is None:
        result.errors.append(
            'Colonne « quantité physique » introuvable. Utilisez par ex. '
            '« Qté physique », « Quantité physique » ou « Physique ».'
        )
        return result
    if idx_sku is None and idx_bar is None:
        result.errors.append(
            'Colonne SKU ou code-barres introuvable. Ajoutez « SKU » ou « Code-barres » / « EAN ».'
        )
        return result

    to_apply: dict[int, Decimal] = {}

    prod_base = Produit.objects.filter(entreprise_id=entreprise_id, est_actif=True)

    ligne_no = 1
    for row in ws.iter_rows(
        min_row=2,
        max_row=min(ws.max_row or 0, max_rows + 1),
        values_only=True,
    ):
        ligne_no += 1
        if not row or all(v is None or str(v).strip() == '' for v in row):
            continue

        sku = ''
        if idx_sku is not None and idx_sku < len(row):
            sku = str(row[idx_sku] or '').strip()
        barcode = ''
        if idx_bar is not None and idx_bar < len(row):
            barcode = str(row[idx_bar] or '').strip()

        raw_phys = row[idx_phys] if idx_phys < len(row) else None
        if raw_phys is None or str(raw_phys).strip() == '':
            if sku or barcode:
                result.errors.append(
                    f'Ligne {ligne_no} : quantité physique vide alors qu’un SKU ou code-barres est renseigné.'
                )
            else:
                result.skipped_blank += 1
            continue

        if not sku and not barcode:
            result.skipped_blank += 1
            continue

        try:
            if isinstance(raw_phys, (int, float)) and not isinstance(raw_phys, bool):
                qty = Decimal(str(raw_phys))
            else:
                qty = Decimal(str(raw_phys).strip().replace(',', '.'))
        except (InvalidOperation, ValueError, TypeError):
            result.errors.append(f'Ligne {ligne_no} : quantité « {raw_phys} » invalide.')
            continue

        if qty < 0:
            result.errors.append(f'Ligne {ligne_no} : quantité négative interdite ({qty}).')
            continue

        p = None
        if sku:
            p = prod_base.filter(sku__iexact=sku[:200]).first()
        if p is None and barcode:
            p = prod_base.filter(code_barre=barcode[:200]).first()
        if p is None:
            ref = sku or barcode
            result.errors.append(
                f'Ligne {ligne_no} : aucun produit actif pour « {ref[:80]} » (SKU / code-barres).'
            )
            continue

        to_apply[p.pk] = qty

    if not to_apply:
        if not result.errors:
            result.errors.append(
                'Aucune ligne valide (fichier vide, en-têtes non reconnus ou aucun produit trouvé).'
            )
        return result

    with transaction.atomic():
        for pid, qty in to_apply.items():
            th = theorique_produit_lieu(pid, depot_cible, pv_stock)
            LigneInventaire.objects.update_or_create(
                inventaire=inventaire,
                produit_id=pid,
                defaults={
                    'quantite_theorique': th,
                    'quantite_physique': qty,
                },
            )
            result.applied += 1

    return result
