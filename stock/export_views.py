"""Exports Excel et PDF pour les listes stock (filtres GET identiques aux vues liste)."""

from __future__ import annotations

import io
from datetime import date, datetime

from django.db.models import Count

from utilisateur.decorators import login_requis
from utilisateur.permissions import peut_voir_prix_achat_ht

from stock.access import (
    get_entreprise_utilisateur,
    utilisateur_est_admin,
)
from stock.export_tabular import (
    excel_workbook_bytes,
    fichier_nom_safe_fragment,
    pdf_table_bytes,
    response_attachment_pdf,
    response_attachment_xlsx,
)
from stock.services import theorique_produit_lieu
from stock.views import (
    _charger_inventaire,
    _detail_produit_stock_context,
    _exiger_entreprise,
    _inventaire_scope_filter,
    _liste_mouvements_context,
    _liste_stocks_context,
    _liste_stocks_synthese_context,
    _mise_a_ecart_queryset,
)


def _unwrap_stock_ctx(result):
    if not isinstance(result, tuple):
        return None, result
    return result, None


def _lbl_user(prof):
    if not prof:
        return ''
    return prof.get_full_name() or getattr(prof, 'username', '') or ''


def _fmt_datetime(val):
    if not val:
        return ''
    if isinstance(val, datetime):
        return val.strftime('%d/%m/%Y %H:%M')
    if isinstance(val, date):
        return val.strftime('%d/%m/%Y')
    return str(val)


LIMIT_LOTS = 20000
LIMIT_MOUVEMENTS_EXPORT = 15000


def _row_ligne_stock(m, lieu: str, voir_pa: bool):
    loc = ''
    if m.location_id:
        loc = getattr(m.location, 'code', '') or ''
    if not loc:
        loc = (m.location_code or '').strip()
    cmd = ''
    if m.ligneordreachat_id:
        loa = m.ligneordreachat
        if loa is not None and getattr(loa, 'ordre_achat', None) is not None:
            cmd = loa.ordre_achat.numero_commande or ''
    p = m.produit
    base = [p.libelle_ligne_achat]
    if lieu == 'pv':
        base.append(m.pointvente.nom if m.pointvente_id else '')
    base.extend(
        [
            m.depot.nom if m.depot_id else '',
            m.quantite_recu,
            m.quantite_active,
            m.quantite_affectee,
            m.quantite_ecarter,
        ]
    )
    if voir_pa:
        base.append(m.prix_unitaire)
    base.extend(
        [
            p.prix_vente_ht,
            p.prix_vente_ttc,
            loc,
            m.lot_batch or '',
            m.dateproduction.strftime('%d/%m/%Y') if m.dateproduction else '',
            m.dateexpiration.strftime('%d/%m/%Y') if m.dateexpiration else '',
            m.get_origine_display(),
            (m.motif or '')[:250],
            cmd,
            m.reference_piece or '',
            m.marque or '',
            m.conditionnement or '',
            m.unite or '',
            _fmt_datetime(m.date_creation),
            _lbl_user(m.effectue_par),
        ]
    )
    return base


def _headers_stock_lots(lieu: str, voir_pa: bool):
    hdr = ['Produit']
    if lieu == 'pv':
        hdr.append('Point de vente')
    hdr.extend(
        ['Dépôt', 'Reçu', 'Actif', 'Affectée', 'Écarter']
    )
    if voir_pa:
        hdr.append('PA HT')
    hdr.extend(
        [
            'PV HT',
            'PV TTC',
            'Empl.',
            'Lot',
            'Fab.',
            'Exp.',
            'Origine',
            'Motif',
            'Cmd achat',
            'Réf. pièce',
            'Marque',
            'Condit.',
            'Unité',
            'Date mouv.',
            'Enregistré par',
        ]
    )
    return hdr


