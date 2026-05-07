from django.contrib import admin
from .models import SessionCaisse, TransactionCaisse


@admin.register(SessionCaisse)
class SessionCaisseAdmin(admin.ModelAdmin):
    list_display  = ('point_vente', 'devise', 'statut', 'fond_ouverture', 'date_ouverture', 'ouvert_par')
    list_filter   = ('statut', 'point_vente')
    search_fields = ('point_vente__nom',)
    readonly_fields = ('date_ouverture',)


@admin.register(TransactionCaisse)
class TransactionCaisseAdmin(admin.ModelAdmin):
    list_display  = ('numero', 'session', 'type_transaction', 'mode_paiement', 'montant', 'devise', 'date_transaction')
    list_filter   = ('type_transaction', 'mode_paiement')
    search_fields = ('numero', 'motif')
    readonly_fields = ('numero', 'date_transaction')
