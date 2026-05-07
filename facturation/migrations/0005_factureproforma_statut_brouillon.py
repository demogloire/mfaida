from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('facturation', '0004_factureproforma_approbation'),
    ]

    operations = [
        migrations.AlterField(
            model_name='factureproforma',
            name='statut',
            field=models.CharField(
                choices=[
                    ('BROUILLON', 'Brouillon'),
                    ('EN_ATTENTE', "En attente d'approbation"),
                    ('ACCEPTEE', 'Acceptée / Convertie'),
                    ('EXPIREE', 'Expirée'),
                    ('ANNULEE', 'Annulée'),
                ],
                default='BROUILLON',
                max_length=20,
            ),
        ),
    ]
