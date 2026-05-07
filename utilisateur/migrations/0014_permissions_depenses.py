from django.db import migrations


def creer_permissions(apps, schema_editor):
    PermissionPersonnalisee = apps.get_model('utilisateur', 'PermissionPersonnalisee')
    RolePermission = apps.get_model('utilisateur', 'RolePermission')
    Role = apps.get_model('utilisateur', 'Role')

    acces, _ = PermissionPersonnalisee.objects.get_or_create(
        code='acces_module_depenses',
        defaults={'nom': 'Dépenses caisse (liste, consultation)'},
    )
    valider, _ = PermissionPersonnalisee.objects.get_or_create(
        code='valider_depense',
        defaults={'nom': 'Valider ou annuler une dépense caisse'},
    )

    # Caissier, Vendeur, Manager, Assistant Manager, Financier, Comptable
    familles_cibles = [
        'MANAGER', 'ASSISTANT_MANAGER', 'CAISSIER', 'VENDEUR', 'FINANCIER', 'COMPTABLE',
    ]
    for role in Role.objects.filter(famille_metier__in=familles_cibles):
        RolePermission.objects.get_or_create(role=role, permission=acces)
        RolePermission.objects.get_or_create(role=role, permission=valider)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('utilisateur', '0013_permission_approuver_proforma'),
    ]

    operations = [
        migrations.RunPython(creer_permissions, noop_reverse),
    ]
