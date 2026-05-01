# Generated manually — liaison mise à l'écart ↔ ligne MouvementStock.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stock', '0007_bon_ajustement_trace'),
    ]

    operations = [
        migrations.AddField(
            model_name='stockmiseaecart',
            name='mouvement_stock',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='mises_a_ecart',
                to='stock.mouvementstock',
            ),
        ),
    ]
