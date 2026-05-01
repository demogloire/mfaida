"""Ajoute BonReception.cree_par (créateur du bon, automatique)."""

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('achat', '0002_bon_reception_destination_simple'),
    ]

    operations = [
        migrations.AddField(
            model_name='bonreception',
            name='cree_par',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name='receptions_creees',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Créé par',
            ),
        ),
    ]
