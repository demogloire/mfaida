from django.shortcuts import render, redirect
from .forms import (
    EntrepriseForm,
    BrancheForm,
    EtagereForm,
    UploadFile,
    DepotForm,
    PoinDeVenteForm,
    MajPoinDeVenteForm,
    DeviseForm,
    FournisseurForm,
)
from django.contrib import messages
from .models import Entreprise, Branche, Location, Depot, PointVente, Devise, Fournisseur
from django.urls import reverse
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST
from .utility import import_csv
from utilities.utility import error_message_list
import json
from django.core.paginator import Paginator
from django.db.models import Q

# Create your views here.

def Dashboard(request):
    context={}
    return render(request,'entreprise/dashboard.html', context)

def Information(request):
    form=EntrepriseForm()
    context={"form":form,"info":"active","subdrop":""}

    if request.method=="POST":
        form = EntrepriseForm(request.POST, request.FILES)
        if form.is_valid():
            nw_user= form.save(commit=True)
            nw_user.user= request.user
            nw_user.save() #Enregistrer 
            messages.success(request, "Entreprise crée")
            q=Entreprise.objects.filter(user=request.user).all()
            response = render(request, 'entreprise/partial/lire/listenetreprise.html', {'listentreprise':  q})
            response['HX-Push-Url'] = '/entreprise/listes/'
            return response

        #Message d'erreur
        else:
            errors_list = []
            for field_name, errors in form.errors.items():
                label = form.fields[field_name].label or field_name
                errors_list.append(f"{label} : {', '.join(errors)}")
            error_msg = " | ".join([f"{', '.join(e)}" for f, e in form.errors.items()])
            messages.info(request, error_msg)
    return render(request,'entreprise/info.html', context)

def ListEntreprise(request):
    q=Entreprise.objects.filter(user=request.user).all()
    context={"info":"active","listentreprise":  q}
    return render(request,'entreprise/liste_entreprise.html', context)

@require_POST
def EntrepriseStatus(request, pk):
    entreprise = get_object_or_404(Entreprise, pk=pk, user=request.user)
    
    entreprise.nepas_actif = 'status' in request.POST
    entreprise.save()
    if entreprise.nepas_actif:
        messages.success(request, "Entreprise est desactivée")
    else:
        messages.success(request, "Entreprise est activée")
    return render(request, 'entreprise/partial/modifier/taggle.html', {'entreprise': entreprise})

def ModifierEntreprise(request, pk):
    entreprise = get_object_or_404(Entreprise, pk=pk, user=request.user)
    form = EntrepriseForm(instance=entreprise)
    context={"form":form,"info":"active","subdrop":"", "logo_display":entreprise.logo}

    if request.method=="POST":
        form = EntrepriseForm(request.POST or None, request.FILES or None, instance=entreprise)
        form.save()
        messages.success(request, "Entreprise est modifiée")
        q=Entreprise.objects.filter(user=request.user).all()
        response = render(request, 'entreprise/partial/lire/listenetreprise.html', {'listentreprise':  q})
        response['HX-Push-Url'] = '/entreprise/listes/'
        return response

    return render(request,'entreprise/info-mod.html', context)


############### BRANCHE ###########################

def BrancheAjouter(request):
    form=BrancheForm(request=request)
    context={"branche1":True,"subdrop":True,"branch":True,"form":form}

    if request.method=="POST":
        form=BrancheForm(request.POST,request=request)
        if form.is_valid():
            form.save()
            messages.success(request, "Branche crée")
            response = HttpResponse(status=204) 
            response['HX-Redirect'] = reverse('entreprise:branche-liste')
            return response
        else:
            error_msg=error_message_list(form)
            messages.info(request, error_msg)
            return render(request,'branche/partial/info.html',context)

    return render(request,'branche/info.html',context)

def ListeDeBranche(request):
    q = Branche.objects.filter(entreprise__user=request.user).select_related('entreprise')
    context={"branche1":True,"subdrop":True,"branch":True,"listebranche":q}
    return render(request,'branche/branche.html', context)

