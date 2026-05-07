from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Sum, Count
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from entreprise.models import Devise, PointVente
from stock.access import get_entreprise_utilisateur, utilisateur_est_admin
from tiers.models import Client
from utilisateur.acces_metier import utilisateur_peut_permission
from utilisateur.decorators import login_requis

from .models import SessionCaisse, TransactionCaisse


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _peut(user, code):
    return utilisateur_peut_permission(user, code)


def _pdvs_accessibles(user, entreprise, admin):
    from stock.access import queryset_points_vente_visibles
    return queryset_points_vente_visibles(user, entreprise, admin)


def _session_ouverte(pdv):
    return SessionCaisse.objects.filter(point_vente=pdv, statut='OUVERTE').first()


# ─────────────────────────────────────────────
# Dashboard caisse
# ─────────────────────────────────────────────

@login_requis
def dashboard_caisse(request):
    if not _peut(request.user, 'acces_module_caisse'):
        messages.error(request, 'Accès refusé.')
        return redirect('entreprise:dashboard')

    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    pdvs       = _pdvs_accessibles(request.user, entreprise, admin)

    sessions_ouvertes = SessionCaisse.objects.filter(
        point_vente__in=pdvs, statut='OUVERTE'
    ).select_related('point_vente', 'ouvert_par', 'devise')

    sessions_attente = SessionCaisse.objects.filter(
        point_vente__in=pdvs, statut='EN_ATTENTE_CLOTURE'
    ).select_related('point_vente', 'ouvert_par', 'devise')

    # Avances RH approuvées en attente de décaissement sur les PDVs accessibles
    from rh.models import AvanceSalaire
    nb_avances_a_decaisser = AvanceSalaire.objects.filter(
        statut='APPROUVEE', point_vente__in=pdvs
    ).count()

    return render(request, 'caisse/dashboard.html', {
        'actif':                 'caisse',
        'pdvs':                  pdvs,
        'sessions_ouvertes':     sessions_ouvertes,
        'sessions_attente':      sessions_attente,
        'peut_ouvrir':           _peut(request.user, 'ouvrir_session_caisse'),
        'peut_approuver':        _peut(request.user, 'approuver_cloture_caisse'),
        'nb_avances_a_decaisser': nb_avances_a_decaisser,
    })


# ─────────────────────────────────────────────
# Liste sessions
# ─────────────────────────────────────────────

@login_requis
def liste_sessions(request):
    if not _peut(request.user, 'acces_module_caisse'):
        messages.error(request, 'Accès refusé.')
        return redirect('entreprise:dashboard')

    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    pdvs       = _pdvs_accessibles(request.user, entreprise, admin)

    qs = SessionCaisse.objects.filter(point_vente__in=pdvs).select_related(
        'point_vente', 'ouvert_par', 'approuve_par', 'devise'
    )

    statut_f = (request.GET.get('statut') or '').strip()
    pdv_f    = (request.GET.get('pdv')    or '').strip()
    if statut_f:
        qs = qs.filter(statut=statut_f)
    if pdv_f.isdigit():
        qs = qs.filter(point_vente_id=int(pdv_f))

    return render(request, 'caisse/liste_sessions.html', {
        'actif':         'caisse',
        'sessions':      qs[:200],
        'pdvs':          pdvs,
        'statuts':       SessionCaisse.STATUTS,
        'filt_statut':   statut_f,
        'filt_pdv':      pdv_f,
        'peut_ouvrir':   _peut(request.user, 'ouvrir_session_caisse'),
    })


# ─────────────────────────────────────────────
# Ouvrir une session
# ─────────────────────────────────────────────

