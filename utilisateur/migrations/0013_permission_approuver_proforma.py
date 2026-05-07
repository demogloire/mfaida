from django.db import migrations


def creer_permission(apps, schema_editor):
    PermissionPersonnalisee = apps.get_model('utilisateur', 'PermissionPersonnalisee')
    RolePermission = apps.get_model('utilisateur', 'RolePermission')
    Role = apps.get_model('utilisateur', 'Role')

    perm, _ = PermissionPersonnalisee.objects.get_or_create(
        code='approuver_facture_proforma',
        defaults={
            'nom': 'Approuver ou rejeter les factures proforma (managers)',
        },
    )

    # Accorder la permission aux rôles Manager et Assistant Manager
    roles_cibles = Role.objects.filter(famille_metier__in=['MANAGER', 'ASSISTANT_MANAGER'])
    for role in roles_cibles:
        RolePermission.objects.get_or_create(role=role, permission=perm)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('utilisateur', '0012_permission_achat_bons_commande'),
    ]

    operations = [
        migrations.RunPython(creer_permission, noop_reverse),
    ]
