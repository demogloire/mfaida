from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """
    Met à jour les FK client dans Facture et FactureProforma
    pour pointer vers tiers.Client au lieu de entreprise.Client.
    """

    dependencies = [
        ('facturation', '0001_initial'),
        ('tiers', '0001_initial'),
        ('entreprise', '0021_remove_client_fournisseur'),
    ]

    operations = [
        migrations.AlterField(
            model_name='facture',
            name='client',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='factures',
                to='tiers.client',
            ),
        ),
        migrations.AlterField(
            model_name='factureproforma',
            name='client',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                to='tiers.client',
            ),
        ),
    ]