@login_requis
def ouvrir_session(request):
    if not _peut(request.user, 'ouvrir_session_caisse'):
        messages.error(request, 'Accès refusé.')
        return redirect('caisse:dashboard')

    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    pdvs       = _pdvs_accessibles(request.user, entreprise, admin)
    devises    = Devise.objects.filter(est_active=True) if hasattr(Devise, 'est_active') else Devise.objects.all()

    if request.method == 'POST':
        pdv_pk        = request.POST.get('point_vente', '').strip()
        devise_pk     = request.POST.get('devise', '').strip()
        fond_raw      = request.POST.get('fond_ouverture', '0').strip().replace(',', '.')

        erreurs = []
        pdv    = pdvs.filter(pk=int(pdv_pk)).first() if pdv_pk.isdigit() else None
        devise = Devise.objects.filter(pk=int(devise_pk)).first() if devise_pk.isdigit() else None

        if not pdv:    erreurs.append('Point de vente invalide.')
        if not devise: erreurs.append('Devise invalide.')
        fond = Decimal('0')
        try:
            fond = Decimal(fond_raw)
            if fond < 0:
                erreurs.append('Le fond de départ ne peut pas être négatif.')
        except Exception:
            erreurs.append('Fond de départ invalide.')

        if pdv and SessionCaisse.objects.filter(point_vente=pdv, statut='OUVERTE').exists():
            erreurs.append(f'Une session est déjà ouverte pour « {pdv.nom} ».')

        if erreurs:
            for e in erreurs:
                messages.error(request, e)
        else:
            session = SessionCaisse.objects.create(
                point_vente=pdv,
                devise=devise,
                ouvert_par=request.user,
                fond_ouverture=fond,
                statut='OUVERTE',
            )
            messages.success(request, f'Session ouverte pour {pdv.nom}.')
            return redirect('caisse:detail-session', pk=session.pk)

    return render(request, 'caisse/ouvrir_session.html', {
        'actif':   'caisse',
        'pdvs':    pdvs,
        'devises': devises,
    })


# ─────────────────────────────────────────────
# Détail session
# ─────────────────────────────────────────────

@login_requis
def detail_session(request, pk):
    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    pdvs       = _pdvs_accessibles(request.user, entreprise, admin)

    session = get_object_or_404(
        SessionCaisse.objects.select_related('point_vente', 'ouvert_par', 'approuve_par', 'devise'),
        pk=pk, point_vente__in=pdvs,
    )
    transactions = session.transactions.select_related(
        'effectue_par', 'devise', 'facture', 'depense', 'retour_vente'
    ).order_by('-date_transaction')

    # Breakdown par mode paiement (encaissements)
    breakdown = (
        session.transactions.filter(type_transaction='ENCAISSEMENT')
        .values('mode_paiement')
        .annotate(total=Sum('montant'))
        .order_by('-total')
    )

    # Factures à crédit / partielles validées pendant cette session
    from django.db.models import Q
    from facturation.models import Facture
    date_fin = session.date_cloture or timezone.now()
    factures_credit_qs = Facture.objects.filter(
        point_vente=session.point_vente,
        statut='VALIDEE',
        date_facture__gte=session.date_ouverture,
        date_facture__lte=date_fin,
    ).filter(Q(mode_paiement='CREDIT') | Q(reste_a_payer__gt=0))

    agg_credit = factures_credit_qs.aggregate(
        total_dette=Sum('reste_a_payer'),
        nb_credit=Count('pk'),
    )
    total_credit    = agg_credit['total_dette'] or Decimal('0')
    nb_credit       = agg_credit['nb_credit']   or 0
    factures_credit = factures_credit_qs.select_related('client', 'devise').order_by('-date_facture')[:50]

    peut_cloturer  = _peut(request.user, 'cloturer_session_caisse') and session.statut == 'OUVERTE'
    peut_approuver = _peut(request.user, 'approuver_cloture_caisse') and session.statut == 'EN_ATTENTE_CLOTURE'
    peut_depot_ret = _peut(request.user, 'depot_retrait_caisse') and session.statut == 'OUVERTE'

    return render(request, 'caisse/detail_session.html', {
        'actif':             'caisse',
        'session':           session,
        'transactions':      transactions,
        'breakdown':         breakdown,
        'modes_labels':      dict(TransactionCaisse.MODES),
        'total_credit':      total_credit,
        'nb_credit':         nb_credit,
        'factures_credit':   factures_credit,
        'peut_cloturer':     peut_cloturer,
        'peut_approuver':    peut_approuver,
        'peut_depot_ret':    peut_depot_ret,
    })


# ─────────────────────────────────────────────
# Dépôt / Retrait manuel
# ─────────────────────────────────────────────