def _subtitle_stock_liste(data):
    bits = []
    if data.get('q'):
        bits.append(f'recherche={data["q"]}')
    if data.get('lieu') == 'depot' and data.get('filt_pk'):
        bits.append(f'dépôt id={data["filt_pk"]}')
    if data.get('lieu') == 'pv' and data.get('filt_pk'):
        bits.append(f'PDV id={data["filt_pk"]}')
    return ' · '.join(bits) if bits else ''


# ——— Stock lots ———


@login_requis
def export_liste_stock_depot_excel(request):
    voir_pa = peut_voir_prix_achat_ht(request.user)
    ctx, redir = _unwrap_stock_ctx(
        _liste_stocks_context(request, 'depot', row_limit=LIMIT_LOTS)
    )
    if redir:
        return redir
    _ent, data = ctx
    rows = [_row_ligne_stock(r['mouvement'], 'depot', voir_pa) for r in data['lignes']]
    hdr = _headers_stock_lots('depot', voir_pa)
    fn = fichier_nom_safe_fragment(_ent.nom + '_stock_depot')
    return response_attachment_xlsx(
        excel_workbook_bytes([('Stock dépôt', hdr, rows)]),
        f'{fn}.xlsx',
    )


@login_requis
def export_liste_stock_depot_pdf(request):
    voir_pa = peut_voir_prix_achat_ht(request.user)
    ctx, redir = _unwrap_stock_ctx(
        _liste_stocks_context(request, 'depot', row_limit=min(LIMIT_LOTS, 400))
    )
    if redir:
        return redir
    _ent, data = ctx
    rows = [_row_ligne_stock(r['mouvement'], 'depot', voir_pa) for r in data['lignes']]
    hdr = _headers_stock_lots('depot', voir_pa)
    sub = _subtitle_stock_liste(data)
    blob = pdf_table_bytes(
        f'Stock dépôt — {_ent.nom}',
        sub + ' · max 400 lignes PDF',
        hdr,
        rows,
        landscape=True,
        font_size=6,
    )
    return response_attachment_pdf(
        blob, f'{fichier_nom_safe_fragment(_ent.nom + "_stock_depot")}.pdf'
    )


@login_requis
def export_liste_stock_pdv_excel(request):
    voir_pa = peut_voir_prix_achat_ht(request.user)
    ctx, redir = _unwrap_stock_ctx(
        _liste_stocks_context(request, 'pv', row_limit=LIMIT_LOTS)
    )
    if redir:
        return redir
    _ent, data = ctx
    rows = [_row_ligne_stock(r['mouvement'], 'pv', voir_pa) for r in data['lignes']]
    hdr = _headers_stock_lots('pv', voir_pa)
    fn = fichier_nom_safe_fragment(_ent.nom + '_stock_pdv')
    return response_attachment_xlsx(
        excel_workbook_bytes([('Stock PDV', hdr, rows)]),
        f'{fn}.xlsx',
    )


@login_requis
def export_liste_stock_pdv_pdf(request):
    voir_pa = peut_voir_prix_achat_ht(request.user)
    ctx, redir = _unwrap_stock_ctx(
        _liste_stocks_context(request, 'pv', row_limit=min(LIMIT_LOTS, 400))
    )
    if redir:
        return redir
    _ent, data = ctx
    rows = [_row_ligne_stock(r['mouvement'], 'pv', voir_pa) for r in data['lignes']]
    hdr = _headers_stock_lots('pv', voir_pa)
    blob = pdf_table_bytes(
        f'Stock points de vente — {_ent.nom}',
        _subtitle_stock_liste(data) + ' · max 400 lignes PDF',
        hdr,
        rows,
        landscape=True,
        font_size=6,
    )
    return response_attachment_pdf(
        blob, f'{fichier_nom_safe_fragment(_ent.nom + "_stock_pdv")}.pdf'
    )


# ——— Synthèse ———


