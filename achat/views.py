import io
import json
from decimal import Decimal, InvalidOperation
from datetime import date, datetime

import openpyxl
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.db.models import Prefetch, Q
from django.http import HttpResponse
from openpyxl.styles import Alignment, Font, PatternFill

from utilisateur.decorators import login_requis
from entreprise.models import Entreprise, Depot, PointVente, Devise, Produit
from tiers.models import Fournisseur

from .bc_export import build_excel_bc, build_pdf_bc
from .models import OrdreAchat, LigneOrdreAchat, BonReception, LigneBonReception
from .forms import OrdreAchatForm, LigneOrdreAchatForm, BonReceptionForm, ImportLignesBcForm, LigneBonReceptionFormSet


# ───────────────────────────── helpers ─────────────────────────────

def _get_entreprise(user):
    """
    Entreprise liée au compte (même logique que la gestion utilisateurs / rôles).
    Branche d'affectation, sinon entreprise dont l'utilisateur est propriétaire (Entreprise.user).
    Pas de repli sur « la première entreprise » pour éviter les fuites de périmètre.
    """
    if getattr(user, 'branche_id', None):
        return user.branche.entreprise
    return Entreprise.objects.filter(user=user).first()


def _est_admin(user):
    return getattr(user, 'admin', False) or getattr(user, 'is_superuser', False)


def _pdv_ids_par_depot_json(entreprise, admin):
    """
    Pour chaque dépôt, liste des PK de points de vente actifs dont depot_source = ce dépôt
    (ordre alphabétique sur le nom du PDV — le premier est présélectionné côté client).
    """
    from entreprise.models import PointVente, Branche
    if admin:
        branches = Branche.objects.filter(est_actif=True)
    elif entreprise:
        branches = entreprise.branches.filter(est_actif=True)
    else:
        return json.dumps({})
    d = {}
    qs = PointVente.objects.filter(
        branche__in=branches,
        est_actif=True,
        depot_source__isnull=False,
    ).order_by('depot_source_id', 'nom')
    for pv in qs:
        d.setdefault(pv.depot_source_id, []).append(pv.pk)
    return json.dumps({str(k): v for k, v in d.items()})


def _exiger_entreprise_si_besoin(request, admin, entreprise, redirect_name='achat:liste-commandes'):
    """Pour un utilisateur non admin : entreprise obligatoire pour agir sur les commandes."""
    if admin or entreprise:
        return None
    messages.error(request, "Aucune entreprise associée à votre compte. Impossible d'utiliser les achats.")
    return redirect(redirect_name)


def _parse_decimal_bc(val, default=None):
    """Parse un nombre depuis Excel (float, int, str avec virgule ou point)."""
    if val is None or val == '':
        return default
    try:
        if isinstance(val, bool):
            return default
        if isinstance(val, (int, float)):
            return Decimal(str(val))
        return Decimal(str(val).replace(',', '.').strip().replace(' ', '').replace('\xa0', ''))
    except (InvalidOperation, ValueError, TypeError):
        return default


def _normalize_excel_cell_text(val):
    """
    Texte / SKU / code depuis Excel : évite '2.0' au lieu de '2', préserve les chaînes non numériques.
    """
    if val is None or val == '':
        return ''
    if isinstance(val, bool):
        return '1' if val else '0'
    if isinstance(val, float):
        if val != val:  # NaN
            return ''
        if val == int(val):
            return str(int(val))
        return str(val).strip()
    if isinstance(val, int):
        return str(val)
    s = str(val).strip()
    # Chaîne type "2.0" issue d'Excel
    if len(s) >= 3 and s.endswith('.0') and s[:-2].lstrip('-').isdigit():
        return s[:-2]
    return s


def _sku_lookup_entreprise(ent_id, sku_token):
    """Trouve un produit par SKU avec tolérance zéros à gauche (Excel numérique vs SKU texte)."""
    if not sku_token:
        return None
    tokens = {sku_token}
    if sku_token.isdigit():
        for pad in range(2, 8):
            tokens.add(sku_token.zfill(pad))
    qs = Produit.objects.filter(entreprise_id=ent_id, est_actif=True)
    for t in tokens:
        p = qs.filter(sku=t).first()
        if p:
            return p
    return None


def _parse_date_bc(val):
    if val is None or val == '':
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    s = str(val).strip()
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], '%Y-%m-%d').date()
    except ValueError:
        pass
    for fmt in ('%d/%m/%Y', '%d-%m-%Y'):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    return None


