from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Profil, Role, PermissionPersonnalisee, RolePermission, JournalConnexion, JournalAction


class RolePermissionInline(admin.TabularInline):
    model = RolePermission
    extra = 1
    autocomplete_fields = ['permission']


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('nom', 'entreprise', 'description')
    list_filter = ('entreprise',)
    search_fields = ('nom', 'description')
    inlines = [RolePermissionInline]


@admin.register(PermissionPersonnalisee)
class PermissionPersonnaliseeAdmin(admin.ModelAdmin):
    list_display = ('nom', 'code')
    search_fields = ('nom', 'code')


@admin.register(RolePermission)
class RolePermissionAdmin(admin.ModelAdmin):
    list_display = ('role', 'permission')
    list_filter = ('role__entreprise',)
    search_fields = ('role__nom', 'permission__nom')


@admin.register(Profil)
class ProfilAdmin(UserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'branche', 'role', 'admin', 'is_active')
    list_filter = ('branche', 'role', 'admin', 'is_active', 'is_staff')
    search_fields = ('username', 'email', 'first_name', 'last_name', 'telephone')
    ordering = ('last_name', 'first_name')

    fieldsets = UserAdmin.fieldsets + (
        ('Informations ERP', {
            'fields': ('branche', 'role', 'telephone', 'adresse', 'photo', 'admin')
        }),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Informations ERP', {
            'fields': ('email', 'first_name', 'last_name', 'branche', 'role', 'telephone', 'admin')
        }),
    )


@admin.register(JournalConnexion)
class JournalConnexionAdmin(admin.ModelAdmin):
    list_display = ('utilisateur', 'username_tente', 'succes', 'adresse_ip', 'date_heure')
    list_filter = ('succes', 'date_heure')
    search_fields = ('utilisateur__username', 'utilisateur__email', 'username_tente', 'adresse_ip')
    readonly_fields = ('utilisateur', 'username_tente', 'date_heure', 'adresse_ip', 'user_agent', 'succes')
    date_hierarchy = 'date_heure'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(JournalAction)
class JournalActionAdmin(admin.ModelAdmin):
    list_display = ('utilisateur', 'verbe', 'module', 'description', 'adresse_ip', 'date_heure')
    list_filter = ('verbe', 'module', 'date_heure')
    search_fields = ('utilisateur__username', 'utilisateur__email', 'description', 'module')
    readonly_fields = ('utilisateur', 'verbe', 'module', 'description', 'adresse_ip', 'date_heure')
    date_hierarchy = 'date_heure'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