def BrancheStatus(request, pk):
    branches = get_object_or_404(Branche, pk=pk, entreprise__user=request.user)

    if branches.est_actif==True:
        branches.est_actif=False
        messages.info(request, "Branche est desactivée")
    else:
        branches.est_actif=True
        messages.success(request, "Branche est activée")
    branches.save()
    
    q = Branche.objects.filter(entreprise__user=request.user).select_related('entreprise')
    context={"branche1":True,"subdrop":True,"branch":True,"listebranche":q}
    return render(request,'branche/partial/liste-loop.html', context)

def ModifierBranche(request, pk):
    branches = get_object_or_404(Branche, pk=pk, entreprise__user=request.user)
    form = BrancheForm(instance=branches)
    context={"branche1":True,"subdrop":True,"branch":True,"form":form, "branche_id":branches.id}

    if request.method=="POST":
        form = BrancheForm(request.POST, instance=branches)
        if form.is_valid():
            form.save()
            messages.success(request, "Entreprise est modifiée")
            if request.headers.get('HX-Request'):
                response = HttpResponse()
                response['HX-Redirect'] = reverse('entreprise:branche-liste')
                return response
                # Redirection classique si pas de HTMX
            return redirect('entreprise:branche-liste')
    return render(request,'branche/maj.html', context)

def Etagere(request, pk):

    form=EtagereForm(branche_id=pk)
    context={"branche1":True,"subdrop":True,"branch":True,"form":form, "pk":pk}

    if request.method=="POST":
        form=EtagereForm(request.POST, branche_id=pk)
        if form.is_valid():
            
            initiale = form.cleaned_data["initiale"].strip()
            reference = form.cleaned_data["reference"].strip()
            nouveau_code = f"{initiale}{reference}"

            if Location.objects.filter(code=nouveau_code, branche_id=pk).exists():
                if request.headers.get('HX-Request'):
                    messages.info(request, "Cette étagère existe déjà dans cette branche.")
                    return render(request, 'etagere/partial/form_etagere.html', {"branche1":True,"subdrop":True,"branch":True,"form":form, "pk":pk})

            #Enregistrement
            etagere = form.save(commit=False)
            etagere.branche_id = pk  
            etagere.code = nouveau_code
            etagere.ramassage=form.cleaned_data["ramassage"]
            etagere.save()
            messages.success(request, "Enregistré avec succès")
            response = HttpResponse(status=204) 
            response['HX-Redirect'] = reverse('entreprise:etagere-liste', args=[pk])
            return response
        
        else:
            form = EtagereForm(branche_id=pk)
            context = {"branche1":True,"subdrop":True,"branch":True,"form":form, "pk":pk}
    return render(request, 'etagere/ajouter.html', context)

def ListeLocation(request, pk):
    q = Location.objects.filter(branche_id=pk, branche__entreprise__user=request.user).select_related('branche')
    context={"branche1":True,"subdrop":True,"branch":True,"locations":q, "pk":pk}
    return render(request,'etagere/liste.html', context)

def EtagereModifier(request, pk, branche_id):
    location = get_object_or_404(Location, pk=pk, branche__entreprise__user=request.user)
    form = EtagereForm(branche_id=branche_id, instance=location)
    context = {"branche1": True, "subdrop": True, "branch": True, "branche_id": branche_id, "pk": pk, "form": form}
    if request.method == "POST":
        form = EtagereForm(request.POST, branche_id=branche_id, instance=location)
        if form.is_valid():
            initiale = form.cleaned_data["initiale"].strip()
            reference = form.cleaned_data["reference"].strip()
            nouveau_code = f"{initiale}{reference}"
            nouveau_ramassage = form.cleaned_data["ramassage"]
            capacite = form.cleaned_data["capacite"]

            # On vérifie si ce code est déjà utilisé par une AUTRE étagère
            code_existe_deja = Location.objects.filter(code=nouveau_code, branche_id=branche_id).exclude(pk=pk).exists()

            if code_existe_deja:
                Location.objects.filter(pk=pk).update(ramassage=nouveau_ramassage,capacite=capacite)
                if request.headers.get('HX-Request'):
                    messages.info(request, "Ce code existe déjà. Seul le statut de ramassage a été mis à jour.")
                    return render(request, 'etagere/partial/form_etagere_mod.html', context)

            else:
                etagere = form.save(commit=False)
                etagere.code = nouveau_code
                etagere.reference=reference
                etagere.ramassage=nouveau_ramassage
                etagere.capacite=capacite
                etagere.save()
                msg_text = "Modifié avec succès"
                msg_level = "success"
            
                messages.add_message(request, messages.SUCCESS if msg_level=="success" else messages.WARNING, msg_text)

            response = HttpResponse()
            response['HX-Redirect'] = reverse('entreprise:etagere-liste', args=[branche_id])
            return response
    else:
        context["form"]= EtagereForm(branche_id=branche_id, instance=location)
    return render(request, 'etagere/mod.html', context)

