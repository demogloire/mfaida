from django.db import migrations


def creer_permissions(apps, schema_editor):
    PermissionPersonnalisee = apps.get_model('utilisateur', 'PermissionPersonnalisee')
    RolePermission = apps.get_model('utilisateur', 'RolePermission')
    Role = apps.get_model('utilisateur', 'Role')

    nouvelles = [
        ('acces_transfert_depot_pdv',   'Transfert stock Dépôt → Point de vente'),
        ('acces_transfert_pdv_depot',   'Transfert stock Point de vente → Dépôt'),
        ('acces_transfert_depot_depot', 'Transfert stock Dépôt → Dépôt'),
        ('acces_transfert_pdv_pdv',     'Transfert stock Point de vente → Point de vente'),
    ]
    perms = {}
    for code, nom in nouvelles:
        p, _ = PermissionPersonnalisee.objects.get_or_create(code=code, defaults={'nom': nom})
        perms[code] = p

    assignations = {
        'MANAGER':           ['acces_transfert_depot_pdv', 'acces_transfert_pdv_depot',
                              'acces_transfert_depot_depot', 'acces_transfert_pdv_pdv'],
        'ASSISTANT_MANAGER': ['acces_transfert_depot_pdv', 'acces_transfert_pdv_depot',
                              'acces_transfert_depot_depot', 'acces_transfert_pdv_pdv'],
        'MAGASINIER':        ['acces_transfert_depot_pdv', 'acces_transfert_depot_depot'],
        'LOGISTICIEN':       ['acces_transfert_depot_pdv', 'acces_transfert_pdv_depot',
                              'acces_transfert_depot_depot', 'acces_transfert_pdv_pdv'],
    }
    for famille, codes in assignations.items():
        for role in Role.objects.filter(famille_metier=famille):
            for code in codes:
                RolePermission.objects.get_or_create(role=role, permission=perms[code])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('utilisateur', '0016_permissions_stock_depot_pdv'),
    ]
    operations = [
        migrations.RunPython(creer_permissions, noop_reverse),
    ]
