from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('achat', '0004_rename_quantite_ecartee_quantite_ecarter'),
    ]

    operations = [
        migrations.RenameField(
            model_name='lignebonreception',
            old_name='motif_ecart',
            new_name='motif_ecarter',
        ),
        migrations.AlterField(
            model_name='lignebonreception',
            name='motif_ecarter',
            field=models.CharField(
                blank=True,
                max_length=255,
                verbose_name='Motif mise à l’écart',
            ),
        ),
    ]
