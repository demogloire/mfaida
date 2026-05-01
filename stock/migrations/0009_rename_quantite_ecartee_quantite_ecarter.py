# Renommage champ opérationnel « à l'écart » (≠ écart campagne inventaire).

from decimal import Decimal

from django.db import migrations


def aligner_actif_legacy_ecarter_br(apps, schema_editor):
    """Anciens BR : quantite_active était = reçu sans soustraire l’écarter saisi."""
    MouvementStock = apps.get_model('stock', 'MouvementStock')
    for m in MouvementStock.objects.all().iterator(chunk_size=800):
        recu = m.quantite_recu or Decimal('0')
        ec = m.quantite_ecarter or Decimal('0')
        act = m.quantite_active or Decimal('0')
        aff = m.quantite_affectee or Decimal('0')
        if ec <= 0 or aff != 0:
            continue
        if act == recu and recu >= ec:
            na = recu - ec
            if na >= 0 and na != act:
                m.quantite_active = na
                m.save(update_fields=['quantite_active'])


class Migration(migrations.Migration):

    dependencies = [
        ('stock', '0008_stockmiseaecart_mouvement_stock'),
    ]

    operations = [
        migrations.RenameField(
            model_name='mouvementstock',
            old_name='quantite_ecartee',
            new_name='quantite_ecarter',
        ),
        migrations.RunPython(aligner_actif_legacy_ecarter_br, migrations.RunPython.noop),
    ]
