from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):
    """
    Migration mixte :
    - State-only pour OrdreAchat et LigneOrdreAchat (tables déjà dans la DB sous entreprise_*)
    - Création physique des nouvelles tables BonReception et LigneBonReception
    """

    initial = True

    dependencies = [
        ('entreprise', '0021_remove_client_fournisseur'),
        ('tiers', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    # ── Opérations d'état seulement (modèles existants déplacés) ──
    state_operations_existing = [
        migrations.CreateModel(
            name='OrdreAchat',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('numero_commande', models.CharField(editable=False, max_length=50, unique=True)),
                ('date_commande', models.DateTimeField(auto_now_add=True)),
                ('date_livraison_prevue', models.DateField(blank=True, null=True)),
                ('statut', models.CharField(choices=[('BROUILLON', 'Brouillon'), ('ENVOYE', 'Envoyé au Fournisseur'), ('RECU_PARTIEL', 'Reçu Partiellement'), ('RECU_TOTAL', 'Reçu Totalement'), ('ANNULE', 'Annulé')], default='BROUILLON', max_length=20)),
                ('total_ht', models.DecimalField(decimal_places=2, default=0.0, max_digits=15)),
                ('total_tva', models.DecimalField(decimal_places=2, default=0.0, max_digits=15)),
                ('total_ttc', models.DecimalField(decimal_places=2, default=0.0, max_digits=15)),
                ('notes', models.TextField(blank=True)),
                ('entreprise', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ordres_achat', to='entreprise.entreprise')),
                ('fournisseur', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='ordres_achat', to='tiers.fournisseur')),
                ('depot_destination', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='entreprise.depot')),
                ('pointdevente_destination', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='entreprise.pointvente')),
                ('devise', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='entreprise.devise')),
                ('cree_par', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='ordres_achat', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': "Ordre d'achat",
                'verbose_name_plural': "Ordres d'achat",
                'db_table': 'entreprise_ordreachat',
                'ordering': ['-date_commande'],
            },
        ),
        migrations.CreateModel(
            name='LigneOrdreAchat',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantite_commandee', models.DecimalField(decimal_places=2, max_digits=15)),
                ('quantite_recue', models.DecimalField(decimal_places=2, default=0.0, max_digits=15)),
                ('dateproduction', models.DateField(blank=True, null=True)),
                ('dateexpiration', models.DateField(blank=True, null=True)),
                ('lot_batch', models.CharField(blank=True, default='', max_length=20)),
                ('unite', models.CharField(blank=True, default='', max_length=20)),
                ('reception', models.BooleanField(default=False)),
                ('prix_unitaire_ht', models.DecimalField(decimal_places=2, max_digits=15)),
                ('sous_total_ht', models.DecimalField(decimal_places=2, default=0, editable=False, max_digits=15)),
                ('ordre_achat', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='lignes', to='achat.ordreachat')),
                ('produit', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='entreprise.produit')),
                ('location', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='entreprise.location')),
            ],
            options={
                'verbose_name': "Ligne d'ordre d'achat",
                'verbose_name_plural': "Lignes d'ordre d'achat",
                'db_table': 'entreprise_ligneordreachat',
            },
        ),
    ]

    # ── Opérations physiques pour les NOUVEAUX modèles ──
    database_operations_new = [
        migrations.CreateModel(
            name='BonReception',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('numero_reception', models.CharField(editable=False, max_length=50, unique=True)),
                ('date_reception', models.DateTimeField(auto_now_add=True)),
                ('statut', models.CharField(choices=[('EN_COURS', 'En cours'), ('VALIDE', 'Validé'), ('ANNULE', 'Annulé')], default='EN_COURS', max_length=20)),
                ('notes', models.TextField(blank=True)),
                ('ordre_achat', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='receptions', to='achat.ordreachat')),
                ('depot_destination', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='receptions', to='entreprise.depot')),
                ('recu_par', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='receptions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Bon de réception',
                'verbose_name_plural': 'Bons de réception',
                'ordering': ['-date_reception'],
            },
        ),
        migrations.CreateModel(
            name='LigneBonReception',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantite_recue_effective', models.DecimalField(decimal_places=2, max_digits=15)),
                ('quantite_ecartee', models.DecimalField(decimal_places=2, default=0.0, max_digits=15)),
                ('motif_ecart', models.CharField(blank=True, max_length=255)),
                ('lot_batch', models.CharField(blank=True, default='', max_length=20)),
                ('bon_reception', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='lignes', to='achat.bonreception')),
                ('ligne_ordre_achat', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='lignes_reception', to='achat.ligneordreachat')),
                ('location', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='entreprise.location')),
            ],
            options={
                'verbose_name': 'Ligne de bon de réception',
                'verbose_name_plural': 'Lignes de bon de réception',
            },
        ),
    ]

    operations = [
        # Étape 1 : déclarer OrdreAchat et LigneOrdreAchat dans l'état Django sans toucher la DB
        migrations.SeparateDatabaseAndState(
            state_operations=state_operations_existing,
            database_operations=[],
        ),
        # Étape 2 : créer physiquement BonReception et LigneBonReception
        *database_operations_new,
    ]