def _rows_synthese(data):
    hdr = [
        'Produit',
        'PU réf. HT',
        'Physique',
        'À l’écart',
        'Disponible',
        'Valeur à l’écart HT',
        'Valeur disponible HT',
    ]
    rows = []
    for r in data['lignes_synthese']:
        rows.append(
            [
                r['produit'].libelle_ligne_achat,
                r['prix_unitaire_ref'],
                r['physique'],
                r['a_ecart'],
                r['disponible'],
                r['valeur_ecart'],
                r['valeur_disponible'],
            ]
        )
    rows.append(
        [
            'Totaux valeur',
            '',
            '',
            '',
            '',
            data['total_valeur_ecart'],
            data['total_valeur_disponible'],
        ]
    )
    return hdr, rows


@login_requis
def export_synthese_depot_excel(request):
    ctx, redir = _unwrap_stock_ctx(_liste_stocks_synthese_context(request, 'depot'))
    if redir:
        return redir
    _ent, data = ctx
    hdr, rows = _rows_synthese(data)
    fn = fichier_nom_safe_fragment(_ent.nom + '_synthese_depot')
    return response_attachment_xlsx(
        excel_workbook_bytes([('Synthèse dépôt', hdr, rows)]),
        f'{fn}.xlsx',
    )


@login_requis
def export_synthese_depot_pdf(request):
    ctx, redir = _unwrap_stock_ctx(_liste_stocks_synthese_context(request, 'depot'))
    if redir:
        return redir
    _ent, data = ctx
    hdr, rows = _rows_synthese(data)
    blob = pdf_table_bytes(
        f'Synthèse stock dépôt — {_ent.nom}',
        _subtitle_stock_liste(data),
        hdr,
        rows,
        landscape=False,
        font_size=8,
    )
    return response_attachment_pdf(
        blob, f'{fichier_nom_safe_fragment(_ent.nom + "_synthese_depot")}.pdf'
    )


@login_requis
def export_synthese_pdv_excel(request):
    ctx, redir = _unwrap_stock_ctx(_liste_stocks_synthese_context(request, 'pv'))
    if redir:
        return redir
    _ent, data = ctx
    hdr, rows = _rows_synthese(data)
    fn = fichier_nom_safe_fragment(_ent.nom + '_synthese_pdv')
    return response_attachment_xlsx(
        excel_workbook_bytes([('Synthèse PDV', hdr, rows)]),
        f'{fn}.xlsx',
    )


@login_requis
def export_synthese_pdv_pdf(request):
    ctx, redir = _unwrap_stock_ctx(_liste_stocks_synthese_context(request, 'pv'))
    if redir:
        return redir
    _ent, data = ctx
    hdr, rows = _rows_synthese(data)
    blob = pdf_table_bytes(
        f'Synthèse stock PDV — {_ent.nom}',
        _subtitle_stock_liste(data),
        hdr,
        rows,
        landscape=False,
        font_size=8,
    )
    return response_attachment_pdf(
        blob, f'{fichier_nom_safe_fragment(_ent.nom + "_synthese_pdv")}.pdf'
    )


# ——— Mouvements ———


def _rows_mouvements(data):
    lieu = data['lieu']
    hdr = ['Date', 'Produit', 'Origine']
    if lieu == 'pv':
        hdr.append('Point de vente')
    hdr.extend(['Dépôt', 'Reçu', 'Actif', 'Par'])
    rows = []
    for m in data['mouvements']:
        r = [_fmt_datetime(m.date_creation), m.produit.libelle_ligne_achat, m.get_origine_display()]
        if lieu == 'pv':
            r.append(m.pointvente.nom if m.pointvente_id else '')
        r.extend([
            m.depot.nom if m.depot_id else '',
            m.quantite_recu,
            m.quantite_active,
            _lbl_user(m.effectue_par),
        ])
        rows.append(r)
    return hdr, rows


@login_requis
def export_mouvements_depot_excel(request):
    ctx, redir = _unwrap_stock_ctx(
        _liste_mouvements_context(request, 'depot', mouvements_limit=LIMIT_MOUVEMENTS_EXPORT)
    )
    if redir:
        return redir
    _ent, data = ctx
    hdr, rows = _rows_mouvements(data)
    fn = fichier_nom_safe_fragment(_ent.nom + '_mouvements_depot')
    return response_attachment_xlsx(
        excel_workbook_bytes([('Mouvements dépôt', hdr, rows)]),
        f'{fn}.xlsx',
    )


