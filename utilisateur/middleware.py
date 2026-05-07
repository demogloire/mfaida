import json
import re

from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin

from utilisateur.acces_metier import utilisateur_peut_permission


class HtmxMessageMiddleware(MiddlewareMixin):
    def process_response(self, request, response):
        # Récupérer le storage de messages
        storage = messages.get_messages(request)

        # Si le template a déjà itéré sur {{ messages }} (toast.html dans base.html),
        # storage.used sera True — les messages sont déjà dans le HTML rendu.
        # Dans ce cas on n'ajoute PAS HX-Trigger pour éviter le double affichage.
        already_rendered_in_template = getattr(storage, 'used', False)

        # Collecter les messages (cette itération marque aussi used=True)
        message_list = []
        original_messages = []
        for message in storage:
            original_messages.append({
                "level": getattr(message, "level", None),
                "message": str(message),
                "extra_tags": getattr(message, "extra_tags", ""),
            })
            message_list.append({
                "message": str(message),
                "tags": f"bg-{message.tags}" if message.tags else "bg-info",
            })

        if not message_list:
            return response

        # CAS 1 : Requête HTMX
        if request.htmx:
            # Sous-cas A : HX-Redirect → on remet les messages en session pour la page cible
            if response.get("HX-Redirect"):
                for m in original_messages:
                    messages.add_message(
                        request,
                        m["level"] if m["level"] is not None else messages.INFO,
                        m["message"],
                        extra_tags=m.get("extra_tags") or "",
                    )
                return response

            # Sous-cas B : les messages ont déjà été rendus dans le HTML du template
            # (page complète avec base.html / toast.html) → on n'ajoute pas HX-Trigger
            if already_rendered_in_template:
                return response

            # Sous-cas C : réponse partielle → envoyer via HX-Trigger (un seul toast JS)
            hx_trigger = response.get('HX-Trigger')
            try:
                payload = json.loads(hx_trigger) if hx_trigger else {}
            except ValueError:
                payload = {hx_trigger: True}

            payload["messages"] = message_list
            response['HX-Trigger'] = json.dumps(payload)

        # CAS 2 : Requête normale (non-HTMX)
        # Django gère l'affichage via {{ messages }} dans le template
        return response


class ControleModulesMetierMiddleware(MiddlewareMixin):
    """
    Vérifie qu'un utilisateur authentifié possède la permission associée au préfixe d'URL.
    Les admins métier et superusers passent tous les contrôles.
    """

    SKIP_PREFIXES = ('/admin/', '/static/', '/media/')
    ANONYME_OK_PREFIXES = (
        '/user/connexion',
        '/user/logout',
        '/user/mot-de-passe-oublie',
        '/user/superuser',
    )
    ACTIVITE_UTIL_PATTERN = re.compile(r'^/user/utilisateurs/\d+/activite/?')

    def process_request(self, request):
        path = request.path
        raw = getattr(request, 'path_info', path) or path
        normalized = '/' + raw.lstrip('/')

        if any(normalized.startswith(s) for s in self.SKIP_PREFIXES):
            return None

        if any(normalized.startswith(s) or normalized.rstrip('/') == s.rstrip('/')
               for s in self.ANONYME_OK_PREFIXES):
            return None

        login_url = reverse('user:connexion')

        if not getattr(request.user, 'is_authenticated', False):
            sep = '&' if ('?' in login_url) else '?'
            return redirect(f'{login_url}{sep}next={request.get_full_path() or "/"}')

        user = request.user

        needs = self._permissions_requises(normalized)
        if not needs:
            return None

        if all(utilisateur_peut_permission(user, code) for code in needs):
            return None

        messages.error(
            request,
            'Accès refusé pour ce module. Contactez un administrateur.',
        )
        return redirect(reverse('entreprise:dashboard'))

    def _permissions_requises(self, path_no_query):
        p = '/' + path_no_query.lstrip('/').split('?', 1)[0]

        dash = '/' + reverse('entreprise:dashboard').lstrip('/')
        dash_n = dash.rstrip('/')
        if p.rstrip('/') == dash_n:
            return []

        if self.ACTIVITE_UTIL_PATTERN.match(p):
            return []

        if p.startswith('/user/profil'):
            return []
        if p.startswith('/user/parametres/securite'):
            return []
        if p.startswith('/user/parametres/signature'):
            return []
        if p.startswith('/user/parametres/audit'):
            return []

        if p.startswith('/facturation'):
            codes = ['acces_module_vente']
            rest = p[len('/facturation') :].lstrip('/')
            if rest.startswith('proforma'):
                codes.append('acces_facturation_proforma')
            elif rest.startswith('retours'):
                codes.append('acces_ventes_retournees')
            return codes

        if p.startswith('/depenses'):
            return ['acces_module_depenses']

        if p.startswith('/caisse'):
            return ['acces_module_caisse']

        if p.startswith('/achat'):
            codes = ['acces_module_achat']
            rest = p[len('/achat') :].lstrip('/')
            if rest.startswith('commandes') or rest.startswith('lignes/'):
                codes.append('acces_achat_bons_commande')
            return codes

        if p.startswith('/stock/'):
            codes = ['acces_module_stock']
            rest = p[len('/stock/'):].lstrip('/')

            # ── Bons d'ajustement ──────────────────────────────────────────
            if rest.startswith('bons-ajustement') or rest.startswith('ajuster'):
                codes.append('acces_bons_ajustement')

            # ── Inventaires ────────────────────────────────────────────────
            elif rest.startswith('inventaires'):
                codes.append('acces_campagnes_inventaire')

            # ── Dépôt : stock, synthèse, mouvements, corrections, mise-à-ecart
            elif rest.startswith('depots/mise-a-ecart') or rest.startswith('mise-a-ecart'):
                codes.append('acces_stock_depot')
                codes.append('acces_mise_a_ecart')
            elif (
                rest.startswith('depots/')
                or rest.startswith('mouvements/depots')
                or rest.startswith('correction-interne/depots')
            ):
                codes.append('acces_stock_depot')

            # ── PDV : stock, synthèse, mouvements, corrections, mise-à-ecart
            elif rest.startswith('points-vente/mise-a-ecart'):
                codes.append('acces_stock_pdv')
                codes.append('acces_mise_a_ecart')
            elif (
                rest.startswith('points-vente/')
                or rest.startswith('mouvements/points-vente')
                or rest.startswith('correction-interne/points-vente')
            ):
                codes.append('acces_stock_pdv')

            # ── Transferts de stock ────────────────────────────────────────
            elif rest.startswith('transferts/api/'):
                # AJAX public aux utilisateurs ayant au moins un droit transfert
                pass  # la vue elle-même vérifie le droit précis
            elif rest.startswith('transferts/'):
                # Accès à la liste : posséder au moins un droit transfert (vérifié dans la vue)
                pass

            return codes

        mapping = (
            ('/entreprise/', 'acces_configuration_entreprise'),
            ('/produit/', 'acces_configuration_catalogue'),
            ('/tiers/', 'acces_module_tiers'),
            ('/finance/', 'acces_module_finance'),
            ('/rh/', 'acces_module_rh'),
        )
        for prefix, code in mapping:
            if p.startswith(prefix):
                return [code]

        if p.startswith('/user/utilisateurs'):
            return ['acces_administration_utilisateurs']

        if (
            p.startswith('/user/roles')
            or p.startswith('/user/permissions')
            or p.startswith('/user/journal')
        ):
            return ['acces_administration_utilisateurs']

        return []