def _resolve_location_code(commande, code_raw):
    from entreprise.models import Location

    code = str(code_raw or '').strip()
    if not code:
        return None
    if commande.depot_destination_id:
        return Location.objects.filter(
            branche_id=commande.depot_destination.branche_id,
            code__iexact=code,
        ).first()
    branches = commande.entreprise.branches.all()
    return Location.objects.filter(branche__in=branches, code__iexact=code).first()


def _resolve_produit_bc(ent_id, data):
    cb = _normalize_excel_cell_text(data.get('code_barre'))
    sku_raw = _normalize_excel_cell_text(data.get('sku'))
    nv = data.get('nom')
    if nv is None or nv == '':
        nom = ''
    elif isinstance(nv, str):
        nom = nv.strip()
    else:
        nom = str(nv).strip()

    if not cb and not sku_raw and not nom:
        return None, 'missing'
    if cb:
        p = Produit.objects.select_related('entreprise').filter(code_barre=cb).first()
        if not p:
            return None, 'introuvable_cb'
        if p.entreprise_id != ent_id:
            return None, 'autre_entreprise_cb'
        if not p.est_actif:
            return None, 'inactif'
        return p, None
    if sku_raw:
        p = _sku_lookup_entreprise(ent_id, sku_raw)
        if p:
            return p, None
        # Excel a peut‑être dégradé le SKU (nombre) ou nom plus fiable
        if nom:
            p = Produit.objects.filter(
                entreprise_id=ent_id, nom__iexact=nom, est_actif=True
            ).first()
            if p:
                return p, None
        return None, 'introuvable_sku'
    p = Produit.objects.filter(entreprise_id=ent_id, nom__iexact=nom, est_actif=True).first()
    if not p:
        return None, 'introuvable_nom'
    return p, None


def _msg_erreur_produit(code):
    return {
        'introuvable_cb': 'code-barres inconnu.',
        'autre_entreprise_cb': 'ce code-barres appartient à un autre catalogue.',
        'introuvable_sku': (
            'SKU introuvable pour cette entreprise '
            '(Excel transforme souvent les SKU en nombre : formater la colonne en « Texte », ou vérifier le nom exact).'
        ),
        'introuvable_nom': 'nom de produit introuvable (exact, insensible à la casse).',
        'inactif': 'produit inactif.',
        'missing': 'renseigner au moins code_barre, sku ou nom.',
    }.get(code, code)


def _row_import_vide(row):
    if row is None:
        return True
    for v in row:
        if v is None:
            continue
        if isinstance(v, str):
            if v.strip():
                return False
            continue
        if v != '':
            return False
    return True


def _commande_export_base_qs():
    return OrdreAchat.objects.select_related(
        'entreprise',
        'fournisseur',
        'depot_destination__branche',
        'pointdevente_destination__branche',
        'devise',
        'cree_par',
    ).prefetch_related(
        Prefetch(
            'lignes',
            queryset=LigneOrdreAchat.objects.select_related(
                'produit',
                'location',
            ).order_by('pk'),
        )
    )


# ═══════════════════════════════════════════════════════════════════
#  ORDRES D'ACHAT
# ═══════════════════════════════════════════════════════════════════

@login_requis
def liste_commandes(request):
    entreprise = _get_entreprise(request.user)
    admin = _est_admin(request.user)
    if admin:
        qs = OrdreAchat.objects.all().select_related(
            'fournisseur',
            'entreprise',
            'depot_destination',
            'pointdevente_destination',
            'devise',
        )
    elif entreprise:
        qs = OrdreAchat.objects.filter(entreprise=entreprise).select_related(
            'fournisseur',
            'entreprise',
            'depot_destination',
            'pointdevente_destination',
            'devise',
        )
    else:
        qs = OrdreAchat.objects.none()

    q = request.GET.get('q', '')
    statut = request.GET.get('statut', '')
    if q:
        qs = qs.filter(
            Q(numero_commande__icontains=q)
            | Q(fournisseur__nom_societe__icontains=q)
            | Q(entreprise__nom__icontains=q)
            | Q(depot_destination__nom__icontains=q)
            | Q(pointdevente_destination__nom__icontains=q)
        )
    if statut:
        qs = qs.filter(statut=statut)

    ctx = {
        'commandes': qs,
        'actif': 'commandes',
        'STATUTS': OrdreAchat.STATUT_CHOICES,
        'q': q, 'statut': statut,
    }
    if request.htmx and request.htmx.target == 'table-container':
        return render(request, 'achat/commandes/partial/table.html', ctx)
    return render(request, 'achat/commandes/liste.html', ctx)