def UploadExcel(request, pk):
    form=UploadFile()
    context = {"branche1": True, "subdrop": True, "branch": True, "pk": pk, "form":form}
    if request.method=="POST":
        form=UploadFile(request.POST, request.FILES)
        
        if form.is_valid():
            
            file=form.cleaned_data["file_excel"]
            erreur, data = import_csv(file)
            if erreur > 0:
                if request.headers.get('HX-Request'):
                    messages.info(request, "Vérifier le fichier, il y'a une erreur sur une ou plusieurs lignes")
                    return render(request, 'etagere/partial/excel.html', context)
            
                
            #Enregistrement
            location = get_object_or_404(Branche, pk=pk)
            for ref in data:
                
                nouveau_code=f"{location.init_location}{ref[0]}"
                existing_location = Location.objects.filter(code=nouveau_code, branche_id=location.id).first()
                if existing_location:
                    Location.objects.filter(pk=existing_location.id).update(ramassage=ref[2], capacite=ref[1])
                else:
                    Location.objects.create(
                        initiale=location.init_location,
                        reference=ref[0],
                        code=nouveau_code,
                        capacite=ref[1],
                        branche=location,
                        ramassage=ref[2]
                    )
            
            messages.success(request, "Charger avec succès")
            response = HttpResponse(status=204) 
            response['HX-Redirect'] = reverse('entreprise:etagere-liste', args=[location.id])
            return response
            
        else:
            errors_list = []
            for field_name, errors in form.errors.items():
                label = form.fields[field_name].label or field_name
                errors_list.append(f"{label} : {', '.join(errors)}")
            error_msg = " | ".join([f"{', '.join(e)}" for f, e in form.errors.items()])
            messages.info(request, error_msg)
            return render(request, 'etagere/partial/excel.html', context)

    return render(request,'etagere/upload_excel.html',context)


############### DEPOT ###########################

def AjouterDepot(request, pk):
    form=DepotForm(branche_id=pk)
    context={"branche1":True,"subdrop":True,"branch":True,"form":form, "branche_id":pk}
    #Appartenance à l'entreprise
    pdv=get_object_or_404(Branche, pk=pk, entreprise__user=request.user)
    
    if request.method=="POST":
        form=DepotForm(request.POST, branche_id=pk)
        if form.is_valid():
            est_principal=form.cleaned_data["est_principal"]
            q=Depot.objects.filter(branche_id=pk, est_principal=True).all()
            if q and est_principal:
                if request.headers.get('HX-Request'):
                    messages.info(request, "Un autré dépôt principal existe")
                    return render(request, 'depot/partial/form_add.html', {"branche1":True,"subdrop":True,"branch":True,"form":form, "branche_id":pk})
            
            enre=form.save(commit=False)
            enre.branche_id=pk
            enre.save()
            messages.success(request, "Dépôt crée avec succes")
            response = HttpResponse(status=204) 
            response['HX-Redirect'] = reverse('entreprise:depot-liste', kwargs={'pk': pk})
            return response
        else:
            if request.headers.get('HX-Request'):
                error_msg=error_message_list(form)
                messages.info(request, error_msg)
                return render(request, 'depot/partial/form_add.html', {"branche1":True,"subdrop":True,"branch":True,"form":form, "branche_id":pk})
    return render(request, 'depot/depot.html', context)

