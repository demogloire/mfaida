from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Q, Count, Sum

from utilisateur.decorators import login_requis
from entreprise.models import Branche, Entreprise

from .models import Client, Fournisseur
from .forms import ClientForm, FournisseurForm


# ───────────────────────────── helpers ─────────────────────────────

def _get_entreprise(user):
    """Entreprise liée : branche ou propriétaire (Entreprise.user). Pas de repli arbitraire."""
    if getattr(user, 'branche_id', None):
        return user.branche.entreprise
    return Entreprise.objects.filter(user=user).first()


def _est_admin(user):
    return getattr(user, 'admin', False) or getattr(user, 'is_superuser', False)


# ═══════════════════════════════════════════════════════════════════
#  CLIENTS
# ═══════════════════════════════════════════════════════════════════

@login_requis
def liste_clients(request):
    entreprise = _get_entreprise(request.user)
    admin = _est_admin(request.user)
    # Administrateur : tous les clients ; sinon uniquement ceux de l'entreprise du compte
    if admin:
        qs = Client.objects.all().select_related('branche', 'branche__entreprise')
    elif entreprise:
        qs = Client.objects.filter(branche__entreprise=entreprise).select_related(
            'branche', 'branche__entreprise'
        )
    else:
        qs = Client.objects.none()

    q = request.GET.get('q', '')
    type_f = request.GET.get('type', '')
    actif_f = request.GET.get('actif', '')

    if q:
        qs = qs.filter(
            Q(nom__icontains=q)
            | Q(code_client__icontains=q)
            | Q(telephone__icontains=q)
            | Q(branche__nom__icontains=q)
            | Q(branche__entreprise__nom__icontains=q)
        )
    if type_f:
        qs = qs.filter(type_client=type_f)
    if actif_f == '1':
        qs = qs.filter(est_actif=True)
    elif actif_f == '0':
        qs = qs.filter(est_actif=False)

    ctx = {
        'clients': qs.order_by('-date_creation'),
        'actif': 'clients',
        'q': q, 'type_f': type_f, 'actif_f': actif_f,
        'TYPES': Client.TYPES_CLIENT,
        'est_super_admin': admin,
        'entreprise_utilisateur': entreprise,
    }
    if request.htmx and request.htmx.target == 'table-container':
        return render(request, 'tiers/clients/partial/table.html', ctx)
    return render(request, 'tiers/clients/liste.html', ctx)


@login_requis
def detail_client(request, pk):
    entreprise = _get_entreprise(request.user)
    admin = _est_admin(request.user)
    if admin:
        client = get_object_or_404(Client, pk=pk)
    else:
        if not entreprise:
            messages.error(request, "Aucune entreprise associée à votre compte.")
            return redirect('tiers:liste-clients')
        client = get_object_or_404(Client, pk=pk, branche__entreprise=entreprise)
    factures = client.factures.order_by('-date_facture')[:10] if hasattr(client, 'factures') else []
    ctx = {'client': client, 'factures': factures, 'actif': 'clients'}
    return render(request, 'tiers/clients/detail.html', ctx)


@login_requis
def creer_client(request):
    entreprise = _get_entreprise(request.user)
    admin = _est_admin(request.user)
    if not admin and not entreprise:
        messages.error(request, "Aucune entreprise associée à votre compte.")
        return redirect('tiers:liste-clients')
    form = ClientForm(request.POST or None, entreprise=entreprise, admin=admin)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, "Client créé avec succès.")
        return redirect('tiers:liste-clients')
    if request.htmx and request.htmx.target == 'form-container':
        return render(request, 'tiers/clients/partial/form.html', {'form': form})
    ctx = {'form': form, 'actif': 'clients', 'titre': 'Nouveau client'}
    return render(request, 'tiers/clients/form.html', ctx)


