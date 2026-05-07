"""Création automatique de TransactionCaisse depuis les autres modules."""

from decimal import Decimal


def _session_active(point_vente):
    """Retourne la session ouverte pour ce PDV, ou None."""
    from .models import SessionCaisse
    return SessionCaisse.objects.filter(point_vente=point_vente, statut='OUVERTE').first()


def enregistrer_encaissement_facture(facture, utilisateur):
    """
    Appelé après la validation d'une facture.
    Crée une TransactionCaisse ENCAISSEMENT si une session est ouverte sur le PDV.
    Aucune transaction si vente à crédit (mode_paiement == 'CREDIT') ou montant_paye == 0.
    """
    from .models import TransactionCaisse

    mode = getattr(facture, 'mode_paiement', 'ESPECES') or 'ESPECES'
    if mode == 'CREDIT':
        return None

    montant_paye = getattr(facture, 'montant_paye', None)
    if not montant_paye or Decimal(str(montant_paye)) <= 0:
        return None

    session = _session_active(facture.point_vente)
    if not session:
        return None

    montant = montant_paye

    return TransactionCaisse.objects.create(
        session          = session,
        type_transaction = 'ENCAISSEMENT',
        mode_paiement    = mode if mode in dict(TransactionCaisse.MODES) else 'AUTRE',
        montant          = Decimal(str(montant)),
        devise           = facture.devise,
        taux_echange     = getattr(facture, 'taux_echange_appliqué', 1) or 1,
        motif            = f'Encaissement facture {facture.numero_facture}',
        facture          = facture,
        client           = getattr(facture, 'client', None),
        effectue_par     = utilisateur,
    )


def enregistrer_encaissement_paiement(paiement, facture, utilisateur):
    """
    Appelé après l'enregistrement d'un PaiementFacture.
    Crée une TransactionCaisse ENCAISSEMENT si une session est ouverte sur le PDV.
    """
    from .models import TransactionCaisse

    session = _session_active(facture.point_vente)
    if not session:
        return None

    mode = getattr(paiement, 'mode_paiement', 'ESPECES') or 'ESPECES'
    # Mapper CASH → ESPECES pour la caisse
    mode_map = {'CASH': 'ESPECES'}
    mode_caisse = mode_map.get(mode, mode)

    return TransactionCaisse.objects.create(
        session          = session,
        type_transaction = 'ENCAISSEMENT',
        mode_paiement    = mode_caisse if mode_caisse in dict(TransactionCaisse.MODES) else 'AUTRE',
        montant          = Decimal(str(paiement.montant)),
        devise           = facture.devise,
        taux_echange     = getattr(facture, 'taux_echange_appliqué', 1) or 1,
        motif            = f'Paiement {paiement.numero} — facture {facture.numero_facture}',
        facture          = facture,
        client           = getattr(facture, 'client', None),
        effectue_par     = utilisateur,
    )


def enregistrer_decaissement_depense(depense, utilisateur):
    """
    Appelé après la validation d'une dépense.
    Crée une TransactionCaisse DECAISSEMENT si une session est ouverte.
    """
    from .models import TransactionCaisse
    session = _session_active(depense.point_vente)
    if not session:
        return None

    # Si la dépense est liée à un retour vente, on récupère le client de ce retour
    client = None
    retour = getattr(depense, 'retour_vente', None)
    if retour:
        client = getattr(retour, 'client', None)

    return TransactionCaisse.objects.create(
        session          = session,
        type_transaction = 'DECAISSEMENT',
        mode_paiement    = 'ESPECES',
        montant          = Decimal(str(depense.montant)),
        devise           = depense.devise,
        taux_echange     = depense.taux_echange or 1,
        motif            = f'Dépense {depense.numero_depense} — {depense.get_type_depense_display()}',
        depense          = depense,
        client           = client,
        effectue_par     = utilisateur,
    )


def enregistrer_decaissement_avance(avance, utilisateur):
    """
    Appelé après l'approbation + décaissement d'une avance sur salaire.
    Crée une TransactionCaisse DECAISSEMENT liée à l'avance.
    Retourne la transaction créée, ou None si aucune session ouverte.
    """
    from .models import TransactionCaisse
    session = _session_active(avance.point_vente)
    if not session:
        return None

    return TransactionCaisse.objects.create(
        session          = session,
        type_transaction = 'DECAISSEMENT',
        mode_paiement    = 'ESPECES',
        montant          = Decimal(str(avance.montant)),
        devise           = avance.devise,
        taux_echange     = 1,
        motif            = f'Avance sur salaire {avance.numero} — {avance.employe}',
        effectue_par     = utilisateur,
    )


def enregistrer_decaissement_retour(retour, depense_liee, utilisateur):
    """
    Appelé après l'approbation d'un retour vente.
    Crée une TransactionCaisse DECAISSEMENT liée au retour.
    """
    from .models import TransactionCaisse
    session = _session_active(retour.point_vente)
    if not session:
        return None

    return TransactionCaisse.objects.create(
        session          = session,
        type_transaction = 'DECAISSEMENT',
        mode_paiement    = 'ESPECES',
        montant          = Decimal(str(retour.total_ttc)),
        devise           = retour.devise,
        taux_echange     = retour.taux_echange or 1,
        motif            = f'Remboursement retour {retour.numero_retour}',
        retour_vente     = retour,
        depense          = depense_liee,
        client           = getattr(retour, 'client', None),
        effectue_par     = utilisateur,
    )
