from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('achat', '0003_bonreception_cree_par'),
    ]

    operations = [
        migrations.RenameField(
            model_name='lignebonreception',
            old_name='quantite_ecartee',
            new_name='quantite_ecarter',
        ),
    ]