@login_requis
def modifier_client(request, pk):
    entreprise = _get_entreprise(request.user)
    admin = _est_admin(request.user)
    # Admin peut modifier n'importe quel client, autre utilisateur seulement ceux de son entreprise
    if admin:
        client = get_object_or_404(Client, pk=pk)
    else:
        if not entreprise:
            messages.error(request, "Aucune entreprise associée à votre compte.")
            return redirect('tiers:liste-clients')
        client = get_object_or_404(Client, pk=pk, branche__entreprise=entreprise)
    form = ClientForm(request.POST or None, instance=client, entreprise=entreprise, admin=admin)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, "Client mis à jour.")
        return redirect('tiers:detail-client', pk=pk)
    if request.htmx and request.htmx.target == 'form-container':
        return render(request, 'tiers/clients/partial/form.html', {'form': form, 'objet': client})
    ctx = {'form': form, 'actif': 'clients', 'titre': 'Modifier le client', 'objet': client}
    return render(request, 'tiers/clients/form.html', ctx)


@login_requis
def toggle_client(request, pk):
    entreprise = _get_entreprise(request.user)
    admin = _est_admin(request.user)
    if admin:
        client = get_object_or_404(Client, pk=pk)
    else:
        if not entreprise:
            messages.error(request, "Aucune entreprise associée à votre compte.")
            return redirect('tiers:liste-clients')
        client = get_object_or_404(Client, pk=pk, branche__entreprise=entreprise)
    client.est_actif = not client.est_actif
    client.save(update_fields=['est_actif'])
    etat = "activé" if client.est_actif else "désactivé"
    messages.success(request, f"Client {etat}.")
    return redirect('tiers:liste-clients')


@login_requis
def supprimer_client(request, pk):
    entreprise = _get_entreprise(request.user)
    admin = _est_admin(request.user)
    if admin:
        client = get_object_or_404(Client, pk=pk)
    else:
        if not entreprise:
            messages.error(request, "Aucune entreprise associée à votre compte.")
            return redirect('tiers:liste-clients')
        client = get_object_or_404(Client, pk=pk, branche__entreprise=entreprise)
    if request.method == 'POST':
        client.delete()
        messages.success(request, "Client supprimé.")
        return redirect('tiers:liste-clients')
    ctx = {'objet': client, 'type': 'client'}
    return render(request, 'tiers/confirm_supprimer.html', ctx)


# ═══════════════════════════════════════════════════════════════════
#  FOURNISSEURS
# ═══════════════════════════════════════════════════════════════════

@login_requis
def liste_fournisseurs(request):
    entreprise = _get_entreprise(request.user)
    admin = _est_admin(request.user)
    if admin:
        qs = Fournisseur.objects.select_related('entreprise').all()
    elif entreprise:
        qs = Fournisseur.objects.select_related('entreprise').filter(entreprise=entreprise)
    else:
        qs = Fournisseur.objects.none()

    q = request.GET.get('q', '')
    actif_f = request.GET.get('actif', '')

    if q:
        qs = qs.filter(Q(nom_societe__icontains=q) | Q(code_fournisseur__icontains=q) | Q(telephone__icontains=q))
    if actif_f == '1':
        qs = qs.filter(est_actif=True)
    elif actif_f == '0':
        qs = qs.filter(est_actif=False)

    ctx = {
        'fournisseurs': qs.order_by('-date_enregistrement'),
        'actif': 'fournisseurs',
        'q': q, 'actif_f': actif_f,
        'est_super_admin': admin,
    }
    if request.htmx and request.htmx.target == 'table-container':
        return render(request, 'tiers/fournisseurs/partial/table.html', ctx)
    return render(request, 'tiers/fournisseurs/liste.html', ctx)


@login_requis
def detail_fournisseur(request, pk):
    entreprise = _get_entreprise(request.user)
    admin = _est_admin(request.user)
    if admin:
        fournisseur = get_object_or_404(Fournisseur.objects.select_related('entreprise'), pk=pk)
    else:
        if not entreprise:
            messages.error(request, "Aucune entreprise associée à votre compte.")
            return redirect('tiers:liste-fournisseurs')
        fournisseur = get_object_or_404(
            Fournisseur.objects.select_related('entreprise'),
            pk=pk,
            entreprise=entreprise,
        )
    commandes = fournisseur.ordres_achat.order_by('-date_commande')[:10]
    ctx = {
        'fournisseur': fournisseur,
        'commandes': commandes,
        'actif': 'fournisseurs',
        'est_super_admin': admin,
    }
    return render(request, 'tiers/fournisseurs/detail.html', ctx)


