from django.db import migrations


def creer_permissions(apps, schema_editor):
    PermissionPersonnalisee = apps.get_model('utilisateur', 'PermissionPersonnalisee')
    RolePermission = apps.get_model('utilisateur', 'RolePermission')
    Role = apps.get_model('utilisateur', 'Role')

    nouvelles = [
        ('acces_module_caisse',      'Caisse — accès au module (sessions, transactions)'),
        ('ouvrir_session_caisse',    'Caisse — ouvrir une session'),
        ('cloturer_session_caisse',  'Caisse — soumettre la clôture de session'),
        ('approuver_cloture_caisse', 'Caisse — approuver ou rejeter la clôture (manager)'),
        ('depot_retrait_caisse',     'Caisse — dépôts et retraits manuels'),
        ('acces_rapport_caisse',     'Caisse — rapports et historique complet'),
    ]
    perms = {}
    for code, nom in nouvelles:
        p, _ = PermissionPersonnalisee.objects.get_or_create(code=code, defaults={'nom': nom})
        perms[code] = p

    assignations = {
        'MANAGER': list(perms.keys()),
        'ASSISTANT_MANAGER': list(perms.keys()),
        'CAISSIER':  ['acces_module_caisse', 'ouvrir_session_caisse', 'cloturer_session_caisse'],
        'VENDEUR':   ['acces_module_caisse', 'ouvrir_session_caisse', 'cloturer_session_caisse'],
        'FINANCIER': ['acces_module_caisse', 'acces_rapport_caisse'],
        'COMPTABLE': ['acces_module_caisse', 'acces_rapport_caisse'],
    }
    for famille, codes in assignations.items():
        for role in Role.objects.filter(famille_metier=famille):
            for code in codes:
                RolePermission.objects.get_or_create(role=role, permission=perms[code])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('utilisateur', '0017_permissions_transferts_stock'),
    ]
    operations = [
        migrations.RunPython(creer_permissions, noop_reverse),
    ]
