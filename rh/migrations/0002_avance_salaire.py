from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('rh', '0001_initial'),
        ('caisse', '0001_session_transaction'),
        ('entreprise', '0002_fournisseur_produit_methode_gestion_produit_vie_and_more'),
        ('utilisateur', '0002_profil_profil_id'),
    ]

    operations = [
        migrations.CreateModel(
            name='AvanceSalaire',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('numero', models.CharField(db_index=True, editable=False, max_length=50, unique=True)),
                ('montant', models.DecimalField(decimal_places=2, max_digits=15)),
                ('motif', models.TextField(blank=True, default='')),
                ('statut', models.CharField(
                    choices=[
                        ('DEMANDE', 'Demandée'),
                        ('APPROUVEE', 'Approuvée'),
                        ('DECAISSEE', 'Décaissée'),
                        ('REMBOURSEE', 'Remboursée'),
                        ('REJETEE', 'Rejetée'),
                    ],
                    default='DEMANDE',
                    max_length=12,
                )),
                ('date_demande', models.DateTimeField(auto_now_add=True)),
                ('date_approbation', models.DateTimeField(blank=True, null=True)),
                ('note_approbation', models.TextField(blank=True, default='')),
                ('date_decaissement', models.DateTimeField(blank=True, null=True)),
                ('approuve_par', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='avances_approuvees',
                    to='utilisateur.profil',
                )),
                ('decaisse_par', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='avances_decaissees',
                    to='utilisateur.profil',
                )),
                ('demande_par', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='avances_demandees',
                    to='utilisateur.profil',
                )),
                ('devise', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    to='entreprise.devise',
                )),
                ('employe', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='avances_salaire',
                    to='rh.employe',
                )),
                ('point_vente', models.ForeignKey(
                    help_text='Point de vente dont la caisse sera débitée lors du décaissement.',
                    on_delete=django.db.models.deletion.PROTECT,
                    to='entreprise.pointvente',
                )),
                ('transaction_caisse', models.OneToOneField(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='avance_salaire',
                    to='caisse.transactioncaisse',
                )),
            ],
            options={
                'verbose_name': 'Avance sur salaire',
                'verbose_name_plural': 'Avances sur salaire',
                'ordering': ['-date_demande'],
            },
        ),
    ]