@login_requis
def detail_commande(request, pk):
    entreprise = _get_entreprise(request.user)
    admin = _est_admin(request.user)
    if admin:
        commande = get_object_or_404(OrdreAchat, pk=pk)
    else:
        redir = _exiger_entreprise_si_besoin(request, admin, entreprise)
        if redir:
            return redir
        commande = get_object_or_404(OrdreAchat, pk=pk, entreprise=entreprise)
    lignes = commande.lignes.select_related('produit', 'location')
    ctx = {
        'commande': commande,
        'lignes': lignes,
        'actif': 'commandes',
        'peut_modifier': commande.statut == 'BROUILLON',
        'import_lignes_form': ImportLignesBcForm() if commande.statut == 'BROUILLON' else None,
    }
    return render(request, 'achat/commandes/detail.html', ctx)


@login_requis
def export_commande_excel(request, pk):
    entreprise = _get_entreprise(request.user)
    admin = _est_admin(request.user)
    qs = _commande_export_base_qs()
    if admin:
        commande = get_object_or_404(qs, pk=pk)
    else:
        redir = _exiger_entreprise_si_besoin(request, admin, entreprise)
        if redir:
            return redir
        commande = get_object_or_404(qs, pk=pk, entreprise=entreprise)

    data = build_excel_bc(commande)
    fn = f"BC_{commande.numero_commande.replace('/', '-')}_donnees.xlsx"
    response = HttpResponse(
        data,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{fn}"'
    return response


@login_requis
def export_commande_pdf(request, pk):
    entreprise = _get_entreprise(request.user)
    admin = _est_admin(request.user)
    qs = _commande_export_base_qs()
    if admin:
        commande = get_object_or_404(qs, pk=pk)
    else:
        redir = _exiger_entreprise_si_besoin(request, admin, entreprise)
        if redir:
            return redir
        commande = get_object_or_404(qs, pk=pk, entreprise=entreprise)

    data = build_pdf_bc(commande)
    fn = f"BC_{commande.numero_commande.replace('/', '-')}.pdf"
    response = HttpResponse(data, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{fn}"'
    return response


@login_requis
def creer_commande(request):
    entreprise = _get_entreprise(request.user)
    admin = _est_admin(request.user)
    redir = _exiger_entreprise_si_besoin(request, admin, entreprise)
    if redir:
        return redir
    form = OrdreAchatForm(request.POST or None, entreprise=entreprise, admin=admin)
    if request.method == 'POST' and form.is_valid():
        commande = form.save(commit=False)
        # Admin : l'entreprise est déduite du fournisseur choisi
        if admin:
            commande.entreprise = commande.fournisseur.entreprise
        else:
            commande.entreprise = entreprise
        commande.cree_par = request.user
        commande.save()
        messages.success(request, f"Bon de commande {commande.numero_commande} créé.")
        return redirect('achat:detail-commande', pk=commande.pk)
    ctx = {
        'form': form,
        'actif': 'commandes',
        'titre': 'Nouveau bon de commande',
        'entreprise_affichage': None if admin else entreprise,
        'pdv_par_depot_json': _pdv_ids_par_depot_json(entreprise, admin),
    }
    return render(request, 'achat/commandes/form.html', ctx)


@login_requis
def modifier_commande(request, pk):
    entreprise = _get_entreprise(request.user)
    admin = _est_admin(request.user)
    if admin:
        commande = get_object_or_404(OrdreAchat, pk=pk, statut='BROUILLON')
    else:
        redir = _exiger_entreprise_si_besoin(request, admin, entreprise)
        if redir:
            return redir
        commande = get_object_or_404(OrdreAchat, pk=pk, entreprise=entreprise, statut='BROUILLON')
    form = OrdreAchatForm(request.POST or None, instance=commande, entreprise=entreprise, admin=admin)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, "Commande mise à jour.")
        return redirect('achat:detail-commande', pk=pk)
    ctx = {
        'form': form,
        'actif': 'commandes',
        'titre': 'Modifier la commande',
        'commande': commande,
        'entreprise_affichage': None if admin else entreprise,
        'pdv_par_depot_json': _pdv_ids_par_depot_json(entreprise, admin),
    }
    return render(request, 'achat/commandes/form.html', ctx)


@login_requis
def annuler_commande(request, pk):
    entreprise = _get_entreprise(request.user)
    admin = _est_admin(request.user)
    if admin:
        commande = get_object_or_404(OrdreAchat, pk=pk)
    else:
        redir = _exiger_entreprise_si_besoin(request, admin, entreprise)
        if redir:
            return redir
        commande = get_object_or_404(OrdreAchat, pk=pk, entreprise=entreprise)
    if request.method == 'POST' and commande.statut in ('BROUILLON', 'ENVOYE'):
        commande.statut = 'ANNULE'
        commande.save(update_fields=['statut'])
        messages.warning(request, f"Commande {commande.numero_commande} annulée.")
        return redirect('achat:liste-commandes')
    ctx = {'commande': commande}
    return render(request, 'achat/commandes/confirm_annuler.html', ctx)


# ── Lignes (HTMX inline) ──

@login_requis
def ajouter_ligne(request, pk):
    entreprise = _get_entreprise(request.user)
    admin = _est_admin(request.user)
    cmd_base = OrdreAchat.objects.select_related(
        'depot_destination__branche__entreprise',
        'entreprise',
    )
    if admin:
        commande = get_object_or_404(cmd_base, pk=pk, statut='BROUILLON')
    else:
        redir = _exiger_entreprise_si_besoin(request, admin, entreprise)
        if redir:
            return redir
        commande = get_object_or_404(
            cmd_base, pk=pk, entreprise=entreprise, statut='BROUILLON'
        )
    form = LigneOrdreAchatForm(request.POST or None, commande=commande)
    if request.method == 'POST' and form.is_valid():
        cleaned = form.cleaned_data
        _, mode = LigneOrdreAchat.creer_ou_fusionner(commande, cleaned)
        if mode == 'merged':
            messages.info(
                request,
                'Quantité ajoutée sur la ligne existante (même produit et mêmes informations).',
            )
        commande.recalculer_totaux()
        lignes = commande.lignes.select_related('produit')
        return render(request, 'achat/commandes/partial/lignes.html', {'commande': commande, 'lignes': lignes})
    return render(request, 'achat/commandes/partial/form_ligne.html', {'form': form, 'commande': commande})


@login_requis
def supprimer_ligne(request, pk):
    ligne = get_object_or_404(LigneOrdreAchat.objects.select_related('ordre_achat'), pk=pk)
    commande = ligne.ordre_achat
    entreprise = _get_entreprise(request.user)
    admin = _est_admin(request.user)
    if not admin:
        if not entreprise or commande.entreprise_id != entreprise.pk:
            messages.error(request, "Vous ne pouvez pas modifier cette commande.")
            lignes = commande.lignes.select_related('produit')
            return render(request, 'achat/commandes/partial/lignes.html', {'commande': commande, 'lignes': lignes})

    lignes = commande.lignes.select_related('produit')
    if commande.statut != 'BROUILLON':
        messages.warning(request, "Seuls les bons en brouillon peuvent être modifiés.")
        return render(request, 'achat/commandes/partial/lignes.html', {'commande': commande, 'lignes': lignes})

    qte_recue = ligne.quantite_recue if ligne.quantite_recue is not None else Decimal('0')
    if qte_recue != Decimal('0'):
        messages.warning(
            request,
            "Impossible de supprimer cette ligne : une quantité a déjà été réceptionnée.",
        )
        return render(request, 'achat/commandes/partial/lignes.html', {'commande': commande, 'lignes': lignes})

    ligne.delete()
    commande.recalculer_totaux()
    lignes = commande.lignes.select_related('produit')
    messages.success(request, "Ligne supprimée.")
    return render(request, 'achat/commandes/partial/lignes.html', {'commande': commande, 'lignes': lignes})


@login_requis
def import_lignes_commande(request, pk):
    """Import Excel des lignes sur un BC brouillon (catalogue = entreprise du bon)."""
    entreprise = _get_entreprise(request.user)
    admin = _est_admin(request.user)
    cmd_base = OrdreAchat.objects.select_related(
        'depot_destination__branche__entreprise',
        'entreprise',
    )
    if admin:
        commande = get_object_or_404(cmd_base, pk=pk, statut='BROUILLON')
    else:
        redir = _exiger_entreprise_si_besoin(request, admin, entreprise)
        if redir:
            return redir
        commande = get_object_or_404(
            cmd_base, pk=pk, entreprise=entreprise, statut='BROUILLON'
        )

    if request.method != 'POST':
        return redirect('achat:detail-commande', pk=pk)

    form = ImportLignesBcForm(request.POST, request.FILES)
    if not form.is_valid():
        for err in form.errors.get('fichier', []):
            messages.error(request, err)
        return redirect('achat:detail-commande', pk=pk)

    ent_id = commande.entreprise_id
    fichier = form.cleaned_data['fichier']
    merged = created = skipped = 0
    errors = []

    try:
        wb = openpyxl.load_workbook(fichier, data_only=True)
        ws = wb.active
        headers = [
            str(c.value).strip().lower().replace(' ', '_') if c.value else ''
            for c in ws[1]
        ]

        with transaction.atomic():
            for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                data = dict(zip(headers, row))
                if _row_import_vide(row):
                    skipped += 1
                    continue

                qte = _parse_decimal_bc(data.get('quantite_commandee'))
                prix = _parse_decimal_bc(data.get('prix_unitaire_ht'))
                if qte is None or qte <= 0:
                    errors.append(f"Ligne {row_idx}: quantité commandée invalide ou manquante.")
                    continue
                if prix is None or prix < 0:
                    errors.append(f"Ligne {row_idx}: prix unitaire HT invalide ou manquant.")
                    continue

                produit, err_code = _resolve_produit_bc(ent_id, data)
                if not produit:
                    hint = _msg_erreur_produit(err_code)
                    errors.append(f"Ligne {row_idx}: {hint}")
                    continue

                loc = _resolve_location_code(commande, data.get('location_code'))
                cleaned = {
                    'produit': produit,
                    'quantite_commandee': qte,
                    'prix_unitaire_ht': prix,
                    'unite': str(data.get('unite') or '').strip(),
                    'lot_batch': str(data.get('lot_batch') or '').strip(),
                    'dateproduction': _parse_date_bc(data.get('dateproduction')),
                    'dateexpiration': _parse_date_bc(data.get('dateexpiration')),
                    'location': loc,
                }

                if cleaned['location'] is None and str(data.get('location_code') or '').strip():
                    errors.append(
                        f"Ligne {row_idx}: emplacement « {data.get('location_code')} » introuvable pour ce dépôt / cette entreprise."
                    )
                    continue

                _, mode = LigneOrdreAchat.creer_ou_fusionner(commande, cleaned)
                if mode == 'merged':
                    merged += 1
                else:
                    created += 1

            commande.recalculer_totaux()

    except Exception as e:
        messages.error(request, f"Lecture du fichier impossible : {e}")
        return redirect('achat:detail-commande', pk=pk)

    if created or merged:
        messages.success(
            request,
            f"{created} ligne(s) créée(s), {merged} fusion(s) avec une ligne existante.",
        )
    if errors:
        messages.warning(
            request,
            f"{len(errors)} ligne(s) en erreur — détails : « {' ; '.join(errors[:8])}{'…' if len(errors) > 8 else ''} »",
        )
    if skipped and not (created or merged) and not errors:
        messages.info(request, "Aucune ligne importée (lignes vides ignorées).")

    return redirect('achat:detail-commande', pk=pk)


@login_requis
def telecharger_modele_lignes_bc(request, pk):
    entreprise = _get_entreprise(request.user)
    admin = _est_admin(request.user)
    if admin:
        commande = get_object_or_404(OrdreAchat, pk=pk, statut='BROUILLON')
    else:
        redir = _exiger_entreprise_si_besoin(request, admin, entreprise)
        if redir:
            return redir
        commande = get_object_or_404(OrdreAchat, pk=pk, entreprise=entreprise, statut='BROUILLON')

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Lignes_BC'

    # Pas de code-barres : SKU = code seul (référence unique par entreprise), pas un libellé type SKU-Nom-UM.
    headers = [
        'sku',
        'nom',
        'quantite_commandee',
        'prix_unitaire_ht',
        'unite',
        'lot_batch',
        'dateproduction',
        'dateexpiration',
        'location_code',
    ]
    h_font = Font(bold=True, color='FFFFFF')
    h_fill = PatternFill('solid', fgColor='1A56DB')
    h_align = Alignment(horizontal='center', vertical='center')

    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = h_font
        cell.fill = h_fill
        cell.alignment = h_align
        ws.column_dimensions[cell.column_letter].width = 22

    lignes_list = list(
        commande.lignes.select_related('produit', 'location').order_by('pk')
    )
    if lignes_list:
        for ligne in lignes_list:
            p = ligne.produit
            sku_val = (p.sku or '').strip()
            ws.append([
                sku_val,
                p.nom,
                ligne.quantite_commandee,
                ligne.prix_unitaire_ht,
                ligne.unite or '',
                ligne.lot_batch or '',
                ligne.dateproduction,
                ligne.dateexpiration,
                ligne.location.code if ligne.location_id else '',
            ])
    else:
        ws.append([
            'MON-SKU-001',
            'Exemple produit',
            10,
            2.5,
            'PCS',
            '',
            '',
            '',
            '',
        ])
        ws.append([
            'REF-002',
            'Autre exemple',
            5,
            100,
            'KG',
            'LOT-A',
            '',
            '',
            '',
        ])

    ws2 = wb.create_sheet('Instructions')
    ws2.column_dimensions['A'].width = 22
    ws2.column_dimensions['B'].width = 12
    ws2.column_dimensions['C'].width = 72
    ws2.append(['Colonne', 'Obligatoire', 'Description'])
    ws2['A1'].font = Font(bold=True)
    ws2['B1'].font = Font(bold=True)
    ws2['C1'].font = Font(bold=True)
    for row in [
        (
            'sku',
            'NON',
            "Code SKU uniquement (comme en catalogue), sans nom ni unité — unique par entreprise. "
            "Si renseigné : identifie le produit en priorité.",
        ),
        (
            'nom',
            'NON',
            "Si SKU vide : nom exact du produit (catalogue de l'entreprise du BC). Au moins sku ou nom doit identifier le produit.",
        ),
        ('quantite_commandee', 'OUI', 'Quantité à commander (nombre > 0).'),
        ('prix_unitaire_ht', 'OUI', 'Prix unitaire hors taxes.'),
        ('unite', 'NON', 'Unité de commande (ex. PCS, KG) — défaut vide.'),
        ('lot_batch', 'NON', 'Lot / batch — défaut vide.'),
        ('dateproduction', 'NON', 'Date AAAA-MM-JJ ou JJ/MM/AAAA — optionnel.'),
        ('dateexpiration', 'NON', 'Idem — optionnel.'),
        ('location_code', 'NON', "Code d'emplacement (Location) du dépôt / de l'entreprise — optionnel."),
        ('—', '—', "Colonne « code_barres » absente : l'import peut encore accepter une colonne code_barre pour compatibilité."),
    ]:
        ws2.append(row)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    safe_num = commande.numero_commande.replace('/', '-')
    suffix = 'lignes' if lignes_list else 'modele'
    response['Content-Disposition'] = (
        f'attachment; filename="{suffix}_lignes_bc_{safe_num}.xlsx"'
    )
    return response


# ═══════════════════════════════════════════════════════════════════
#  RECEPTIONS
# ═══════════════════════════════════════════════════════════════════

@login_requis
def liste_receptions(request):
    entreprise = _get_entreprise(request.user)
    admin = _est_admin(request.user)
    if admin:
        qs = BonReception.objects.all().select_related('ordre_achat__fournisseur', 'depot_destination', 'recu_par', 'ordre_achat__entreprise')
    elif entreprise:
        qs = BonReception.objects.filter(
            ordre_achat__entreprise=entreprise
        ).select_related('ordre_achat__fournisseur', 'depot_destination', 'recu_par')
    else:
        qs = BonReception.objects.none()

    q = request.GET.get('q', '')
    statut = request.GET.get('statut', '')
    if q:
        qs = qs.filter(
            Q(numero_reception__icontains=q) |
            Q(ordre_achat__numero_commande__icontains=q) |
            Q(ordre_achat__fournisseur__nom_societe__icontains=q)
        )
    if statut:
        qs = qs.filter(statut=statut)

    ctx = {
        'receptions': qs,
        'actif': 'receptions',
        'STATUTS': BonReception.STATUT_CHOICES,
        'q': q, 'statut': statut,
    }
    if request.htmx and request.htmx.target == 'table-container':
        return render(request, 'achat/receptions/partial/table.html', ctx)
    return render(request, 'achat/receptions/liste.html', ctx)


@login_requis
def creer_reception(request, ordre_pk):
    entreprise = _get_entreprise(request.user)
    admin = _est_admin(request.user)
    if admin:
        commande = get_object_or_404(OrdreAchat, pk=ordre_pk, statut__in=['ENVOYE', 'RECU_PARTIEL'])
    else:
        redir = _exiger_entreprise_si_besoin(request, admin, entreprise, redirect_name='achat:liste-receptions')
        if redir:
            return redir
        commande = get_object_or_404(
            OrdreAchat, pk=ordre_pk, entreprise=entreprise,
            statut__in=['ENVOYE', 'RECU_PARTIEL']
        )
    lignes_commande = commande.lignes.select_related('produit')

    if request.method == 'POST':
        form = BonReceptionForm(request.POST, commande=commande)
        if form.is_valid():
            with transaction.atomic():
                reception = form.save(commit=False)
                reception.ordre_achat = commande
                reception.recu_par = request.user
                reception.save()

                total_recu = 0
                total_commande = lignes_commande.count()

                for ligne in lignes_commande:
                    qte_key = f'qte_{ligne.pk}'
                    ecart_key = f'ecart_{ligne.pk}'
                    motif_key = f'motif_{ligne.pk}'
                    lot_key = f'lot_{ligne.pk}'

                    qte = request.POST.get(qte_key)
                    if qte:
                        try:
                            qte = float(qte)
                        except ValueError:
                            qte = 0
                        ecartee = float(request.POST.get(ecart_key, 0) or 0)
                        LigneBonReception.objects.create(
                            bon_reception=reception,
                            ligne_ordre_achat=ligne,
                            quantite_recue_effective=qte,
                            quantite_ecartee=ecartee,
                            motif_ecart=request.POST.get(motif_key, ''),
                            lot_batch=request.POST.get(lot_key, ''),
                        )
                        ligne.quantite_recue += qte
                        ligne.save(update_fields=['quantite_recue'])
                        if ligne.quantite_recue >= ligne.quantite_commandee:
                            total_recu += 1

                # Mise à jour statut de la commande
                if total_recu >= total_commande:
                    commande.statut = 'RECU_TOTAL'
                elif total_recu > 0:
                    commande.statut = 'RECU_PARTIEL'
                commande.save(update_fields=['statut'])

                messages.success(request, f"Bon de réception {reception.numero_reception} créé.")
                return redirect('achat:detail-reception', pk=reception.pk)
    else:
        form = BonReceptionForm(commande=commande)

    ctx = {
        'form': form,
        'commande': commande,
        'lignes_commande': lignes_commande,
        'actif': 'receptions',
    }
    return render(request, 'achat/receptions/form.html', ctx)


@login_requis
def detail_reception(request, pk):
    entreprise = _get_entreprise(request.user)
    admin = _est_admin(request.user)
    if admin:
        reception = get_object_or_404(BonReception, pk=pk)
    else:
        redir = _exiger_entreprise_si_besoin(request, admin, entreprise, redirect_name='achat:liste-receptions')
        if redir:
            return redir
        reception = get_object_or_404(BonReception, pk=pk, ordre_achat__entreprise=entreprise)
    lignes = reception.lignes.select_related('ligne_ordre_achat__produit', 'location')
    ctx = {'reception': reception, 'lignes': lignes, 'actif': 'receptions'}
    return render(request, 'achat/receptions/detail.html', ctx)


@login_requis
def valider_reception(request, pk):
    entreprise = _get_entreprise(request.user)
    admin = _est_admin(request.user)
    if admin:
        reception = get_object_or_404(BonReception, pk=pk, statut='EN_COURS')
    else:
        redir = _exiger_entreprise_si_besoin(request, admin, entreprise, redirect_name='achat:liste-receptions')
        if redir:
            return redir
        reception = get_object_or_404(BonReception, pk=pk, ordre_achat__entreprise=entreprise, statut='EN_COURS')
    if request.method == 'POST':
        reception.statut = 'VALIDE'
        reception.save(update_fields=['statut'])
        messages.success(request, f"Réception {reception.numero_reception} validée.")
        return redirect('achat:detail-reception', pk=pk)
    ctx = {'reception': reception}
    return render(request, 'achat/receptions/confirm_valider.html', ctx)
