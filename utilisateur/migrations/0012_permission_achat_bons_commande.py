from django.db import migrations


def creer_et_raccorder(apps, schema_editor):
    PermissionPersonnalisee = apps.get_model('utilisateur', 'PermissionPersonnalisee')
    RolePermission = apps.get_model('utilisateur', 'RolePermission')

    bc, _ = PermissionPersonnalisee.objects.get_or_create(
        code='acces_achat_bons_commande',
        defaults={
            'nom': (
                'Bons de commande — création, modification, envoi et lignes '
                '(sous-module achats ; les réceptions restent sous « Achats » général)'
            ),
        },
    )

    achat_perm = PermissionPersonnalisee.objects.filter(code='acces_module_achat').first()
    if not achat_perm:
        return
    role_ids = RolePermission.objects.filter(permission_id=achat_perm.pk).values_list(
        'role_id', flat=True
    )
    for role_id in set(role_ids):
        RolePermission.objects.get_or_create(role_id=role_id, permission_id=bc.pk)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('utilisateur', '0011_permission_facturation_proforma_et_ventes_retournees'),
    ]

    operations = [
        migrations.RunPython(creer_et_raccorder, noop_reverse),
    ]
