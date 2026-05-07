from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('facturation', '0007_retourvente_approbation'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='PaiementFacture',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('numero', models.CharField(db_index=True, editable=False, max_length=50, unique=True)),
                ('montant', models.DecimalField(decimal_places=2, max_digits=15)),
                ('mode_paiement', models.CharField(
                    choices=[
                        ('CASH',         'Espèces'),
                        ('MOBILE_MONEY', 'Mobile Money'),
                        ('CARTE',        'Carte bancaire'),
                        ('CHEQUE',       'Chèque'),
                        ('VIREMENT',     'Virement bancaire'),
                    ],
                    default='CASH',
                    max_length=20,
                )),
                ('date_paiement', models.DateTimeField(auto_now_add=True)),
                ('notes', models.TextField(blank=True, default='')),
                ('facture', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='paiements',
                    to='facturation.facture',
                )),
                ('effectue_par', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='paiements_factures',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Paiement de facture',
                'verbose_name_plural': 'Paiements de factures',
                'ordering': ['-date_paiement'],
            },
        ),
    ]
