"""
Exports Excel et PDF pour les bons de commande (achat).
"""
from io import BytesIO


def branche_siege_pour(entreprise):
    from entreprise.models import Branche

    return (
        Branche.objects.filter(entreprise=entreprise, est_siege_social=True)
        .order_by('pk')
        .first()
    )


def _esc_pdf(txt):
    if txt is None:
        return ''
    s = str(txt)
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def build_excel_bc(commande):
    """Retourne le contenu binaire d'un classeur .xlsx (récap + lignes)."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = 'Récap'

    ent = commande.entreprise
    four = commande.fournisseur
    bs = branche_siege_pour(ent)

    titre_font = Font(bold=True, size=14)
    ws['A1'] = f'Bon de commande {commande.numero_commande}'
    ws['A1'].font = titre_font
    ws.merge_cells('A1:B1')

    meta = [
        ('Entreprise', ent.nom),
        ('Adresse siège social', ent.adresse_siege or ''),
        ('RCCM', ent.rccm or ''),
        ('ID National', ent.idnat or ''),
        ('N° impôt', ent.numero_impot or ''),
        ('Téléphone', ent.telephone or ''),
        ('Email', ent.email or ''),
        ('Branche siège social', bs.nom if bs else ''),
        ('Ville (siège)', bs.ville if bs else ''),
        ('Code branche siège', bs.code_branche if bs else ''),
        ('', ''),
        ('Fournisseur', four.nom_societe),
        ('Code fournisseur', four.code_fournisseur),
        ('Contact', four.contact_nom or ''),
        ('Tél. fournisseur', four.telephone or ''),
        ('Email fournisseur', four.email or ''),
        ('Adresse fournisseur', four.adresse or ''),
        ('Ville fournisseur', four.ville or ''),
        ('ID Fiscal / RCCM (tiers)', four.rccm_id or ''),
        ('', ''),
        ('N° commande', commande.numero_commande),
        ('Date commande', commande.date_commande.strftime('%d/%m/%Y %H:%M')),
        ('Statut', commande.get_statut_display()),
        ('Livraison prévue', commande.date_livraison_prevue.strftime('%d/%m/%Y') if commande.date_livraison_prevue else ''),
        ('Dépôt destination', commande.depot_destination.nom if commande.depot_destination_id else ''),
        ('Point de vente destination', commande.pointdevente_destination.nom if commande.pointdevente_destination_id else ''),
        ('Devise', commande.devise.code if commande.devise_id else ''),
        ('Créé par', commande.cree_par.get_username() if commande.cree_par_id else ''),
        ('Notes commande', commande.notes or ''),
        ('', ''),
        ('Total HT', float(commande.total_ht)),
        ('Total TVA', float(commande.total_tva)),
        ('Total TTC', float(commande.total_ttc)),
    ]

    row = 3
    label_fill = PatternFill('solid', fgColor='E8EEF7')
    for label, val in meta:
        ws.cell(row=row, column=1, value=label)
        ws.cell(row=row, column=2, value=val)
        if label:
            ws.cell(row=row, column=1).font = Font(bold=True)
            ws.cell(row=row, column=1).fill = label_fill
        ws.cell(row=row, column=2).alignment = Alignment(wrap_text=True, vertical='top')
        row += 1

    ws.column_dimensions['A'].width = 28
    ws.column_dimensions['B'].width = 55

    ws2 = wb.create_sheet('Lignes')
    headers = [
        'sku',
        'nom_produit',
        'code_barre',
        'quantite_commandee',
        'unite',
        'prix_unitaire_ht',
        'taux_tva_pct',
        'montant_ht_ligne',
        'quantite_recue',
        'lot_batch',
        'dateproduction',
        'dateexpiration',
        'location_code',
    ]
    h_font = Font(bold=True, color='FFFFFF')
    h_fill = PatternFill('solid', fgColor='1A56DB')
    for col, h in enumerate(headers, 1):
        c = ws2.cell(row=1, column=col, value=h)
        c.font = h_font
        c.fill = h_fill

    for ligne in commande.lignes.all():
        p = ligne.produit
        ws2.append(
            [
                (p.sku or '') if p.sku else '',
                p.nom,
                p.code_barre or '',
                float(ligne.quantite_commandee),
                ligne.unite or '',
                float(ligne.prix_unitaire_ht),
                float(p.tva_taux),
                float(ligne.sous_total_ht),
                float(ligne.quantite_recue or 0),
                ligne.lot_batch or '',
                ligne.dateproduction.isoformat() if ligne.dateproduction else '',
                ligne.dateexpiration.isoformat() if ligne.dateexpiration else '',
                ligne.location.code if ligne.location_id else '',
            ]
        )

    for col in range(1, len(headers) + 1):
        ws2.column_dimensions[ws2.cell(row=1, column=col).column_letter].width = 16

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


def _statut_couleur(statut):
    return {
        'BROUILLON': '#64748B',
        'ENVOYE': '#1A56DB',
        'RECU_PARTIEL': '#D97706',
        'RECU_TOTAL': '#059669',
        'ANNULE': '#DC2626',
    }.get(statut, '#64748B')


def _symbole_devise(commande):
    if commande.devise_id and getattr(commande.devise, 'symbole', None):
        return commande.devise.symbole
    return '$'


def _qr_flowable(commande):
    """QR code pointant vers la fiche BC si SITE_PUBLIC_URL est défini, sinon référence interne."""
    from io import BytesIO as _BIO

    try:
        from django.conf import settings
        from django.urls import reverse

        base = getattr(settings, 'SITE_PUBLIC_URL', '').strip()
        if base:
            txt = base.rstrip('/') + reverse('achat:detail-commande', args=[commande.pk])
        else:
            txt = f'BC:{commande.numero_commande}|PK:{commande.pk}|ENT:{commande.entreprise_id}'
    except Exception:
        txt = f'BC:{commande.numero_commande}|PK:{commande.pk}'

    import qrcode
    from reportlab.lib.units import cm
    from reportlab.platypus import Image as RLImage

    buf = _BIO()
    qr = qrcode.QRCode(version=None, box_size=3, border=1)
    qr.add_data(txt)
    qr.make(fit=True)
    img = qr.make_image(fill_color='#111827', back_color='white')
    img.save(buf, format='PNG')
    buf.seek(0)
    return RLImage(buf, width=2.6 * cm, height=2.6 * cm)


def build_pdf_bc(commande):
    """PDF type document commercial : en-tête, émetteur / fournisseur, QR, lignes, totaux, signatures."""
    import os

    from django.conf import settings

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Image as RLImage
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buf = BytesIO()
    margin = 1.6 * cm
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin,
        bottomMargin=margin,
        title=f'BC {commande.numero_commande}',
    )

    W = A4[0] - 2 * margin
    styles = getSampleStyleSheet()

    title_doc = ParagraphStyle(
        'title_doc',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        textColor=colors.HexColor('#0F172A'),
        leading=14,
    )
    muted = ParagraphStyle(
        'muted',
        parent=styles['Normal'],
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor('#475569'),
    )
    body = ParagraphStyle(
        'body',
        parent=styles['Normal'],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#334155'),
    )
    small_white = ParagraphStyle(
        'small_white',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        textColor=colors.white,
        alignment=1,
    )

    sym = _symbole_devise(commande)
    ent = commande.entreprise
    four = commande.fournisseur
    bs = branche_siege_pour(ent)

    story = []

    # --- Logo entreprise (optionnel) ---
    logo_flow = None
    try:
        if ent.logo:
            pth = ent.logo.path
            if os.path.isfile(pth):
                logo_flow = RLImage(pth)
                logo_flow.restrictSize(2.5 * cm, 1.5 * cm)
    except Exception:
        logo_flow = None

    siege_txt = ''
    if bs:
        siege_txt = (
            f'<font size="9"><b>Branche siège social</b><br/>'
            f'{_esc_pdf(bs.nom)} — {_esc_pdf(bs.ville)} (code {_esc_pdf(bs.code_branche)})</font>'
        )

    emitter_detail_html = (
        f'<font size="11" color="#0F172A"><b>{_esc_pdf(ent.nom)}</b></font><br/><br/>'
        f'<font size="9">{_esc_pdf(ent.adresse_siege or "")}<br/><br/>'
        f'Tél. {_esc_pdf(ent.telephone)} · {_esc_pdf(ent.email)}<br/>'
        f'RCCM {_esc_pdf(ent.rccm)} · ID Nat. {_esc_pdf(ent.idnat)} · N° impôt {_esc_pdf(ent.numero_impot)}'
        f'</font>'
    )
    if siege_txt:
        emitter_detail_html += '<br/><br/>' + siege_txt

    emitter_compact_html = (
        f'<font size="13" color="#0F172A"><b>{_esc_pdf(ent.nom)}</b></font><br/>'
        f'<font size="8.5" color="#64748B">{_esc_pdf((ent.adresse_siege or "")[:280])}</font>'
    )

    left_stack = []
    if logo_flow:
        left_stack.append([logo_flow])
        left_stack.append([Spacer(1, 0.15 * cm)])
    left_stack.append([Paragraph(emitter_compact_html, body)])

    left_tbl = Table(left_stack, colWidths=[W * 0.52])
    left_tbl.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0)]))

    meta_lines = [
        [Paragraph('<font size="8" color="#64748B">N° bon de commande</font>', body),
         Paragraph(f'<b>{_esc_pdf(commande.numero_commande)}</b>', title_doc)],
        [Paragraph('<font size="8" color="#64748B">Date d\'émission</font>', body),
         Paragraph(_esc_pdf(commande.date_commande.strftime('%d/%m/%Y à %H:%M')), title_doc)],
        [Paragraph('<font size="8" color="#64748B">Livraison prévue</font>', body),
         Paragraph(
             _esc_pdf(
                 commande.date_livraison_prevue.strftime('%d/%m/%Y')
                 if commande.date_livraison_prevue
                 else '—'
             ),
             title_doc,
         )],
        [Paragraph('<font size="8" color="#64748B">Devise</font>', body),
         Paragraph(_esc_pdf(commande.devise.code if commande.devise_id else '—'), title_doc)],
    ]
    meta_tbl = Table(meta_lines, colWidths=[3.4 * cm, 4.2 * cm])
    meta_tbl.setStyle(
        TableStyle(
            [
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('BOTTOMPADDING', (0, 0), (-1, -2), 6),
            ]
        )
    )

    st_bg = colors.HexColor(_statut_couleur(commande.statut))
    statut_cell = Table(
        [[Paragraph(_esc_pdf(commande.get_statut_display()), small_white)]],
        colWidths=[3.6 * cm],
        rowHeights=[0.65 * cm],
    )
    statut_cell.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, -1), st_bg),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]
        )
    )

    qr = _qr_flowable(commande)
    right_bottom = Table([[meta_tbl], [Spacer(1, 0.2 * cm)], [statut_cell], [Spacer(1, 0.25 * cm)], [qr]])
    right_bottom.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'RIGHT')]))

    header_row = Table([[left_tbl, right_bottom]], colWidths=[W * 0.52, W * 0.48])
    header_row.setStyle(
        TableStyle(
            [
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(header_row)
    story.append(Spacer(1, 0.35 * cm))

    band = Table(
        [[Paragraph('<font color="white"><b>BON DE COMMANDE FOURNISSEUR</b></font>', body)]],
        colWidths=[W],
        rowHeights=[0.75 * cm],
    )
    band.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#1A56DB')),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]
        )
    )
    story.append(band)
    story.append(Spacer(1, 0.35 * cm))

    # Émetteur / Destinataire (deux colonnes comme facture)
    four_html = (
        f'<b><font color="#0F172A">{_esc_pdf(four.nom_societe)}</font></b><br/>'
        f'Réf. {_esc_pdf(four.code_fournisseur)}<br/><br/>'
        f'{_esc_pdf(four.adresse)}<br/>{_esc_pdf(four.ville)}<br/><br/>'
        f'Tél. {_esc_pdf(four.telephone)} · {_esc_pdf(four.email)}<br/>'
        f'Contact : {_esc_pdf(four.contact_nom)} · RCCM {_esc_pdf(four.rccm_id)}'
    )
    addr_tbl = Table(
        [
            [
                Paragraph('<font size="8" color="#64748B"><b>ÉMETTEUR</b></font><br/><br/>' + emitter_detail_html, body),
                Paragraph('<font size="8" color="#64748B"><b>FOURNISSEUR (DESTINATAIRE)</b></font><br/><br/>' + four_html, body),
            ]
        ],
        colWidths=[W / 2 - 0.1 * cm, W / 2 - 0.1 * cm],
    )
    addr_tbl.setStyle(
        TableStyle(
            [
                ('BOX', (0, 0), (-1, -1), 0.8, colors.HexColor('#E2E8F0')),
                ('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#F8FAFC')),
                ('BACKGROUND', (1, 0), (1, 0), colors.HexColor('#F8FAFC')),
                ('LEFTPADDING', (0, 0), (-1, -1), 10),
                ('RIGHTPADDING', (0, 0), (-1, -1), 10),
                ('TOPPADDING', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ]
        )
    )
    story.append(addr_tbl)
    story.append(Spacer(1, 0.45 * cm))

    dep_esc = (
        _esc_pdf(commande.depot_destination.nom)
        if commande.depot_destination_id
        else '(dépôt non renseigné)'
    )
    objet = (
        f'<i>Objet : commande de marchandises / prestations pour <b>{dep_esc}</b>'
    )
    if commande.pointdevente_destination_id:
        objet += f' — Point de vente : <b>{_esc_pdf(commande.pointdevente_destination.nom)}</b>'
    objet += '</i>'
    story.append(Paragraph(objet, muted))
    story.append(Spacer(1, 0.35 * cm))

    # Tableau lignes (style gris en-tête)
    hdr = [
        'Réf. / SKU',
        'Désignation',
        'Qté',
        'U.',
        f'PU HT ({sym})',
        'TVA %',
        f'Montant HT ({sym})',
    ]
    data_lines = [hdr]
    for ligne in commande.lignes.all():
        p = ligne.produit
        data_lines.append(
            [
                _esc_pdf((p.sku or '—')[:20]),
                _esc_pdf(p.nom[:120]),
                _esc_pdf(str(ligne.quantite_commandee)),
                _esc_pdf((ligne.unite or '')[:8]),
                _esc_pdf(f'{ligne.prix_unitaire_ht:.2f}'),
                _esc_pdf(f'{p.tva_taux:.1f}'),
                _esc_pdf(f'{ligne.sous_total_ht:.2f}'),
            ]
        )

    cw = [2.0 * cm, 6.3 * cm, 1.5 * cm, 1.0 * cm, 2.0 * cm, 1.3 * cm, 2.1 * cm]
    t_lines = Table(data_lines, colWidths=cw, repeatRows=1)
    t_lines.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E8EDF3')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#1E293B')),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 8),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.35, colors.HexColor('#CBD5E1')),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#FAFBFC')]),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(t_lines)
    story.append(Spacer(1, 0.45 * cm))

    tot_rows = [
        ['Sous-total HT', f'{commande.total_ht:.2f} {sym}'],
        ['Total TVA', f'{commande.total_tva:.2f} {sym}'],
        ['', ''],
        ['TOTAL TTC', f'{commande.total_ttc:.2f} {sym}'],
    ]
    tot_inner = Table(
        [[_esc_pdf(a), _esc_pdf(b)] for a, b in tot_rows],
        colWidths=[4.5 * cm, 4.2 * cm],
    )
    tot_inner.setStyle(
        TableStyle(
            [
                ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
                ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
                ('FONTNAME', (0, 0), (-1, -2), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -2), 9),
                ('LINEABOVE', (0, -1), (-1, -1), 1.2, colors.HexColor('#1A56DB')),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, -1), (-1, -1), 11),
                ('TEXTCOLOR', (0, -1), (-1, -1), colors.HexColor('#1A56DB')),
            ]
        )
    )
    tot_wrap = Table([['', tot_inner]], colWidths=[W - 8.8 * cm, 8.8 * cm])
    tot_wrap.setStyle(TableStyle([('ALIGN', (1, 0), (1, 0), 'RIGHT')]))
    story.append(tot_wrap)
    story.append(Spacer(1, 0.55 * cm))

    terms = (
        '<b>Conditions.</b> Ce document formalise la commande des articles ci-dessus aux conditions '
        'tarifaires et délais convenus avec le fournisseur. Les montants sont exprimés dans la devise '
        'indiquée ; la TVA est calculée selon le taux applicable à chaque ligne.'
    )
    story.append(Paragraph(_esc_pdf(terms), muted))
    story.append(Spacer(1, 0.35 * cm))

    if commande.notes:
        story.append(Paragraph(f'<b>Notes internes / bon :</b><br/>{_esc_pdf(commande.notes)}', body))
        story.append(Spacer(1, 0.35 * cm))

    creator = commande.cree_par
    sig_creator_img = None
    if creator:
        try:
            if getattr(creator, 'signature', None) and creator.signature:
                spath = creator.signature.path
                if os.path.isfile(spath):
                    sig_creator_img = RLImage(spath)
                    sig_creator_img.restrictSize(4.2 * cm, 2.6 * cm)
        except Exception:
            sig_creator_img = None

    left_sig_rows = [[Paragraph('<font size="8"><b>Pour ' + _esc_pdf(ent.nom) + '</b></font>', body)]]
    if creator:
        nom_cr = creator.get_full_name() or creator.get_username()
        left_sig_rows.append(
            [
                Paragraph(
                    '<font size="8">Émis par : <b>' + _esc_pdf(nom_cr) + '</b></font>',
                    body,
                )
            ]
        )
    left_sig_rows.append([Spacer(1, 0.12 * cm)])
    if sig_creator_img:
        left_sig_rows.append([sig_creator_img])
        left_sig_rows.append([Spacer(1, 0.1 * cm)])
        left_sig_rows.append(
            [
                Paragraph(
                    '<font size="8" color="#64748B">Signature et cachet</font>',
                    body,
                )
            ]
        )
    else:
        left_sig_rows.append([Spacer(1, 0.85 * cm)])
        left_sig_rows.append(
            [
                Paragraph(
                    '<font size="8" color="#64748B">Signature et cachet</font><br/>'
                    '<font size="8">_________________________</font>',
                    body,
                )
            ]
        )

    left_sig_tbl = Table(left_sig_rows, colWidths=[W / 2 - 0.15 * cm])
    left_sig_tbl.setStyle(
        TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0)])
    )

    right_sig_cell = Paragraph(
        '<font size="8"><b>Pour le fournisseur</b><br/>(' + _esc_pdf(four.nom_societe) + ')<br/><br/><br/>'
        'Signature<br/><br/>_________________________</font>',
        body,
    )
    sig = Table([[left_sig_tbl, right_sig_cell]], colWidths=[W / 2 - 0.15 * cm, W / 2 - 0.15 * cm])
    sig.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    story.append(sig)
    story.append(Spacer(1, 0.45 * cm))

    footer_txt = getattr(settings, 'BC_PDF_FOOTER_TEXT', None)
    if footer_txt:
        story.append(Paragraph(_esc_pdf(footer_txt).replace('\n', '<br/>'), muted))
    else:
        ft = f'{ent.nom} · Document généré automatiquement — Réf. interne PK-{commande.pk}'
        story.append(Paragraph(f'<font size="7.5" color="#94A3B8">{_esc_pdf(ft)}</font>', muted))

    doc.build(story)
    buf.seek(0)
    return buf.getvalue()
