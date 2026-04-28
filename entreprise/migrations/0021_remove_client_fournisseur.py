from django.db import migrations


class Migration(migrations.Migration):
    """
    Migration state-only : retire Client et Fournisseur de l'état Django de l'app entreprise
    sans supprimer les tables physiques (elles sont maintenant gérées par l'app tiers).
    """

    dependencies = [
        ('entreprise', '0020_alter_depot_options_alter_pointvente_options_and_more'),
        ('tiers', '0001_initial'),
    ]

    state_operations = [
        migrations.DeleteModel(name='Client'),
        migrations.DeleteModel(name='Fournisseur'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=state_operations,
            database_operations=[],
        )
    ]
