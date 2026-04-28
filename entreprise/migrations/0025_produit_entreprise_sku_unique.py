# Generated manually — SKU unique par entreprise

import django.db.models.deletion
from django.db import migrations, models
from django.db.models import OuterRef, Subquery


def backfill_produit_entreprise(apps, schema_editor):
    Produit = apps.get_model('entreprise', 'Produit')
    SousCategorie = apps.get_model('entreprise', 'SousCategorie')
    Produit.objects.update(
        entreprise_id=Subquery(
            SousCategorie.objects.filter(pk=OuterRef('sous_categorie_id')).values(
                'categorie__entreprise_id'
            )[:1]
        )
    )


def normalize_dedupe_sku_par_entreprise(apps, schema_editor):
    Produit = apps.get_model('entreprise', 'Produit')
    Produit.objects.filter(sku='').update(sku=None)
    for p in Produit.objects.exclude(sku__isnull=True).only('id', 'sku'):
        if not (p.sku or '').strip():
            Produit.objects.filter(pk=p.pk).update(sku=None)

    seen = set()
    for p in (
        Produit.objects.exclude(sku__isnull=True)
        .order_by('entreprise_id', 'sku', 'id')
        .only('id', 'entreprise_id', 'sku')
    ):
        key = (p.entreprise_id, p.sku)
        if key in seen:
            Produit.objects.filter(pk=p.pk).update(sku=None)
        else:
            seen.add(key)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('entreprise', '0024_produit_sku_unique_mysql'),
    ]

    operations = [
        migrations.AddField(
            model_name='produit',
            name='entreprise',
            field=models.ForeignKey(
                help_text="Renseigne automatiquement selon la sous-categorie ; sert a l'unicite du SKU.",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='produits',
                to='entreprise.entreprise',
                verbose_name='Entreprise',
            ),
        ),
        migrations.RunPython(backfill_produit_entreprise, noop),
        migrations.RemoveConstraint(
            model_name='produit',
            name='uniq_produit_sku_par_sous_categorie',
        ),
        migrations.RunPython(normalize_dedupe_sku_par_entreprise, noop),
        migrations.AlterField(
            model_name='produit',
            name='entreprise',
            field=models.ForeignKey(
                help_text="Renseigne automatiquement selon la sous-categorie ; sert a l'unicite du SKU.",
                on_delete=django.db.models.deletion.CASCADE,
                related_name='produits',
                to='entreprise.entreprise',
                verbose_name='Entreprise',
            ),
        ),
        migrations.AddConstraint(
            model_name='produit',
            constraint=models.UniqueConstraint(
                fields=('entreprise', 'sku'),
                name='uniq_produit_sku_par_entreprise',
            ),
        ),
    ]
