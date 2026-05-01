import json
from django.contrib import messages
from django.utils.deprecation import MiddlewareMixin

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