def ListeDepot(request, pk):
    q = Depot.objects.filter(branche_id=pk, branche__entreprise__user=request.user).select_related('branche')
    context={"branche1":True,"subdrop":True,"branch":True,"depots":q, "pk":pk}
    return render(request, 'depot/liste.html', context)

def ListeDepotTous(request):
    search = (request.GET.get("q") or "").strip()
    qs = Depot.objects.filter(branche__entreprise__user=request.user).select_related('branche', 'branche__entreprise')
    if search:
        qs = qs.filter(
            Q(code_depot__icontains=search)
            | Q(nom__icontains=search)
            | Q(adresse__icontains=search)
            | Q(branche__nom__icontains=search)
            | Q(branche__entreprise__nom__icontains=search)
        )

    qs = qs.order_by("branche__entreprise__nom", "branche__nom", "nom")
    paginator = Paginator(qs, 10)
    page_obj = paginator.get_page(request.GET.get("page") or 1)

    context = {
        "branche1": True,
        "subdrop": True,
        "depot": True,
        "depots": page_obj,
        "q": search,
    }
    if request.headers.get("HX-Request") and request.headers.get("HX-Target") == "depot-list":
        return render(request, "depot/partial/lire_tous.html", context)
    return render(request, "depot/liste_tous.html", context)

def MajDepot(request, pk):
    #Requête sur le depôt.
    depot_unique=get_object_or_404(Depot, pk=pk, branche__entreprise__user=request.user)
    form=DepotForm(instance=depot_unique, branche_id=depot_unique.branche_id)
    context={"branche1":True,"subdrop":True,"branch":True,"form":form, "depot_id":pk, "branche_id":depot_unique.branche_id}

    if request.method == "POST":
        form=DepotForm(request.POST, instance=depot_unique, branche_id=depot_unique.branche_id)
        if form.is_valid():
            est_principal=form.cleaned_data["est_principal"]
            q=Depot.objects.filter(branche_id=depot_unique.branche_id, est_principal=True).exclude(pk=pk).exists()
            if q and est_principal:
                if request.headers.get('HX-Request'):
                    messages.info(request, "Un autré dépôt principal existe")
                    return render(request, 'depot/partial/form_mod.html', context)
            form.save()
            messages.success(request, "Dépôt mise à jour")
            response = HttpResponse(status=204) 
            response['HX-Redirect'] = reverse('entreprise:depot-liste', kwargs={'pk': depot_unique.branche_id})
            return response
        else:
            if request.headers.get('HX-Request'):
                error_msg=error_message_list(form)
                messages.info(request, error_msg)
                return render(request, 'depot/partial/form_mod.html',context)
    
    return render(request, 'depot/maj.html', context)


############### POINT DE VENTE ###########################

def AjouterPoindeVente(request, pk):
    params={"branche":pk,"user_id":request.user}
    form=PoinDeVenteForm(params=params)
    context={"branche1":True,"subdrop":True,"branch":True,"form":form, "branche_id":pk}
    #Appartenance à l'entreprise
    pdv=get_object_or_404(Branche, pk=pk, entreprise__user=request.user)

    if request.method == "POST":
        form=PoinDeVenteForm(request.POST, params=params)
        if form.is_valid():
            enre=form.save(commit=False)
            enre.branche_id=pk
            form.save()
            messages.success(request, "Poin de vente crée avec succès")
            response = HttpResponse(status=204) 
            response['HX-Redirect'] = reverse('entreprise:pvente-liste', kwargs={'pk': pk})
            return response
        else:
            if request.headers.get('HX-Request'):
                error_msg=error_message_list(form)
                messages.info(request, error_msg)
                return render(request, 'pvente/partial/form_add.html', context)
    return render(request, 'pvente/pvente.html', context)


def ListePVente(request, pk):
    q = PointVente.objects.filter(branche_id=pk, branche__entreprise__user=request.user).select_related('branche', 'depot_source')
    context={"branche1":True,"subdrop":True,"branch":True,"pventes":q, "pk":pk}
    return render(request, 'pvente/liste.html', context)