@login_requis
@require_POST
def depot_retrait(request, pk):
    if not _peut(request.user, 'depot_retrait_caisse'):
        messages.error(request, 'Droits insuffisants.')
        return redirect('caisse:detail-session', pk=pk)

    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    pdvs       = _pdvs_accessibles(request.user, entreprise, admin)
    session    = get_object_or_404(SessionCaisse, pk=pk, point_vente__in=pdvs, statut='OUVERTE')

    type_t  = request.POST.get('type_transaction', '').strip()
    montant_raw = request.POST.get('montant', '').strip().replace(',', '.')
    motif   = request.POST.get('motif', '').strip()

    if type_t not in ('DEPOT', 'RETRAIT'):
        messages.error(request, 'Type invalide.')
        return redirect('caisse:detail-session', pk=pk)
    try:
        montant = Decimal(montant_raw)
        if montant <= 0:
            raise ValueError
    except Exception:
        messages.error(request, 'Montant invalide.')
        return redirect('caisse:detail-session', pk=pk)

    TransactionCaisse.objects.create(
        session=session,
        type_transaction=type_t,
        mode_paiement='ESPECES',
        montant=montant,
        devise=session.devise,
        motif=motif or ('Dépôt manuel' if type_t == 'DEPOT' else 'Retrait manuel'),
        effectue_par=request.user,
    )
    label = 'Dépôt' if type_t == 'DEPOT' else 'Retrait'
    messages.success(request, f'{label} de {montant} enregistré.')
    return redirect('caisse:detail-session', pk=pk)


# ─────────────────────────────────────────────
# Soumettre la clôture
# ─────────────────────────────────────────────

@login_requis
@require_POST
def soumettre_cloture(request, pk):
    if not _peut(request.user, 'cloturer_session_caisse'):
        messages.error(request, 'Droits insuffisants.')
        return redirect('caisse:detail-session', pk=pk)

    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    pdvs       = _pdvs_accessibles(request.user, entreprise, admin)
    session    = get_object_or_404(SessionCaisse, pk=pk, point_vente__in=pdvs, statut='OUVERTE')

    fond_raw = request.POST.get('fond_reel_cloture', '').strip().replace(',', '.')
    commentaire = request.POST.get('commentaire_cloture', '').strip()

    try:
        fond_reel = Decimal(fond_raw)
        if fond_reel < 0:
            raise ValueError
    except Exception:
        messages.error(request, 'Montant de clôture invalide.')
        return redirect('caisse:detail-session', pk=pk)

    session.fond_reel_cloture   = fond_reel
    session.commentaire_cloture = commentaire
    session.statut              = 'EN_ATTENTE_CLOTURE'
    session.soumis_cloture_le   = timezone.now()
    session.save(update_fields=['fond_reel_cloture', 'commentaire_cloture', 'statut', 'soumis_cloture_le'])
    messages.success(request, 'Clôture soumise au manager pour approbation.')
    return redirect('caisse:detail-session', pk=pk)


# ─────────────────────────────────────────────
# Approuver la clôture (manager)
# ─────────────────────────────────────────────

@login_requis
@require_POST
def approuver_cloture(request, pk):
    if not _peut(request.user, 'approuver_cloture_caisse'):
        messages.error(request, 'Droits insuffisants.')
        return redirect('caisse:detail-session', pk=pk)

    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    pdvs       = _pdvs_accessibles(request.user, entreprise, admin)
    session    = get_object_or_404(SessionCaisse, pk=pk, point_vente__in=pdvs, statut='EN_ATTENTE_CLOTURE')

    commentaire = request.POST.get('commentaire_manager', '').strip()
    session.statut            = 'CLOSE'
    session.approuve_par      = request.user
    session.commentaire_manager = commentaire
    session.date_approbation  = timezone.now()
    session.date_cloture      = timezone.now()
    session.save(update_fields=['statut', 'approuve_par', 'commentaire_manager', 'date_approbation', 'date_cloture'])
    messages.success(request, f'Session clôturée. Écart : {session.ecart_cloture}.')
    return redirect('caisse:detail-session', pk=pk)


# ─────────────────────────────────────────────
# Rejeter la clôture (manager)
# ─────────────────────────────────────────────