@login_requis
def export_mouvements_depot_pdf(request):
    ctx, redir = _unwrap_stock_ctx(
        _liste_mouvements_context(request, 'depot', mouvements_limit=min(800, LIMIT_MOUVEMENTS_EXPORT))
    )
    if redir:
        return redir
    _ent, data = ctx
    hdr, rows = _rows_mouvements(data)
    blob = pdf_table_bytes(
        f'Mouvements dépôt — {_ent.nom}',
        (data.get('origine') or '') + ' · max 800 lignes PDF',
        hdr,
        rows,
        landscape=True,
        font_size=7,
    )
    return response_attachment_pdf(
        blob, f'{fichier_nom_safe_fragment(_ent.nom + "_mvt_depot")}.pdf'
    )


@login_requis
def export_mouvements_pdv_excel(request):
    ctx, redir = _unwrap_stock_ctx(
        _liste_mouvements_context(request, 'pv', mouvements_limit=LIMIT_MOUVEMENTS_EXPORT)
    )
    if redir:
        return redir
    _ent, data = ctx
    hdr, rows = _rows_mouvements(data)
    fn = fichier_nom_safe_fragment(_ent.nom + '_mouvements_pdv')
    return response_attachment_xlsx(
        excel_workbook_bytes([('Mouvements PDV', hdr, rows)]),
        f'{fn}.xlsx',
    )


@login_requis
def export_mouvements_pdv_pdf(request):
    ctx, redir = _unwrap_stock_ctx(
        _liste_mouvements_context(request, 'pv', mouvements_limit=min(800, LIMIT_MOUVEMENTS_EXPORT))
    )
    if redir:
        return redir
    _ent, data = ctx
    hdr, rows = _rows_mouvements(data)
    blob = pdf_table_bytes(
        f'Mouvements PDV — {_ent.nom}',
        (data.get('origine') or '') + ' · max 800 lignes PDF',
        hdr,
        rows,
        landscape=True,
        font_size=7,
    )
    return response_attachment_pdf(
        blob, f'{fichier_nom_safe_fragment(_ent.nom + "_mvt_pdv")}.pdf'
    )


# ——— Mises à l'écart ———


def _rows_mises(mises_iter, lieu: str):
    hdr = ['Date', 'Produit', 'SKU', 'Lieu', 'Mouvement', 'Quantité', 'Motif', 'Créé par']
    rows = []
    for mi in mises_iter:
        sku = getattr(mi.produit, 'sku', '') or ''
        lieu_txt = (
            mi.depot.nom if lieu == 'depot' else (mi.pointdevente.nom if mi.pointdevente_id else '')
        )
        rows.append(
            [
                _fmt_datetime(mi.date_creation),
                mi.produit.libelle_ligne_achat,
                sku,
                lieu_txt,
                mi.mouvement_stock_id or '',
                mi.quantite,
                (mi.motif or '')[:400],
                _lbl_user(mi.cree_par),
            ]
        )
    return hdr, rows


@login_requis
def export_mise_a_ecart_depot_excel(request):
    entreprise, qs, *_pack = _mise_a_ecart_queryset(request, 'depot')
    redir = _pack[-1]
    if redir:
        return redir
    mises = list(qs.order_by('-date_creation')[:LIMIT_MOUVEMENTS_EXPORT])
    hdr, rows = _rows_mises(mises, 'depot')
    fn = fichier_nom_safe_fragment(entreprise.nom + '_mises_ecart_depot')
    return response_attachment_xlsx(
        excel_workbook_bytes([('Mises à l’écart dépôt', hdr, rows)]), f'{fn}.xlsx'
    )


