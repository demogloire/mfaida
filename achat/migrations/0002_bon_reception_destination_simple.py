import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('achat', '0001_initial'),
        ('entreprise', '0025_produit_entreprise_sku_unique'),
        ('tiers', '0003_client_entreprise_code_unique'),
    ]

    operations = [
        migrations.AddField(
            model_name='bonreception',
            name='fournisseur',
            field=models.ForeignKey(
                blank=True,
                help_text='Pour une réception sans bon de commande.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='receptions_directes',
                to='tiers.fournisseur',
                verbose_name='Fournisseur',
            ),
        ),
        migrations.AddField(
            model_name='bonreception',
            name='point_destination',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='receptions',
                to='entreprise.pointvente',
                verbose_name='Point de vente (boutique) de réception',
            ),
        ),
        migrations.AlterField(
            model_name='bonreception',
            name='depot_destination',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='receptions',
                to='entreprise.depot',
                verbose_name='Dépôt de réception',
            ),
        ),
        migrations.AlterField(
            model_name='bonreception',
            name='ordre_achat',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='receptions',
                to='achat.ordreachat',
                verbose_name='Bon de commande',
            ),
        ),
        migrations.AddField(
            model_name='lignebonreception',
            name='conditionnement',
            field=models.CharField(
                blank=True,
                max_length=100,
                verbose_name='Taille du conditionnement',
            ),
        ),
        migrations.AddField(
            model_name='lignebonreception',
            name='dateexpiration',
            field=models.DateField(blank=True, null=True, verbose_name="Date d'expiration"),
        ),
        migrations.AddField(
            model_name='lignebonreception',
            name='dateproduction',
            field=models.DateField(blank=True, null=True, verbose_name='Date de production'),
        ),
        migrations.AddField(
            model_name='lignebonreception',
            name='marque',
            field=models.CharField(blank=True, max_length=100, verbose_name='Marque'),
        ),
        migrations.AddField(
            model_name='lignebonreception',
            name='prix_unitaire_ht',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Réception hors commande : si vide, le prix catalogue du produit est utilisé.",
                max_digits=15,
                null=True,
                verbose_name="Prix d'achat unitaire HT",
            ),
        ),
        migrations.AddField(
            model_name='lignebonreception',
            name='produit',
            field=models.ForeignKey(
                blank=True,
                help_text='Pour un bon sans commande.',
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='lignes_bon_reception',
                to='entreprise.produit',
                verbose_name='Produit (réception simple)',
            ),
        ),
        migrations.AlterField(
            model_name='lignebonreception',
            name='ligne_ordre_achat',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='lignes_reception',
                to='achat.ligneordreachat',
            ),
        ),
    ]
