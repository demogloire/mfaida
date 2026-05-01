from django.db import migrations


def creer_permission(apps, schema_editor):
    PermissionPersonnalisee = apps.get_model('utilisateur', 'PermissionPersonnalisee')
    PermissionPersonnalisee.objects.get_or_create(
        code='voir_prix_achat_ht',
        defaults={
            'nom': "Consulter les prix d'achat et coûts (produits, stock, ajustements)",
        },
    )


def supprimer_permission(apps, schema_editor):
    PermissionPersonnalisee = apps.get_model('utilisateur', 'PermissionPersonnalisee')
    PermissionPersonnalisee.objects.filter(code='voir_prix_achat_ht').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('utilisateur', '0006_accesdepot_accespointvente'),
    ]

    operations = [
        migrations.RunPython(creer_permission, supprimer_permission),
    ]