@login_requis
@require_POST
def rejeter_cloture(request, pk):
    if not _peut(request.user, 'approuver_cloture_caisse'):
        messages.error(request, 'Droits insuffisants.')
        return redirect('caisse:detail-session', pk=pk)

    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    pdvs       = _pdvs_accessibles(request.user, entreprise, admin)
    session    = get_object_or_404(SessionCaisse, pk=pk, point_vente__in=pdvs, statut='EN_ATTENTE_CLOTURE')

    commentaire = request.POST.get('commentaire_manager', '').strip()
    if not commentaire:
        messages.error(request, 'Un commentaire de rejet est obligatoire.')
        return redirect('caisse:detail-session', pk=pk)

    session.statut              = 'OUVERTE'   # on réouvre pour correction
    session.commentaire_manager = commentaire
    session.fond_reel_cloture   = None
    session.soumis_cloture_le   = None
    session.save(update_fields=['statut', 'commentaire_manager', 'fond_reel_cloture', 'soumis_cloture_le'])
    messages.warning(request, 'Clôture rejetée. La session est réouverte pour correction.')
    return redirect('caisse:detail-session', pk=pk)


# ─────────────────────────────────────────────
# Rapport imprimable
# ─────────────────────────────────────────────

@login_requis
def compte_client(request, client_pk):
    """Compte client complet : factures, retours, remboursements, dettes."""
    if not _peut(request.user, 'acces_module_caisse'):
        messages.error(request, 'Accès refusé.')
        return redirect('entreprise:dashboard')

    from facturation.models import Facture, RetourVente

    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    pdvs       = _pdvs_accessibles(request.user, entreprise, admin)

    client = get_object_or_404(Client, pk=client_pk, entreprise=entreprise)

    pdv_f    = (request.GET.get('pdv')    or '').strip()
    statut_f = (request.GET.get('statut') or '').strip()

    # ── Factures ─────────────────────────────────────────────────────────────
    factures_qs = Facture.objects.filter(
        client=client, point_vente__in=pdvs
    ).select_related('point_vente', 'devise', 'vendeur').order_by('-date_facture')
    if pdv_f.isdigit():
        factures_qs = factures_qs.filter(point_vente_id=int(pdv_f))
    if statut_f:
        factures_qs = factures_qs.filter(statut=statut_f)

    # ── Retours ───────────────────────────────────────────────────────────────
    retours_qs = RetourVente.objects.filter(
        client=client, point_vente__in=pdvs
    ).select_related('facture_origine', 'point_vente', 'devise').order_by('-date_retour')
    if pdv_f.isdigit():
        retours_qs = retours_qs.filter(point_vente_id=int(pdv_f))

    # ── Agrégats financiers ───────────────────────────────────────────────────
    agg_fact = Facture.objects.filter(client=client, point_vente__in=pdvs).aggregate(
        total_facture  = Sum('total_ttc'),
        total_paye     = Sum('montant_paye'),
        total_dette    = Sum('reste_a_payer'),
        nb_factures    = Count('pk'),
        nb_avec_dette  = Count('pk', filter=Q(reste_a_payer__gt=0)),
    )
    agg_ret = RetourVente.objects.filter(
        client=client, point_vente__in=pdvs, statut='APPROUVE'
    ).aggregate(
        total_rembourse = Sum('total_ttc'),
        nb_retours      = Count('pk'),
    )

    return render(request, 'caisse/compte_client.html', {
        'actif':           'caisse',
        'client':          client,
        'factures':        factures_qs,
        'retours':         retours_qs,
        'pdvs':            pdvs,
        'statuts_facture': Facture.STATUTS_FACTURE,
        'filt_pdv':        pdv_f,
        'filt_statut':     statut_f,
        # KPIs
        'total_facture':   agg_fact['total_facture']  or Decimal('0'),
        'total_paye':      agg_fact['total_paye']     or Decimal('0'),
        'total_dette':     agg_fact['total_dette']    or Decimal('0'),
        'total_rembourse': agg_ret['total_rembourse'] or Decimal('0'),
        'nb_factures':     agg_fact['nb_factures']    or 0,
        'nb_avec_dette':   agg_fact['nb_avec_dette']  or 0,
        'nb_retours':      agg_ret['nb_retours']      or 0,
    })


