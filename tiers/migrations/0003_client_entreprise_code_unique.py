from django.db import migrations, models
from django.db.models import Count
import django.db.models.deletion


def add_entreprise_column_if_needed(apps, schema_editor):
    """Colonne parfois déjà créée si une migration précédente a échoué au milieu du fichier."""
    connection = schema_editor.connection
    table = 'entreprise_client'
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
              AND COLUMN_NAME = 'entreprise_id'
            """,
            [table],
        )
        if cursor.fetchone()[0]:
            return
    schema_editor.execute(
        'ALTER TABLE entreprise_client ADD COLUMN entreprise_id BIGINT NULL'
    )
    schema_editor.execute(
        """ALTER TABLE entreprise_client
           ADD CONSTRAINT tiers_client_entreprise_id_fk
           FOREIGN KEY (entreprise_id) REFERENCES entreprise_entreprise (id)
           ON DELETE CASCADE"""
    )


def drop_entreprise_column_if_safe(apps, schema_editor):
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'entreprise_client'
              AND CONSTRAINT_NAME = 'tiers_client_entreprise_id_fk'
            """
        )
        if cursor.fetchone()[0]:
            schema_editor.execute(
                'ALTER TABLE entreprise_client DROP FOREIGN KEY tiers_client_entreprise_id_fk'
            )
    schema_editor.execute('ALTER TABLE entreprise_client DROP COLUMN entreprise_id')


def fill_entreprise_depuis_branche(apps, schema_editor):
    Client = apps.get_model('tiers', 'Client')
    Branche = apps.get_model('entreprise', 'Branche')
    for c in Client.objects.all().iterator():
        if not c.branche_id:
            continue
        ent_id = (
            Branche.objects.filter(pk=c.branche_id).values_list('entreprise_id', flat=True).first()
        )
        if ent_id:
            Client.objects.filter(pk=c.pk).update(entreprise_id=ent_id)


def _max_cli_suffix(Client, ent_id, prefix, exclude_pk=None):
    max_num = 0
    qs = Client.objects.filter(entreprise_id=ent_id, code_client__startswith=prefix)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    for row in qs.only('code_client'):
        tail = row.code_client[len(prefix) :]
        try:
            max_num = max(max_num, int(tail))
        except ValueError:
            continue
    return max_num


def dedupe_codes_par_entreprise(apps, schema_editor):
    Client = apps.get_model('tiers', 'Client')
    PREFIX = 'CLI-'

    dup_groups = (
        Client.objects.values('entreprise_id', 'code_client')
        .annotate(n=Count('pk'))
        .filter(n__gt=1)
    )
    for g in dup_groups:
        eid = g['entreprise_id']
        code = g['code_client']
        if not eid:
            continue
        pks = list(
            Client.objects.filter(entreprise_id=eid, code_client=code).order_by('pk').values_list('pk', flat=True)
        )
        for pk in pks[1:]:
            next_num = _max_cli_suffix(Client, eid, PREFIX, exclude_pk=pk) + 1
            Client.objects.filter(pk=pk).update(
                intial=PREFIX,
                reference=f'{next_num:06d}',
                code_client=f'{PREFIX}{next_num:06d}',
            )


class Migration(migrations.Migration):

    dependencies = [
        ('tiers', '0002_add_notes_est_actif'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(add_entreprise_column_if_needed, migrations.RunPython.noop),
            ],
            state_operations=[
                migrations.AddField(
                    model_name='client',
                    name='entreprise',
                    field=models.ForeignKey(
                        help_text='Redondant avec la branche ; utilisé pour garantir un code client unique par société.',
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='clients_societe',
                        to='entreprise.entreprise',
                    ),
                ),
            ],
        ),
        migrations.RunPython(fill_entreprise_depuis_branche, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='client',
            name='intial',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AlterField(
            model_name='client',
            name='reference',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.RunPython(dedupe_codes_par_entreprise, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='client',
            name='code_client',
            field=models.CharField(db_index=True, max_length=64),
        ),
        migrations.AlterField(
            model_name='client',
            name='entreprise',
            field=models.ForeignKey(
                help_text='Redondant avec la branche ; utilisé pour garantir un code client unique par société.',
                on_delete=django.db.models.deletion.CASCADE,
                related_name='clients_societe',
                to='entreprise.entreprise',
            ),
        ),
        migrations.AddConstraint(
            model_name='client',
            constraint=models.UniqueConstraint(
                fields=('entreprise', 'code_client'),
                name='uniq_client_code_par_entreprise',
            ),
        ),
    ]