@login_requis
def export_mise_a_ecart_depot_pdf(request):
    entreprise, qs, *_pack = _mise_a_ecart_queryset(request, 'depot')
    redir = _pack[-1]
    if redir:
        return redir
    mises = list(qs.order_by('-date_creation')[:600])
    hdr, rows = _rows_mises(mises, 'depot')
    blob = pdf_table_bytes(
        f'Mises à l’écart — dépôt — {entreprise.nom}',
        'max 600 lignes PDF',
        hdr,
        rows,
        landscape=True,
        font_size=8,
    )
    return response_attachment_pdf(
        blob, f'{fichier_nom_safe_fragment(entreprise.nom + "_mise_ec_depot")}.pdf'
    )


@login_requis
def export_mise_a_ecart_pdv_excel(request):
    entreprise, qs, *_pack = _mise_a_ecart_queryset(request, 'pv')
    redir = _pack[-1]
    if redir:
        return redir
    mises = list(qs.order_by('-date_creation')[:LIMIT_MOUVEMENTS_EXPORT])
    hdr, rows = _rows_mises(mises, 'pv')
    fn = fichier_nom_safe_fragment(entreprise.nom + '_mises_ecart_pdv')
    return response_attachment_xlsx(
        excel_workbook_bytes([('Mises à l’écart PDV', hdr, rows)]), f'{fn}.xlsx'
    )


@login_requis
def export_mise_a_ecart_pdv_pdf(request):
    entreprise, qs, *_pack = _mise_a_ecart_queryset(request, 'pv')
    redir = _pack[-1]
    if redir:
        return redir
    mises = list(qs.order_by('-date_creation')[:600])
    hdr, rows = _rows_mises(mises, 'pv')
    blob = pdf_table_bytes(
        f'Mises à l’écart — PDV — {entreprise.nom}',
        'max 600 lignes PDF',
        hdr,
        rows,
        landscape=True,
        font_size=8,
    )
    return response_attachment_pdf(
        blob, f'{fichier_nom_safe_fragment(entreprise.nom + "_mise_ec_pdv")}.pdf'
    )


# ——— Inventaires ———


def _filt_inventaires_qs(request):
    entreprise = get_entreprise_utilisateur(request.user)
    admin = utilisateur_est_admin(request.user)
    redir = _exiger_entreprise(request, entreprise)
    if redir:
        return None, None, redir
    filt = request.GET.get('lieu', '')
    qs = (
        _inventaire_scope_filter(entreprise, request.user, admin)
        .select_related('depot', 'pointdevente', 'valide_par')
        .annotate(lignes_n=Count('lignes'))
        .order_by('-date_inventaire', '-pk')
    )
    if filt == 'depot':
        qs = qs.filter(depot__isnull=False, pointdevente__isnull=True)
    elif filt == 'pv':
        qs = qs.filter(pointdevente__isnull=False)
    return entreprise, qs, None


@login_requis
def export_inventaires_liste_excel(request):
    entreprise, qs, redir = _filt_inventaires_qs(request)
    if redir:
        return redir
    hdr = ['Lot', 'Date', 'Lieu', 'Nb lignes', 'Statut', 'Validé par']
    rows = []
    for inv in qs:
        lieu = (
            inv.depot.nom
            if inv.depot_id
            else (inv.pointdevente.nom if inv.pointdevente_id else '')
        )
        rows.append(
            [
                inv.lot,
                inv.date_inventaire.strftime('%d/%m/%Y')
                if inv.date_inventaire
                else '',
                lieu,
                inv.lignes_n,
                'Clôturé' if inv.cloture else 'Ouvert',
                _lbl_user(inv.valide_par),
            ]
        )
    fn = fichier_nom_safe_fragment(entreprise.nom + '_inventaires')
    return response_attachment_xlsx(
        excel_workbook_bytes([('Inventaires', hdr, rows)]), f'{fn}.xlsx'
    )


