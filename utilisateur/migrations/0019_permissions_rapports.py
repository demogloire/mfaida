from django.db import migrations


def creer_permissions(apps, schema_editor):
    PermissionPersonnalisee = apps.get_model('utilisateur', 'PermissionPersonnalisee')
    RolePermission          = apps.get_model('utilisateur', 'RolePermission')
    Role                    = apps.get_model('utilisateur', 'Role')

    nouvelles = [
        ('acces_module_rapports',   'Rapports — accès au module'),
        ('rapports_ventes',         'Rapports — ventes et facturation'),
        ('rapports_stock',          'Rapports — stock et inventaire'),
        ('rapports_rh',             'Rapports — ressources humaines'),
        ('rapports_finance',        'Rapports — caisse, dépenses et finance'),
        ('rapports_tiers',          'Rapports — clients et fournisseurs'),
        ('rapports_achats',         'Rapports — achats et commandes'),
        ('rapports_export_pdf',     'Rapports — export PDF'),
    ]

    perms = {}
    for code, nom in nouvelles:
        p, _ = PermissionPersonnalisee.objects.get_or_create(code=code, defaults={'nom': nom})
        perms[code] = p

    # Toutes les permissions rapports selon la famille de rôle
    assignations = {
        'MANAGER':           list(perms.keys()),
        'ASSISTANT_MANAGER': list(perms.keys()),
        'FINANCIER':         ['acces_module_rapports', 'rapports_ventes', 'rapports_finance', 'rapports_tiers', 'rapports_achats', 'rapports_export_pdf'],
        'COMPTABLE':         ['acces_module_rapports', 'rapports_ventes', 'rapports_finance', 'rapports_tiers', 'rapports_achats', 'rapports_export_pdf'],
        'VENDEUR':           ['acces_module_rapports', 'rapports_ventes', 'rapports_tiers'],
        'MAGASINIER':        ['acces_module_rapports', 'rapports_stock'],
        'RH':                ['acces_module_rapports', 'rapports_rh'],
    }

    for famille, codes in assignations.items():
        for role in Role.objects.filter(famille_metier=famille):
            for code in codes:
                RolePermission.objects.get_or_create(role=role, permission=perms[code])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('utilisateur', '0018_permissions_caisse'),
    ]
    operations = [
        migrations.RunPython(creer_permissions, noop_reverse),
    ]
