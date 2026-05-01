# Generated manually for plan stock / facturation alignment

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stock', '0004_mouvementstock_marque_conditionnement'),
    ]

    operations = [
        migrations.AddField(
            model_name='mouvementstock',
            name='origine',
            field=models.CharField(
                choices=[
                    ('BR', 'Bon de réception'),
                    ('AJUSTEMENT', 'Ajustement manuel'),
                    ('INVENTAIRE', 'Inventaire (écart physique)'),
                    ('VENTE', 'Sortie vente (facture)'),
                ],
                default='BR',
                max_length=20,
                verbose_name='Origine du mouvement',
            ),
        ),
        migrations.AddField(
            model_name='mouvementstock',
            name='motif',
            field=models.TextField(blank=True, default='', verbose_name='Motif / commentaire'),
        ),
        migrations.AddField(
            model_name='mouvementstock',
            name='reference_piece',
            field=models.CharField(blank=True, default='', max_length=80, verbose_name='Référence pièce'),
        ),
        migrations.AddField(
            model_name='mouvementstock',
            name='inventaire',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='mouvements_correction',
                to='stock.inventaire',
                verbose_name='Inventaire lié',
            ),
        ),
        migrations.AddField(
            model_name='mouvementstock',
            name='sens_adjustement',
            field=models.IntegerField(
                blank=True,
                choices=[(1, 'Entrée'), (-1, 'Sortie interne')],
                help_text='Rempli uniquement pour les lignes d’ajustement manuel (+ entrée stock, − sortie).',
                null=True,
                verbose_name='Sens ajustement',
            ),
        ),
        migrations.AlterField(
            model_name='inventaire',
            name='lot',
            field=models.CharField(blank=True, default='', max_length=20),
        ),
    ]
