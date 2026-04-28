from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Ajoute les champs notes et est_actif à Client,
    et notes à Fournisseur (champs ajoutés dans le nouveau modèle tiers).
    """

    dependencies = [
        ('tiers', '0001_initial'),
    ]

    operations = [
        # ── Fournisseur ──
        migrations.AddField(
            model_name='fournisseur',
            name='notes',
            field=models.TextField(blank=True, default=''),
            preserve_default=False,
        ),
        # ── Client ──
        migrations.AddField(
            model_name='client',
            name='notes',
            field=models.TextField(blank=True, default=''),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='client',
            name='est_actif',
            field=models.BooleanField(default=True),
        ),
    ]
