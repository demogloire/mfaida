# Generated manually — renommage FK ligne facture pour clarté

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('facturation', '0002_alter_client_fk'),
        ('stock', '0005_stock_plan_features'),
    ]

    operations = [
        migrations.RenameField(
            model_name='lignefacture',
            old_name='stock',
            new_name='mouvement_stock',
        ),
        migrations.AlterField(
            model_name='lignefacture',
            name='mouvement_stock',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='lignes_factures',
                to='stock.mouvementstock',
            ),
        ),
        migrations.AlterField(
            model_name='lignefacture',
            name='produit',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='facture_ligne_produit',
                to='entreprise.produit',
            ),
        ),
    ]
