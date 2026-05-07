from django.db import migrations


def creer_permissions(apps, schema_editor):
    PermissionPersonnalisee = apps.get_model('utilisateur', 'PermissionPersonnalisee')
    RolePermission = apps.get_model('utilisateur', 'RolePermission')
    Role = apps.get_model('utilisateur', 'Role')

    nouvelles = [
        ('acces_bons_ajustement',    "Bons d'ajustement de stock (création, validation)"),
        ('acces_mise_a_ecart',       "Mise à l'écart de stock (quarantaine, retrait)"),
        ('acces_campagnes_inventaire', "Campagnes d'inventaire (création, clôture)"),
    ]

    perms = {}
    for code, nom in nouvelles:
        p, _ = PermissionPersonnalisee.objects.get_or_create(code=code, defaults={'nom': nom})
        perms[code] = p

    # Rôles autorisés : Manager, Assistant Manager, Magasinier, Logisticien
    familles_cibles = ['MANAGER', 'ASSISTANT_MANAGER', 'MAGASINIER', 'LOGISTICIEN']
    for role in Role.objects.filter(famille_metier__in=familles_cibles):
        for perm in perms.values():
            RolePermission.objects.get_or_create(role=role, permission=perm)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('utilisateur', '0014_permissions_depenses'),
    ]

    operations = [
        migrations.RunPython(creer_permissions, noop_reverse),
    ]
