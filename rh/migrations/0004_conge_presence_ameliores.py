from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('rh', '0003_departement_branche'),
        ('utilisateur', '0001_initial'),
    ]

    operations = [
        # --- Présence ---
        migrations.AddField(
            model_name='presence',
            name='note',
            field=models.CharField(blank=True, default='', max_length=200),
        ),
        migrations.AlterField(
            model_name='presence',
            name='statut',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('PRESENT', 'Présent'),
                    ('RETARD',  'Retard'),
                    ('ABSENT',  'Absent'),
                    ('CONGE',   'En congé'),
                    ('FERIE',   'Jour férié'),
                ],
                default='PRESENT',
            ),
        ),
        migrations.AlterField(
            model_name='presence',
            name='heure_arrivee',
            field=models.TimeField(null=True, blank=True),
        ),
        migrations.AlterField(
            model_name='presence',
            name='heure_depart',
            field=models.TimeField(null=True, blank=True),
        ),
        migrations.AlterUniqueTogether(
            name='presence',
            unique_together={('employe', 'date')},
        ),

        # --- Congé ---
        migrations.AlterField(
            model_name='conge',
            name='type_conge',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('ANNUEL',    'Congé annuel'),
                    ('MALADIE',   'Maladie'),
                    ('MATERNITE', 'Maternité / Paternité'),
                    ('SANS_SOLDE','Sans solde'),
                    ('AUTRE',     'Autre'),
                ],
            ),
        ),
        migrations.AddField(
            model_name='conge',
            name='motif',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='conge',
            name='statut',
            field=models.CharField(
                max_length=12,
                choices=[
                    ('DEMANDE',   'Demandé'),
                    ('APPROUVEE', 'Approuvé'),
                    ('REJETEE',   'Rejeté'),
                    ('ANNULEE',   'Annulé'),
                ],
                default='DEMANDE',
            ),
        ),
        migrations.AddField(
            model_name='conge',
            name='demande_par',
            field=models.ForeignKey(
                default=1,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='conges_demandes',
                to='utilisateur.profil',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='conge',
            name='date_demande',
            field=models.DateTimeField(default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='conge',
            name='approuve_par',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='conges_traites',
                to='utilisateur.profil',
            ),
        ),
        migrations.AddField(
            model_name='conge',
            name='date_approbation',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='conge',
            name='note_approbation',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.RemoveField(
            model_name='conge',
            name='approuve',
        ),
    ]
