from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('stock', '0003_alter_ligneordreachat_fk'),
    ]

    operations = [
        migrations.AddField(
            model_name='mouvementstock',
            name='marque',
            field=models.CharField(blank=True, default='', max_length=100, verbose_name='Marque'),
        ),
        migrations.AddField(
            model_name='mouvementstock',
            name='conditionnement',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Ex. carton 12 pcs, bidon 5 L…',
                max_length=100,
                verbose_name='Taille du conditionnement / emballage',
            ),
        ),
    ]