def ListePVenteTous(request):
    search = (request.GET.get("q") or "").strip()
    qs = PointVente.objects.filter(branche__entreprise__user=request.user).select_related('branche', 'depot_source', 'branche__entreprise')
    if search:
        qs = qs.filter(
            Q(code_pointvente__icontains=search)
            | Q(nom__icontains=search)
            | Q(branche__nom__icontains=search)
            | Q(branche__entreprise__nom__icontains=search)
            | Q(depot_source__nom__icontains=search)
        )

    qs = qs.order_by("branche__entreprise__nom", "branche__nom", "nom")
    paginator = Paginator(qs, 10)
    page_obj = paginator.get_page(request.GET.get("page") or 1)

    context = {"branche1": True, "subdrop": True, "pdvente": True, "pventes": page_obj, "q": search}
    if request.headers.get("HX-Request") and request.headers.get("HX-Target") == "pvente-list":
        return render(request, "pvente/partial/lire_tous.html", context)
    return render(request, "pvente/liste_tous.html", context)


def MajPDVente(request, pk):
    #Requête sur le depôt.
    pdvente_unique=get_object_or_404(PointVente, pk=pk, branche__entreprise__user=request.user)
    params={"branche":pdvente_unique.branche_id,"user_id":request.user}
    form=MajPoinDeVenteForm(instance=pdvente_unique, params=params)
    context={"branche1":True,"subdrop":True,"branch":True,"form":form, "pk":pk, "branche_id":pdvente_unique.branche_id}

    if request.method == "POST":
        form=MajPoinDeVenteForm(request.POST, instance=pdvente_unique, params=params)
        if form.is_valid():
            form.save()
            messages.success(request, "PDVente mise à jour")
            response = HttpResponse(status=204) 
            response['HX-Redirect'] = reverse('entreprise:pvente-liste', kwargs={'pk': pdvente_unique.branche_id})
            return response
        else:
            if request.headers.get('HX-Request'):
                error_msg=error_message_list(form)
                messages.info(request, error_msg)
                return render(request, 'pvente/partial/form_mod.html',context)

    return render(request, 'pvente/modifier.html', context)

############### DEVISE ###########################

def DeviseAjouter(request):
    form = DeviseForm(request=request)
    context = {"devise": True, "form": form}

    if request.method == "POST":
        form = DeviseForm(request.POST, request=request)
        if form.is_valid():
            devise = form.save()
            if devise.est_principale:
                Devise.objects.filter(entreprise=devise.entreprise).exclude(pk=devise.pk).update(est_principale=False)
            messages.success(request, "Devise créée")
            response = HttpResponse(status=204)
            response["HX-Redirect"] = reverse("entreprise:devise-liste")
            return response
        error_msg = error_message_list(form)
        messages.info(request, error_msg)
        return render(request, "devise/partial/form_add.html", context)

    return render(request, "devise/devise.html", context)


def DeviseListe(request):
    search = (request.GET.get("q") or "").strip()
    qs = Devise.objects.filter(entreprise__user=request.user).select_related("entreprise")
    if search:
        qs = qs.filter(
            Q(entreprise__nom__icontains=search)
            | Q(code__icontains=search)
            | Q(symbole__icontains=search)
        )

    qs = qs.order_by("entreprise__nom", "code")
    paginator = Paginator(qs, 10)
    page_obj = paginator.get_page(request.GET.get("page") or 1)

    context = {"devise": True, "devises": page_obj, "q": search}
    if request.headers.get("HX-Request") and request.headers.get("HX-Target") == "devise-list":
        return render(request, "devise/partial/lire.html", context)
    return render(request, "devise/liste.html", context)


