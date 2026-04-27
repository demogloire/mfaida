import json
from django.contrib import messages
from django.utils.deprecation import MiddlewareMixin

class HtmxMessageMiddleware(MiddlewareMixin):
    def process_response(self, request, response):
        # Récupérer les messages en attente (système Django)
        django_messages = messages.get_messages(request)
        if not django_messages:
            return response

        message_list = []
        original_messages = []
        for message in django_messages:
            # Conserver les infos nécessaires si on doit "rejouer" les messages après un HX-Redirect
            original_messages.append(
                {
                    "level": getattr(message, "level", None),
                    "message": str(message),
                    "extra_tags": getattr(message, "extra_tags", ""),
                }
            )
            message_list.append({
                "message": str(message),
                "tags": f"bg-{message.tags}" if message.tags else "bg-info"
            })

        # CAS 1 : C'est du HTMX, on passe par le Header HX-Trigger
        if request.headers.get('HX-Request'):
            # Si HTMX va faire un redirect (HX-Redirect), on veut afficher le toast
            # SUR la page cible. Donc on remet les messages dans le storage et on ne
            # les envoie pas via HX-Trigger sur la réponse intermédiaire.
            if response.get("HX-Redirect"):
                for m in original_messages:
                    messages.add_message(
                        request,
                        m["level"] if m["level"] is not None else messages.INFO,
                        m["message"],
                        extra_tags=m.get("extra_tags") or "",
                    )
                return response

            hx_trigger = response.get('HX-Trigger')
            try:
                payload = json.loads(hx_trigger) if hx_trigger else {}
            except ValueError:
                payload = {hx_trigger: True}

            payload["messages"] = message_list
            response['HX-Trigger'] = json.dumps(payload)
        
        # CAS 2 : Pas HTMX ou Redirect classique
        # Django gère déjà l'affichage via le context 'messages' dans le template
        
        return response
