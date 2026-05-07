from django.db import migrations, models


def seed_permissions_et_retrocompat_roles(apps, schema_editor):
    PermissionPersonnalisee = apps.get_model('utilisateur', 'PermissionPersonnalisee')
    Role = apps.get_model('utilisateur', 'Role')
    RolePermission = apps.get_model('utilisateur', 'RolePermission')

    definitions = [
        (
            'acces_configuration_entreprise',
            "Configurer l'entreprise (branches, dépôts, points de vente, devises)",
        ),
        ('acces_configuration_catalogue', 'Gérer le catalogue produits (catégories, import)'),
        ('acces_module_tiers', 'Clients et fournisseurs'),
        ('acces_module_achat', 'Achats et réceptions'),
        ('acces_module_stock', 'Stock, inventaires et mouvements'),
        ('acces_module_vente', 'Facturation et ventes'),
        (
            'acces_module_finance',
            'Finance et comptabilité (modules dédiés à brancher sous /finance/)',
        ),
        (
            'acces_administration_utilisateurs',
            'Utilisateurs, rôles, permissions et journal de connexion',
        ),
        (
            'voir_prix_achat_ht',
            "Consulter les prix d'achat et les coûts (PA HT, valorisation)",
        ),
    ]
    for code, nom in definitions:
        PermissionPersonnalisee.objects.get_or_create(code=code, defaults={'nom': nom})

    jeu_manager = frozenset(c for c, _ in definitions)
    perms_par_code = {
        p.code: p
        for p in PermissionPersonnalisee.objects.filter(code__in=jeu_manager)
    }
    missing = jeu_manager - set(perms_par_code.keys())
    if missing:
        raise RuntimeError(f"Permissions introuvable après création : {sorted(missing)}")

    manager_code = 'MANAGER'

    for role in Role.objects.all().iterator():
        if RolePermission.objects.filter(role_id=role.pk).exists():
            continue
        for code in jeu_manager:
            p = perms_par_code.get(code)
            if p:
                RolePermission.objects.get_or_create(role_id=role.pk, permission_id=p.pk)
        Role.objects.filter(pk=role.pk).update(famille_metier=manager_code)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('utilisateur', '0007_permission_voir_prix_achat_ht'),
    ]

    operations = [
        migrations.AddField(
            model_name='role',
            name='famille_metier',
            field=models.CharField(
                blank=True,
                choices=[
                    ('MANAGER', 'Manager entreprise'),
                    ('ASSISTANT_MANAGER', 'Assistant manager entreprise'),
                    ('CAISSIER', 'Caissier (point de vente)'),
                    ('VENDEUR', 'Vendeur (point de vente)'),
                    ('MAGASINIER', 'Magasinier (dépôt)'),
                    ('FINANCIER', 'Financier'),
                    ('COMPTABLE', 'Comptable'),
                    ('LOGISTICIEN', 'Logisticien'),
                ],
                default='',
                help_text='Type de poste pour proposer les accès types ; peut être affine par les permissions du rôle.',
                max_length=24,
                verbose_name='famille métier',
            ),
        ),
        migrations.RunPython(seed_permissions_et_retrocompat_roles, noop_reverse),
    ]
