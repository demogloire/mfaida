from django.db import migrations


def creer_et_raccorder_rh(apps, schema_editor):
    PermissionPersonnalisee = apps.get_model('utilisateur', 'PermissionPersonnalisee')
    Role = apps.get_model('utilisateur', 'Role')
    RolePermission = apps.get_model('utilisateur', 'RolePermission')

    rh, _ = PermissionPersonnalisee.objects.get_or_create(
        code='acces_module_rh',
        defaults={
            'nom': (
                'Ressources humaines (employés, contrats, présence, '
                'congés et paie lorsque disponibles)'
            ),
        },
    )

    famille_rh_direct = frozenset({
        'MANAGER',
        'ASSISTANT_MANAGER',
        'FINANCIER',
        'COMPTABLE',
    })

    for role in Role.objects.iterator():
        fm = (getattr(role, 'famille_metier', None) or '').strip()
        if fm in famille_rh_direct:
            RolePermission.objects.get_or_create(role_id=role.pk, permission_id=rh.pk)
            continue
        ok = RolePermission.objects.filter(
            role_id=role.pk,
            permission__code='acces_administration_utilisateurs',
        ).exists()
        if ok:
            RolePermission.objects.get_or_create(role_id=role.pk, permission_id=rh.pk)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('utilisateur', '0008_role_famille_metier_et_permissions_modules'),
    ]

    operations = [
        migrations.RunPython(creer_et_raccorder_rh, noop_reverse),
    ]
