from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('utilisateur', '0009_permission_acces_module_rh'),
    ]

    operations = [
        migrations.AlterField(
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
                    ('RESSOURCES_HUMAINES', 'Ressources humaines (entreprise)'),
                ],
                default='',
                help_text=(
                    'Type de poste pour proposer les accès types ; '
                    'peut être affine par les permissions du rôle.'
                ),
                max_length=24,
                verbose_name='famille métier',
            ),
        ),
    ]