@login_requis
def export_inventaires_liste_pdf(request):
    entreprise, qs, redir = _filt_inventaires_qs(request)
    if redir:
        return redir
    hdr = ['Lot', 'Date', 'Lieu', 'Nb lignes', 'Statut', 'Validé par']
    rows = []
    for inv in qs[:400]:
        lieu = (
            inv.depot.nom
            if inv.depot_id
            else (inv.pointdevente.nom if inv.pointdevente_id else '')
        )
        rows.append(
            [
                inv.lot,
                inv.date_inventaire.strftime('%d/%m/%Y')
                if inv.date_inventaire
                else '',
                lieu,
                inv.lignes_n,
                'Clôturé' if inv.cloture else 'Ouvert',
                _lbl_user(inv.valide_par),
            ]
        )
    blob = pdf_table_bytes(
        f'Campagnes inventaire — {entreprise.nom}',
        'max 400 lignes PDF',
        hdr,
        rows,
        landscape=True,
        font_size=8,
    )
    return response_attachment_pdf(
        blob, f'{fichier_nom_safe_fragment(entreprise.nom + "_inventaires")}.pdf'
    )


@login_requis
def export_inventaire_detail_excel(request, pk):
    inv, redir = _charger_inventaire(request, pk)
    if redir:
        return redir
    if inv.pointdevente_id:
        depot_cible = inv.pointdevente.depot_source
        pv_stock = inv.pointdevente
    else:
        depot_cible = inv.depot
        pv_stock = None
    hdr = [
        'Produit',
        'SKU',
        'Qté théorique (saisie)',
        'Qté physique',
        'Écart',
        'Disponible lots (à la clôture)',
    ]
    rows = []
    for li in inv.lignes.select_related('produit').order_by('produit__nom'):
        th = theorique_produit_lieu(li.produit_id, depot_cible, pv_stock)
        rows.append(
            [
                li.produit.libelle_ligne_achat,
                li.produit.sku or '',
                li.quantite_theorique,
                li.quantite_physique,
                li.ecart,
                th,
            ]
        )
    fn = fichier_nom_safe_fragment(f'{inv.lot}_{pk}')
    return response_attachment_xlsx(
        excel_workbook_bytes([(f'INV {inv.lot}', hdr, rows)]),
        f'{fn}.xlsx',
    )


@login_requis
def export_inventaire_detail_pdf(request, pk):
    inv, redir = _charger_inventaire(request, pk)
    if redir:
        return redir
    if inv.pointdevente_id:
        depot_cible = inv.pointdevente.depot_source
        pv_stock = inv.pointdevente
    else:
        depot_cible = inv.depot
        pv_stock = None
    hdr = ['Produit', 'SKU', 'Théo. saisie', 'Phys.', 'Écart', 'Dispo. lots']
    rows = []
    for li in inv.lignes.select_related('produit').order_by('produit__nom'):
        th = theorique_produit_lieu(li.produit_id, depot_cible, pv_stock)
        rows.append(
            [
                li.produit.libelle_ligne_achat,
                li.produit.sku or '',
                li.quantite_theorique,
                li.quantite_physique,
                li.ecart,
                th,
            ]
        )
    lieu = (
        inv.depot.nom
        if inv.depot_id
        else (inv.pointdevente.nom if inv.pointdevente_id else '')
    )
    blob = pdf_table_bytes(
        f'Inventaire {inv.lot}',
        f'{lieu} — {inv.date_inventaire}',
        hdr,
        rows,
        landscape=True,
        font_size=7,
    )
    return response_attachment_pdf(
        blob, f'{fichier_nom_safe_fragment(inv.lot)}.pdf'
    )


