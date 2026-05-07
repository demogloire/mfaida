# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tiers', '0003_client_entreprise_code_unique'),
    ]

    operations = [
        migrations.AddField(
            model_name='client',
            name='est_client_passager',
            field=models.BooleanField(
                default=False,
                help_text="Client occasionnel enregistré rapidement lors d'un achat, à distinguer d'un client suivi régulièrement.",
                verbose_name='Client passager / comptoir',
            ),
        ),
    ]