def DeviseMaj(request, pk):
    devise_obj = get_object_or_404(Devise, pk=pk, entreprise__user=request.user)
    form = DeviseForm(instance=devise_obj, request=request)
    context = {"devise": True, "form": form, "devise_id": pk}

    if request.method == "POST":
        form = DeviseForm(request.POST, instance=devise_obj, request=request)
        if form.is_valid():
            devise = form.save()
            if devise.est_principale:
                Devise.objects.filter(entreprise=devise.entreprise).exclude(pk=devise.pk).update(est_principale=False)
            messages.success(request, "Devise mise à jour")
            response = HttpResponse(status=204)
            response["HX-Redirect"] = reverse("entreprise:devise-liste")
            return response

        error_msg = error_message_list(form)
        messages.info(request, error_msg)
        return render(request, "devise/partial/form_mod.html", context)

    return render(request, "devise/modifier.html", context)


@require_POST
def DeviseSupprimer(request, pk):
    devise_obj = get_object_or_404(Devise, pk=pk, entreprise__user=request.user)
    devise_obj.delete()
    messages.success(request, "Devise supprimée")
    devises = Devise.objects.filter(entreprise__user=request.user).select_related("entreprise").order_by("entreprise__nom", "code")
    return render(request, "devise/partial/lire.html", {"devise": True, "devises": devises})


############### FOURNISSEUR ###########################

def FournisseurListe(request):
    search = (request.GET.get("q") or "").strip()
    qs = Fournisseur.objects.filter(entreprise__user=request.user).select_related("entreprise")
    if search:
        qs = qs.filter(
            Q(entreprise__nom__icontains=search)
            | Q(code_fournisseur__icontains=search)
            | Q(nom_societe__icontains=search)
            | Q(telephone__icontains=search)
            | Q(ville__icontains=search)
        )

    qs = qs.order_by("entreprise__nom", "nom_societe")
    paginator = Paginator(qs, 10)
    page_obj = paginator.get_page(request.GET.get("page") or 1)

    context = {"fournisseur": True, "fournisseurs": page_obj, "q": search}
    if request.headers.get("HX-Request") and request.headers.get("HX-Target") == "fournisseur-list":
        return render(request, "fournisseur/partial/lire.html", context)
    return render(request, "fournisseur/liste.html", context)


def FournisseurAjouter(request):
    form = FournisseurForm(request=request)
    context = {"fournisseur": True, "form": form}

    if request.method == "POST":
        form = FournisseurForm(request.POST, request=request)
        if form.is_valid():
            fournisseur = form.save()
            messages.success(request, f"Fournisseur créé ({fournisseur.code_fournisseur})")
            response = HttpResponse(status=204)
            response["HX-Redirect"] = reverse("entreprise:fournisseur-liste")
            return response
        messages.info(request, error_message_list(form))
        return render(request, "fournisseur/partial/form_add.html", context)

    return render(request, "fournisseur/fournisseur.html", context)


def FournisseurMaj(request, pk):
    fournisseur_obj = get_object_or_404(Fournisseur, pk=pk, entreprise__user=request.user)
    form = FournisseurForm(instance=fournisseur_obj, request=request)
    context = {"fournisseur": True, "form": form, "fournisseur_id": pk, "code": fournisseur_obj.code_fournisseur}

    if request.method == "POST":
        form = FournisseurForm(request.POST, instance=fournisseur_obj, request=request)
        if form.is_valid():
            fournisseur = form.save()
            messages.success(request, f"Fournisseur mis à jour ({fournisseur.code_fournisseur})")
            response = HttpResponse(status=204)
            response["HX-Redirect"] = reverse("entreprise:fournisseur-liste")
            return response
        messages.info(request, error_message_list(form))
        return render(request, "fournisseur/partial/form_mod.html", context)

    return render(request, "fournisseur/modifier.html", context)


@require_POST
def FournisseurSupprimer(request, pk):
    fournisseur_obj = get_object_or_404(Fournisseur, pk=pk, entreprise__user=request.user)
    fournisseur_obj.delete()
    messages.success(request, "Fournisseur supprimé")
    fournisseurs = (
        Fournisseur.objects.filter(entreprise__user=request.user)
        .select_related("entreprise")
        .order_by("entreprise__nom", "nom_societe")
    )
    return render(request, "fournisseur/partial/lire.html", {"fournisseur": True, "fournisseurs": fournisseurs})