def _tx_base_scope(pdvs, pdv_f='', type_f=''):
    """
    Queryset de base : toutes les transactions de caisse dans le périmètre
    accessible, annoté avec eff_client_id = COALESCE(client, facture.client,
    retour_vente.client) pour capturer les transactions dont le client est
    indiqué dans le document source et non directement sur la transaction.
    """
    qs = TransactionCaisse.objects.filter(
        session__point_vente__in=pdvs,
    ).annotate(
        eff_client_id=Coalesce(
            'client_id',
            'facture__client_id',
            'retour_vente__client_id',
        )
    )
    if pdv_f.isdigit():
        qs = qs.filter(session__point_vente_id=int(pdv_f))
    if type_f:
        qs = qs.filter(type_transaction=type_f)
    return qs


@login_requis
def api_autocomplete_clients(request):
    """AJAX : suggestions clients de l'entreprise (basé sur les factures accessibles)."""
    from facturation.models import Facture

    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    pdvs       = _pdvs_accessibles(request.user, entreprise, admin)

    q     = (request.GET.get('q')   or '').strip()
    pdv_f = (request.GET.get('pdv') or '').strip()

    # Clients ayant au moins une facture dans le périmètre
    fact_qs = Facture.objects.filter(point_vente__in=pdvs)
    if pdv_f.isdigit():
        fact_qs = fact_qs.filter(point_vente_id=int(pdv_f))
    ids = fact_qs.values_list('client_id', flat=True).distinct()

    qs = Client.objects.filter(pk__in=ids)
    if q:
        qs = qs.filter(
            Q(nom__icontains=q) | Q(code_client__icontains=q) | Q(telephone__icontains=q)
        )

    results = [
        {'id': c.pk, 'nom': c.nom, 'code': c.code_client, 'tel': c.telephone or ''}
        for c in qs.order_by('nom')[:20]
    ]
    return JsonResponse({'results': results})


@login_requis
def liste_clients_caisse(request):
    """Comptes clients — basé sur les factures (pas les transactions caisse)."""
    if not _peut(request.user, 'acces_module_caisse'):
        messages.error(request, 'Accès refusé.')
        return redirect('entreprise:dashboard')

    from facturation.models import Facture, RetourVente

    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    pdvs       = _pdvs_accessibles(request.user, entreprise, admin)

    q       = (request.GET.get('q')       or '').strip()
    pdv_f   = (request.GET.get('pdv')     or '').strip()
    dette_f = (request.GET.get('dette')   or '').strip()  # '1' = avec dette uniquement

    # Clients ayant au moins une facture dans le périmètre accessible
    fact_base = Facture.objects.filter(point_vente__in=pdvs)
    if pdv_f.isdigit():
        fact_base = fact_base.filter(point_vente_id=int(pdv_f))

    ids_avec_facture = fact_base.values_list('client_id', flat=True).distinct()

    clients_qs = Client.objects.filter(pk__in=ids_avec_facture, entreprise=entreprise)
    if q:
        clients_qs = clients_qs.filter(
            Q(nom__icontains=q) | Q(code_client__icontains=q) | Q(telephone__icontains=q)
        )
    clients_list = list(clients_qs.order_by('nom'))
    filtered_ids = [c.pk for c in clients_list]

    # Agrégats factures par client
    stats_fact = (
        fact_base.filter(client_id__in=filtered_ids)
        .values('client_id')
        .annotate(
            nb_factures   = Count('pk'),
            total_facture = Sum('total_ttc'),
            total_paye    = Sum('montant_paye'),
            total_dette   = Sum('reste_a_payer'),
        )
    )
    # Agrégats retours approuvés par client
    stats_ret = (
        RetourVente.objects.filter(
            client_id__in=filtered_ids,
            point_vente__in=pdvs,
            statut='APPROUVE',
        )
        .values('client_id')
        .annotate(
            nb_retours      = Count('pk'),
            total_rembourse = Sum('total_ttc'),
        )
    )
    fact_map = {s['client_id']: s for s in stats_fact}
    ret_map  = {s['client_id']: s for s in stats_ret}

    for c in clients_list:
        sf = fact_map.get(c.pk, {})
        sr = ret_map.get(c.pk,  {})
        c.nb_factures    = sf.get('nb_factures',   0)
        c.total_facture  = sf.get('total_facture')  or Decimal('0')
        c.total_paye     = sf.get('total_paye')     or Decimal('0')
        c.total_dette    = sf.get('total_dette')    or Decimal('0')
        c.nb_retours     = sr.get('nb_retours',    0)
        c.total_rembourse= sr.get('total_rembourse') or Decimal('0')

    # Filtre "avec dette seulement"
    if dette_f == '1':
        clients_list = [c for c in clients_list if c.total_dette > 0]

    # KPIs globaux page
    totaux = {
        'nb_clients':       len(clients_list),
        'total_facture':    sum(c.total_facture   for c in clients_list),
        'total_paye':       sum(c.total_paye      for c in clients_list),
        'total_dette':      sum(c.total_dette     for c in clients_list),
        'total_rembourse':  sum(c.total_rembourse for c in clients_list),
    }

    return render(request, 'caisse/liste_clients.html', {
        'actif':      'caisse',
        'clients':    clients_list,
        'pdvs':       pdvs,
        'q':          q,
        'filt_pdv':   pdv_f,
        'filt_dette': dette_f,
        'totaux':     totaux,
    })


