from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """
    Migration state-only : déclare Client et Fournisseur dans l'app tiers
    sans créer de nouvelles tables (les tables entreprise_client et
    entreprise_fournisseur existent déjà dans la DB).
    """

    initial = True

    dependencies = [
        ('entreprise', '0020_alter_depot_options_alter_pointvente_options_and_more'),
    ]

    state_operations = [
        migrations.CreateModel(
            name='Fournisseur',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('intial', models.CharField(blank=True, default='', max_length=255)),
                ('reference', models.CharField(blank=True, default='', max_length=255)),
                ('code_fournisseur', models.CharField(max_length=255)),
                ('nom_societe', models.CharField(max_length=255)),
                ('rccm_id', models.CharField(blank=True, max_length=100, verbose_name='ID Fiscal / RCCM')),
                ('contact_nom', models.CharField(blank=True, max_length=100)),
                ('telephone', models.CharField(max_length=20)),
                ('email', models.EmailField(blank=True)),
                ('adresse', models.TextField()),
                ('ville', models.CharField(blank=True, max_length=100)),
                ('solde_du', models.DecimalField(decimal_places=2, default=0.0, max_digits=15)),
                ('notes', models.TextField(blank=True)),
                ('est_actif', models.BooleanField(default=True)),
                ('date_enregistrement', models.DateTimeField(auto_now_add=True)),
                ('entreprise', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='fournisseurs', to='entreprise.entreprise')),
            ],
            options={
                'verbose_name': 'Fournisseur',
                'verbose_name_plural': 'Fournisseurs',
                'db_table': 'entreprise_fournisseur',
            },
        ),
        migrations.CreateModel(
            name='Client',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('intial', models.CharField(max_length=255)),
                ('reference', models.CharField(max_length=255)),
                ('code_client', models.CharField(max_length=255)),
                ('nom', models.CharField(max_length=255)),
                ('type_client', models.CharField(choices=[('AUTRE', 'Autre type client'), ('DETAIL', 'Particulier / Détail'), ('GROS', 'Grossiste / Entreprise')], default='DETAIL', max_length=10)),
                ('telephone', models.CharField(max_length=20)),
                ('email', models.EmailField(blank=True)),
                ('adresse', models.TextField(blank=True)),
                ('limite_credit', models.DecimalField(decimal_places=2, default=0.0, max_digits=15)),
                ('solde_compte', models.DecimalField(decimal_places=2, default=0.0, max_digits=15)),
                ('points_fidelite', models.IntegerField(default=0)),
                ('notes', models.TextField(blank=True)),
                ('est_actif', models.BooleanField(default=True)),
                ('date_creation', models.DateTimeField(auto_now_add=True)),
                ('branche', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='clients', to='entreprise.branche')),
            ],
            options={
                'verbose_name': 'Client',
                'verbose_name_plural': 'Clients',
                'db_table': 'entreprise_client',
            },
        ),
        migrations.AddConstraint(
            model_name='fournisseur',
            constraint=models.UniqueConstraint(fields=['entreprise', 'code_fournisseur'], name='uniq_fournisseur_code_par_entreprise'),
        ),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=state_operations,
            database_operations=[],
        )
    ]
