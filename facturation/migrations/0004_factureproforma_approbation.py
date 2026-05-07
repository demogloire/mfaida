from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('facturation', '0003_rename_ligne_facture_mouvement'),
        ('utilisateur', '0012_permission_achat_bons_commande'),
    ]

    operations = [
        migrations.AddField(
            model_name='factureproforma',
            name='soumis_le',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='factureproforma',
            name='approuve_par',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='proformas_approuvees',
                to='utilisateur.profil',
            ),
        ),
        migrations.AddField(
            model_name='factureproforma',
            name='date_approbation',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='factureproforma',
            name='commentaire_manager',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AlterField(
            model_name='factureproforma',
            name='vendeur',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='proformas_crees',
                to='utilisateur.profil',
            ),
        ),
    ]
