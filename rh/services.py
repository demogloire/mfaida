"""Services métier pour le module RH — génération des bulletins de paie."""

import calendar
from datetime import date
from decimal import Decimal

from django.db import transaction

from .models import AvanceSalaire, BulletinPaie, LigneBulletin, Presence


@transaction.atomic
def generer_bulletin(employe, mois: int, annee: int, cree_par,
                     jours_ouvrables: int = 26) -> BulletinPaie:
    """
    Génère automatiquement un bulletin de paie pour un employé sur une période donnée.

    Calculs effectués :
    - Jours prestés  : PRESENT + RETARD dans les présences du mois
    - Jours congés   : CONGE dans les présences du mois
    - Jours absences : ABSENT dans les présences du mois
    - Salaire brut   : (salaire_base / jours_ouvrables) × jours_prestés
    - Avances        : toutes les avances DECAISSEE non encore remboursées
    - Lignes supplémentaires  : aucune (à ajouter manuellement ensuite)
    - Salaire net    : brut + avantages - retenues_autres - retenues_avances
    """
    if BulletinPaie.objects.filter(
        employe=employe, periode_mois=mois, periode_annee=annee
    ).exists():
        raise ValueError(
            f"Un bulletin existe déjà pour {employe} — {mois:02d}/{annee}."
        )

    # ── Contrat actif ─────────────────────────────────────────────────────────
    contrat = employe.contrats.filter(est_actuel=True).first()
    if not contrat:
        raise ValueError(f"Aucun contrat actif trouvé pour {employe}.")

    devise        = contrat.devise
    salaire_base  = contrat.salaire_base

    # ── Présences du mois ─────────────────────────────────────────────────────
    _, nb_jours_mois = calendar.monthrange(annee, mois)
    debut_mois   = date(annee, mois, 1)
    fin_mois     = date(annee, mois, nb_jours_mois)

    presences_qs = Presence.objects.filter(
        employe=employe,
        date__range=(debut_mois, fin_mois),
    )
    jours_prestes  = presences_qs.filter(statut__in=['PRESENT', 'RETARD']).count()
    jours_conges   = presences_qs.filter(statut='CONGE').count()
    jours_absences = presences_qs.filter(statut='ABSENT').count()

    # ── Salaire brut proratisé ────────────────────────────────────────────────
    if jours_ouvrables > 0 and jours_prestes > 0:
        salaire_brut = (salaire_base / Decimal(jours_ouvrables)) * Decimal(jours_prestes)
        salaire_brut = salaire_brut.quantize(Decimal('0.01'))
    elif jours_prestes == 0:
        salaire_brut = Decimal('0.00')
    else:
        salaire_brut = salaire_base

    # ── Avances sur salaire à déduire ─────────────────────────────────────────
    # Avances décaissées dans la même devise, pas encore remboursées ni déjà
    # incluses dans un bulletin VALIDE ou PAYE.
    avances_a_deduire = AvanceSalaire.objects.filter(
        employe=employe,
        statut='DECAISSEE',
        devise=devise,
    ).filter(
        ligne_bulletin__isnull=True  # pas encore dans aucun bulletin
    )

    retenues_avances = sum(
        (a.montant for a in avances_a_deduire), Decimal('0.00')
    )

    # ── Salaire net ───────────────────────────────────────────────────────────
    salaire_net = (salaire_brut - retenues_avances).quantize(Decimal('0.01'))

    # ── Création du bulletin ──────────────────────────────────────────────────
    bulletin = BulletinPaie.objects.create(
        employe          = employe,
        contrat          = contrat,
        devise           = devise,
        periode_mois     = mois,
        periode_annee    = annee,
        jours_ouvrables  = jours_ouvrables,
        jours_prestes    = jours_prestes,
        jours_conges     = jours_conges,
        jours_absences   = jours_absences,
        salaire_base_ref = salaire_base,
        salaire_brut     = salaire_brut,
        allocations      = Decimal('0.00'),
        retenues         = Decimal('0.00'),
        retenues_avances = retenues_avances,
        salaire_net      = salaire_net,
        cree_par         = cree_par,
    )

    # ── Lignes pour les avances ───────────────────────────────────────────────
    for avance in avances_a_deduire:
        LigneBulletin.objects.create(
            bulletin = bulletin,
            type     = 'RETENUE',
            libelle  = f"Retenue — avance {avance.numero} ({avance.date_demande.strftime('%d/%m/%Y')})",
            montant  = avance.montant,
            avance   = avance,
        )

    return bulletin


def recalculer_totaux(bulletin: BulletinPaie) -> None:
    """Recalcule allocations, retenues et salaire_net à partir des lignes."""
    allocations      = Decimal('0.00')
    retenues_autres  = Decimal('0.00')

    for ligne in bulletin.lignes.all():
        if ligne.avance_id:
            # Les avances sont déjà dans retenues_avances — ne pas doubler
            continue
        if ligne.type == 'AVANTAGE':
            allocations += ligne.montant
        elif ligne.type == 'RETENUE':
            retenues_autres += ligne.montant

    salaire_net = (
        bulletin.salaire_brut
        + allocations
        - retenues_autres
        - bulletin.retenues_avances
    ).quantize(Decimal('0.01'))

    bulletin.allocations = allocations
    bulletin.retenues    = retenues_autres
    bulletin.salaire_net = salaire_net
    bulletin.save(update_fields=['allocations', 'retenues', 'salaire_net'])
