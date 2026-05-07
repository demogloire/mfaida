from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.urls import reverse


def login_requis(vue):
    """Redirige vers la page de connexion si l'utilisateur n'est pas authentifié."""
    @wraps(vue)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"{reverse('user:connexion')}?next={request.path}")
        return vue(request, *args, **kwargs)
    return wrapper


def admin_requis(vue):
    """Accès réservé aux administrateurs ERP (profil.admin) ou superutilisateurs Django."""
    @wraps(vue)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f"{reverse('user:connexion')}?next={request.path}")
        if not (
            getattr(request.user, 'admin', False)
            or getattr(request.user, 'is_superuser', False)
        ):
            messages.error(
                request,
                "Accès réservé aux administrateurs.",
            )
            return redirect('entreprise:dashboard')
        return vue(request, *args, **kwargs)
    return wrapper


def permission_requise(code_permission):
    """
    Vérifie que l'utilisateur connecté possède la PermissionPersonnalisee
    identifiée par `code_permission` via son rôle.

    Usage :
        @permission_requise('voir_finance')
        def ma_vue(request): ...
    """
    def decorateur(vue):
        @wraps(vue)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect(f"{reverse('user:connexion')}?next={request.path}")
            if not request.user.a_la_permission(code_permission):
                messages.error(
                    request,
                    f"Accès refusé : permission «\u00a0{code_permission}\u00a0» requise."
                )
                return redirect('entreprise:dashboard')
            return vue(request, *args, **kwargs)
        return wrapper
    return decorateur
