from django.db import migrations


class Migration(migrations.Migration):
    """
    Migration state-only : retire OrdreAchat et LigneOrdreAchat de l'état Django
    de l'app entreprise sans supprimer les tables physiques
    (elles sont maintenant gérées par l'app achat).
    """

    dependencies = [
        ('entreprise', '0021_remove_client_fournisseur'),
        ('achat', '0001_initial'),
    ]

    state_operations = [
        migrations.DeleteModel(name='LigneOrdreAchat'),
        migrations.DeleteModel(name='OrdreAchat'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=state_operations,
            database_operations=[],
        )
    ]
