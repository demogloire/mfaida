from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """
    Met à jour le FK ligneordreachat dans MouvementStock
    pour pointer vers achat.LigneOrdreAchat au lieu de entreprise.LigneOrdreAchat.
    """

    dependencies = [
        ('stock', '0002_mouvementstock_location_code_and_more'),
        ('achat', '0001_initial'),
        ('entreprise', '0022_remove_ordreachat_ligneordreachat'),
    ]

    operations = [
        migrations.AlterField(
            model_name='mouvementstock',
            name='ligneordreachat',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to='achat.ligneordreachat',
            ),
        ),
    ]