@login_requis
def rapport_session(request, pk):
    if not _peut(request.user, 'acces_module_caisse'):
        messages.error(request, 'Accès refusé.')
        return redirect('caisse:dashboard')

    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    pdvs       = _pdvs_accessibles(request.user, entreprise, admin)

    session = get_object_or_404(
        SessionCaisse.objects.select_related('point_vente', 'ouvert_par', 'approuve_par', 'devise'),
        pk=pk, point_vente__in=pdvs,
    )
    transactions = session.transactions.select_related(
        'effectue_par', 'devise', 'facture', 'depense'
    ).order_by('date_transaction')

    breakdown_encaiss = (
        session.transactions.filter(type_transaction='ENCAISSEMENT')
        .values('mode_paiement')
        .annotate(total=Sum('montant'))
        .order_by('-total')
    )
    breakdown_decaiss = (
        session.transactions.filter(type_transaction__in=['DECAISSEMENT', 'RETRAIT'])
        .values('type_transaction', 'mode_paiement')
        .annotate(total=Sum('montant'))
        .order_by('-total')
    )

    return render(request, 'caisse/rapport_session.html', {
        'session':           session,
        'transactions':      transactions,
        'breakdown_encaiss': breakdown_encaiss,
        'breakdown_decaiss': breakdown_decaiss,
        'modes_labels':      dict(TransactionCaisse.MODES),
        'types_labels':      dict(TransactionCaisse.TYPES),
        'entreprise':        entreprise,
    })


# ─────────────────────────────────────────────
# Avances sur salaire — File de décaissement
# ─────────────────────────────────────────────

@login_requis
def avances_a_decaisser(request):
    """
    Liste des avances RH approuvées en attente de décaissement par le caissier.
    Filtrées sur les PDV accessibles à l'utilisateur courant.
    """
    if not _peut(request.user, 'acces_module_caisse'):
        messages.error(request, 'Accès refusé.')
        return redirect('entreprise:dashboard')

    from rh.models import AvanceSalaire

    entreprise = get_entreprise_utilisateur(request.user)
    admin      = utilisateur_est_admin(request.user)
    pdvs       = _pdvs_accessibles(request.user, entreprise, admin)

    avances_qs = (
        AvanceSalaire.objects
        .filter(statut='APPROUVEE', point_vente__in=pdvs)
        .select_related('employe', 'devise', 'point_vente', 'approuve_par')
        .order_by('date_approbation')
    )

    # PDVs avec une session ouverte
    pdvs_ids_session_ouverte = set(
        SessionCaisse.objects.filter(
            point_vente__in=pdvs, statut='OUVERTE'
        ).values_list('point_vente_id', flat=True)
    )

    # Annoter chaque avance avec le flag session_disponible (calcul Python, pas template)
    avances = list(avances_qs)
    for av in avances:
        av.session_disponible = av.point_vente_id in pdvs_ids_session_ouverte

    # PDVs sans session mais ayant des avances à décaisser
    pdvs_manquants = {
        av.point_vente for av in avances if not av.session_disponible
    }

    return render(request, 'caisse/avances_decaissement.html', {
        'avances':        avances,
        'pdvs_manquants': pdvs_manquants,
        'nb_avances':     len(avances),
    })
