from django.db import migrations


def creer_et_raccorder(apps, schema_editor):
    PermissionPersonnalisee = apps.get_model('utilisateur', 'PermissionPersonnalisee')
    RolePermission = apps.get_model('utilisateur', 'RolePermission')

    proforma, _ = PermissionPersonnalisee.objects.get_or_create(
        code='acces_facturation_proforma',
        defaults={
            'nom': (
                'Factures proforma (devis ou commande avant facturation définitive — '
                'écran liste / création lorsque disponible)'
            ),
        },
    )
    retours, _ = PermissionPersonnalisee.objects.get_or_create(
        code='acces_ventes_retournees',
        defaults={
            'nom': 'Ventes retournées (suivi avoirs et retours — écrans lorsque disponibles)',
        },
    )

    vente_perm = PermissionPersonnalisee.objects.filter(code='acces_module_vente').first()
    if not vente_perm:
        return
    role_ids = RolePermission.objects.filter(permission_id=vente_perm.pk).values_list(
        'role_id', flat=True
    )
    for role_id in set(role_ids):
        RolePermission.objects.get_or_create(role_id=role_id, permission_id=proforma.pk)
        RolePermission.objects.get_or_create(role_id=role_id, permission_id=retours.pk)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('utilisateur', '0010_role_famille_metier_rh'),
    ]

    operations = [
        migrations.RunPython(creer_et_raccorder, noop_reverse),
    ]