@login_requis
def export_produit_stock_excel(request, pk):
    ctx = _detail_produit_stock_context(request, pk, mouvements_limit=5000)
    if not isinstance(ctx, dict):
        return ctx
    p = ctx['produit']
    feuilles = (
        (
            'Niveaux dépôt',
            ['Dépôt', 'Quantité'],
            [[s.depot.nom, s.quantite_reelle] for s in ctx['niveaux_depot']],
        ),
        (
            'Niveaux PDV',
            ['Point de vente', 'Dépôt', 'Quantité'],
            [
                [s.pointdevente.nom, s.depot.nom, s.quantite_reelle]
                for s in ctx['niveaux_pdv']
            ],
        ),
        (
            'Mouvements dépôt',
            ['Date', 'Origine', 'Dépôt', 'Reçu', 'Actif', 'Affecté'],
            [
                [
                    _fmt_datetime(m.date_creation),
                    m.get_origine_display(),
                    m.depot.nom if m.depot_id else '',
                    m.quantite_recu,
                    m.quantite_active,
                    m.quantite_affectee,
                ]
                for m in ctx['mouvements_depot']
            ],
        ),
        (
            'Mouvements PDV',
            ['Date', 'Origine', 'PDV', 'Dépôt', 'Reçu', 'Actif', 'Affecté'],
            [
                [
                    _fmt_datetime(m.date_creation),
                    m.get_origine_display(),
                    m.pointvente.nom if m.pointvente_id else '',
                    m.depot.nom if m.depot_id else '',
                    m.quantite_recu,
                    m.quantite_active,
                    m.quantite_affectee,
                ]
                for m in ctx['mouvements_pdv']
            ],
        ),
    )
    fn = fichier_nom_safe_fragment(f'stock_produit_{p.sku or p.pk}')
    return response_attachment_xlsx(excel_workbook_bytes(feuilles), f'{fn}.xlsx')


@login_requis
def export_produit_stock_pdf(request, pk):
    ctx = _detail_produit_stock_context(request, pk, mouvements_limit=200)
    if not isinstance(ctx, dict):
        return ctx
    p = ctx['produit']

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    def esc(t):
        if t is None:
            return ''
        return str(t).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    pdf_buf = io.BytesIO()
    doc = SimpleDocTemplate(pdf_buf, pagesize=A4, leftMargin=1 * cm, rightMargin=1 * cm)
    sty = getSampleStyleSheet()
    story = []
    story.append(Paragraph(f'<b>{esc(p.libelle_ligne_achat)}</b>', sty['Title']))
    story.append(Spacer(1, 0.3 * cm))

    def add_tbl(title_txt, hdr, rowdata):
        story.append(Paragraph(f'<b>{esc(title_txt)}</b>', sty['Heading4']))
        d = [hdr] + rowdata
        tbl = Table(d, repeatRows=1)
        tbl.setStyle(
            TableStyle(
                [
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E2E8F0')),
                    ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
                    ('FONTSIZE', (0, 0), (-1, -1), 7),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ]
            )
        )
        story.append(tbl)
        story.append(Spacer(1, 0.35 * cm))

    add_tbl(
        'Stock dépôt',
        ['Dépôt', 'Qté'],
        [[s.depot.nom, str(s.quantite_reelle)] for s in ctx['niveaux_depot']],
    )
    add_tbl(
        'Stock PDV',
        ['PDV', 'Dépôt', 'Qté'],
        [
            [s.pointdevente.nom, s.depot.nom, str(s.quantite_reelle)]
            for s in ctx['niveaux_pdv']
        ],
    )
    add_tbl(
        'Mouvements dépôt (200 derniers)',
        ['Date', 'Origine', 'Dépôt', 'Actif'],
        [
            [
                _fmt_datetime(m.date_creation),
                m.get_origine_display(),
                m.depot.nom if m.depot_id else '',
                str(m.quantite_active),
            ]
            for m in ctx['mouvements_depot']
        ],
    )
    add_tbl(
        'Mouvements PDV (200 derniers)',
        ['Date', 'Origine', 'PDV', 'Actif'],
        [
            [
                _fmt_datetime(m.date_creation),
                m.get_origine_display(),
                m.pointvente.nom if m.pointvente_id else '',
                str(m.quantite_active),
            ]
            for m in ctx['mouvements_pdv']
        ],
    )

    doc.build(story)
    return response_attachment_pdf(pdf_buf.getvalue(), f'{fichier_nom_safe_fragment(str(p.pk))}_produit.pdf')