@login_requis
def creer_fournisseur(request):
    entreprise = _get_entreprise(request.user)
    admin = _est_admin(request.user)
    if not admin and not entreprise:
        messages.error(request, "Aucune entreprise associée à votre compte.")
        return redirect('tiers:liste-fournisseurs')
    form = FournisseurForm(request.POST or None, entreprise=entreprise, admin=admin)
    if request.method == 'POST' and form.is_valid():
        fournisseur = form.save(commit=False)
        if admin:
            fournisseur.entreprise = form.cleaned_data['entreprise']
        else:
            fournisseur.entreprise = entreprise
        fournisseur.save()
        messages.success(request, "Fournisseur créé avec succès.")
        return redirect('tiers:liste-fournisseurs')
    if request.htmx and request.htmx.target == 'form-container':
        return render(request, 'tiers/fournisseurs/partial/form.html', {'form': form})
    ctx = {
        'form': form,
        'actif': 'fournisseurs',
        'titre': 'Nouveau fournisseur',
        'est_super_admin': admin,
    }
    return render(request, 'tiers/fournisseurs/form.html', ctx)


@login_requis
def modifier_fournisseur(request, pk):
    entreprise = _get_entreprise(request.user)
    admin = _est_admin(request.user)
    if admin:
        fournisseur = get_object_or_404(
            Fournisseur.objects.select_related('entreprise'),
            pk=pk,
        )
    else:
        if not entreprise:
            messages.error(request, 'Aucune entreprise associée à votre compte.')
            return redirect('tiers:liste-fournisseurs')
        fournisseur = get_object_or_404(
            Fournisseur.objects.select_related('entreprise'),
            pk=pk,
            entreprise=entreprise,
        )

    form = FournisseurForm(
        request.POST or None,
        instance=fournisseur,
        entreprise=entreprise,
        admin=admin,
    )
    if request.method == 'POST' and form.is_valid():
        if admin:
            inst = form.save(commit=False)
            inst.entreprise = form.cleaned_data['entreprise']
            inst.save()
        else:
            form.save()
        messages.success(request, 'Fournisseur mis à jour.')
        return redirect('tiers:detail-fournisseur', pk=pk)
    if request.htmx and request.htmx.target == 'form-container':
        return render(
            request,
            'tiers/fournisseurs/partial/form.html',
            {'form': form, 'objet': fournisseur},
        )
    ctx = {
        'form': form,
        'actif': 'fournisseurs',
        'titre': 'Modifier le fournisseur',
        'objet': fournisseur,
        'est_super_admin': admin,
    }
    return render(request, 'tiers/fournisseurs/form.html', ctx)


@login_requis
def toggle_fournisseur(request, pk):
    entreprise = _get_entreprise(request.user)
    admin = _est_admin(request.user)
    if admin:
        fournisseur = get_object_or_404(Fournisseur, pk=pk)
    else:
        if not entreprise:
            messages.error(request, "Aucune entreprise associée à votre compte.")
            return redirect('tiers:liste-fournisseurs')
        fournisseur = get_object_or_404(Fournisseur, pk=pk, entreprise=entreprise)
    fournisseur.est_actif = not fournisseur.est_actif
    fournisseur.save(update_fields=['est_actif'])
    etat = "activé" if fournisseur.est_actif else "désactivé"
    messages.success(request, f"Fournisseur {etat}.")
    return redirect('tiers:liste-fournisseurs')


@login_requis
def supprimer_fournisseur(request, pk):
    entreprise = _get_entreprise(request.user)
    admin = _est_admin(request.user)
    if admin:
        fournisseur = get_object_or_404(Fournisseur, pk=pk)
    else:
        if not entreprise:
            messages.error(request, "Aucune entreprise associée à votre compte.")
            return redirect('tiers:liste-fournisseurs')
        fournisseur = get_object_or_404(Fournisseur, pk=pk, entreprise=entreprise)
    if request.method == 'POST':
        fournisseur.delete()
        messages.success(request, "Fournisseur supprimé.")
        return redirect('tiers:liste-fournisseurs')
    ctx = {'objet': fournisseur, 'type': 'fournisseur'}
    return render(request, 'tiers/confirm_supprimer.html', ctx)
