from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('rh', '0004_conge_presence_ameliores'),
        ('entreprise', '0001_initial'),
        ('utilisateur', '0001_initial'),
    ]

    operations = [
        # ── Supprimer les anciens champs simples de BulletinPaie ──────────────
        migrations.RemoveField(model_name='bulletinpaie', name='est_paye'),

        # ── Ajouter les nouveaux champs à BulletinPaie ────────────────────────
        migrations.AddField(
            model_name='bulletinpaie',
            name='numero',
            field=models.CharField(blank=True, db_index=True, default='', editable=False, max_length=50),
        ),
        migrations.AddField(
            model_name='bulletinpaie',
            name='contrat',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='bulletins', to='rh.contrat',
            ),
        ),
        migrations.AddField(
            model_name='bulletinpaie',
            name='devise',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to='entreprise.devise',
            ),
        ),
        migrations.AddField(
            model_name='bulletinpaie',
            name='jours_ouvrables',
            field=models.IntegerField(default=26),
        ),
        migrations.AddField(
            model_name='bulletinpaie',
            name='jours_prestes',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='bulletinpaie',
            name='jours_conges',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='bulletinpaie',
            name='jours_absences',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='bulletinpaie',
            name='salaire_base_ref',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=15),
        ),
        migrations.AddField(
            model_name='bulletinpaie',
            name='retenues_avances',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=15),
        ),
        migrations.AddField(
            model_name='bulletinpaie',
            name='statut',
            field=models.CharField(
                choices=[('BROUILLON', 'Brouillon'), ('VALIDE', 'Validé'), ('PAYE', 'Payé')],
                default='BROUILLON', max_length=12,
            ),
        ),
        migrations.AddField(
            model_name='bulletinpaie',
            name='note',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='bulletinpaie',
            name='cree_par',
            field=models.ForeignKey(
                default=1,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='bulletins_crees',
                to='utilisateur.profil',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='bulletinpaie',
            name='date_creation',
            field=models.DateTimeField(default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='bulletinpaie',
            name='valide_par',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='bulletins_valides',
                to='utilisateur.profil',
            ),
        ),
        migrations.AddField(
            model_name='bulletinpaie',
            name='date_validation',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='bulletinpaie',
            name='paye_par',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='bulletins_payes',
                to='utilisateur.profil',
            ),
        ),
        migrations.AlterField(
            model_name='bulletinpaie',
            name='date_paiement',
            field=models.DateTimeField(blank=True, null=True),
        ),

        # ── Contrainte unique + meta ──────────────────────────────────────────
        migrations.AlterUniqueTogether(
            name='bulletinpaie',
            unique_together={('employe', 'periode_mois', 'periode_annee')},
        ),

        # ── Créer LigneBulletin ───────────────────────────────────────────────
        migrations.CreateModel(
            name='LigneBulletin',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('type', models.CharField(
                    choices=[('AVANTAGE', 'Avantage / Allocation'), ('RETENUE', 'Retenue')],
                    max_length=10,
                )),
                ('libelle', models.CharField(max_length=200)),
                ('montant', models.DecimalField(decimal_places=2, max_digits=15)),
                ('bulletin', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='lignes',
                    to='rh.bulletinpaie',
                )),
                ('avance', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='ligne_bulletin',
                    to='rh.avancesalaire',
                )),
            ],
            options={'ordering': ['type', 'libelle']},
        ),
    ]
