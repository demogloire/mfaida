from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('rh', '0002_avance_salaire'),
        ('entreprise', '0002_fournisseur_produit_methode_gestion_produit_vie_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='departement',
            name='branche',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='departements',
                to='entreprise.branche',
            ),
        ),
    ]
