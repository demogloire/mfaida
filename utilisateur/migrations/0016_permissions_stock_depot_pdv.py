from django.db import migrations


def creer_permissions(apps, schema_editor):
    PermissionPersonnalisee = apps.get_model('utilisateur', 'PermissionPersonnalisee')
    RolePermission = apps.get_model('utilisateur', 'RolePermission')
    Role = apps.get_model('utilisateur', 'Role')

    depot, _ = PermissionPersonnalisee.objects.get_or_create(
        code='acces_stock_depot',
        defaults={'nom': 'Stock dépôt — niveaux, synthèse, mouvements, corrections internes'},
    )
    pdv, _ = PermissionPersonnalisee.objects.get_or_create(
        code='acces_stock_pdv',
        defaults={'nom': 'Stock point de vente — niveaux, synthèse, mouvements, corrections internes'},
    )

    # Rôles avec accès dépôt
    for role in Role.objects.filter(famille_metier__in=['MANAGER', 'ASSISTANT_MANAGER', 'MAGASINIER', 'LOGISTICIEN']):
        RolePermission.objects.get_or_create(role=role, permission=depot)

    # Rôles avec accès PDV
    for role in Role.objects.filter(famille_metier__in=['MANAGER', 'ASSISTANT_MANAGER', 'LOGISTICIEN', 'VENDEUR', 'CAISSIER']):
        RolePermission.objects.get_or_create(role=role, permission=pdv)

    # S'assurer que vendeur/caissier ont bien acces_module_stock
    perm_stock = PermissionPersonnalisee.objects.filter(code='acces_module_stock').first()
    if perm_stock:
        for role in Role.objects.filter(famille_metier__in=['VENDEUR', 'CAISSIER']):
            RolePermission.objects.get_or_create(role=role, permission=perm_stock)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('utilisateur', '0015_permissions_stock_avancees'),
    ]

    operations = [
        migrations.RunPython(creer_permissions, noop_reverse),
    ]
