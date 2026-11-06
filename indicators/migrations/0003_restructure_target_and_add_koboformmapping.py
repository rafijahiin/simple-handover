"""
Step 2 of the IDMS rebuild — restructure IndicatorTarget for the new
data model and introduce KoboFormMapping.

Old IndicatorTarget shape (organisation CharField + indicator_code +
period_start/end) is replaced with the partner-FK + activity_code +
nullable target_value shape. Existing IndicatorTarget rows on the
production Postgres are zero (verified) — the table was last seeded
into the now-wiped ephemeral SQLite, never against Postgres. So this
migration deletes any leftover rows and reshapes the table fields
in a single step.
"""
import uuid

from django.conf import settings
from django.db import migrations, models


def _clear_existing_indicator_rows(apps, schema_editor):
    """Wipe any pre-existing IndicatorTarget rows. Safe because nothing
    persistent has been written here yet — but explicit, so the schema
    operations below cannot fail on stranded rows."""
    IndicatorTarget = apps.get_model('indicators', 'IndicatorTarget')
    IndicatorTarget.objects.all().delete()


def _noop(apps, schema_editor):
    """Reverse direction. Nothing to restore."""


class Migration(migrations.Migration):

    dependencies = [
        ('indicators', '0002_alter_indicatortarget_organisation'),
        ('partners',   '0001_initial'),
        ('accounts',   '0004_remap_super_admin_role'),
    ]

    operations = [
        # 1. Drop any existing IndicatorTarget rows (zero rows expected).
        migrations.RunPython(_clear_existing_indicator_rows, _noop),

        # 1b. Clear the old unique_together BEFORE removing the fields it
        #     references, otherwise SQLite cannot remake the table.
        migrations.AlterUniqueTogether(
            name='indicatortarget',
            unique_together=set(),
        ),

        # 2. Create KoboFormMapping table.
        migrations.CreateModel(
            name='KoboFormMapping',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('form_slug', models.CharField(max_length=80, unique=True,
                    help_text="Stable identifier, e.g. 'spondon_clinic_visit_v1'.")),
                ('form_label', models.CharField(max_length=200,
                    help_text="Human-readable name, e.g. 'Clinic Visit (KF-02)'.")),
                ('kobo_asset_uid', models.CharField(blank=True, max_length=80,
                    help_text='KoboToolbox asset UID. Mirrors KOBO_ASSET_UID_* env vars.')),
                ('is_active', models.BooleanField(default=True)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('partner', models.ForeignKey(
                    null=True, blank=True,
                    on_delete=models.deletion.PROTECT,
                    related_name='kobo_forms',
                    to='partners.partner',
                    help_text='Null = cross-partner form.',
                )),
            ],
            options={
                'verbose_name': 'Kobo Form Mapping',
                'verbose_name_plural': 'Kobo Form Mappings',
                'ordering': ['form_slug'],
            },
        ),

        # 3. Reshape IndicatorTarget — remove old columns first.
        migrations.RemoveField(model_name='indicatortarget', name='organisation'),
        migrations.RemoveField(model_name='indicatortarget', name='indicator_code'),
        migrations.RemoveField(model_name='indicatortarget', name='indicator_name'),
        migrations.RemoveField(model_name='indicatortarget', name='objective'),
        migrations.RemoveField(model_name='indicatortarget', name='activity_ref'),
        migrations.RemoveField(model_name='indicatortarget', name='period_start'),
        migrations.RemoveField(model_name='indicatortarget', name='period_end'),

        # 4. Add the new columns.
        migrations.AddField(
            model_name='indicatortarget',
            name='partner',
            field=models.ForeignKey(
                on_delete=models.deletion.PROTECT,
                related_name='indicator_targets',
                to='partners.partner',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='indicatortarget',
            name='objective_number',
            field=models.PositiveSmallIntegerField(default=1,
                help_text='SIDA objective number. 0 = Overall (renders above Obj 1).'),
        ),
        migrations.AddField(
            model_name='indicatortarget',
            name='activity_code',
            field=models.CharField(db_index=True, default='', max_length=10,
                help_text="Short activity ref, e.g. '1.1' or '1.5a' for sub-rows."),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='indicatortarget',
            name='activity_label',
            field=models.CharField(default='', max_length=400),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='indicatortarget',
            name='indicator_label',
            field=models.CharField(default='', max_length=600),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='indicatortarget',
            name='source_form',
            field=models.ForeignKey(
                null=True, blank=True,
                on_delete=models.deletion.SET_NULL,
                related_name='indicators',
                to='indicators.koboformmapping',
                help_text='Which Kobo form generates this indicator. Filled at workshop.',
            ),
        ),
        migrations.AddField(
            model_name='indicatortarget',
            name='updated_by',
            field=models.ForeignKey(
                null=True, blank=True,
                on_delete=models.deletion.SET_NULL,
                related_name='+',
                to=settings.AUTH_USER_MODEL,
            ),
        ),

        # 5. target_value becomes nullable (was required).
        migrations.AlterField(
            model_name='indicatortarget',
            name='target_value',
            field=models.DecimalField(
                decimal_places=2, max_digits=14, null=True, blank=True,
                help_text='Numeric target. Null = "Not Set" — display orange pill.',
            ),
        ),

        # 6. Reshape Meta — new unique_together and ordering.
        migrations.AlterUniqueTogether(
            name='indicatortarget',
            unique_together={('partner', 'activity_code', 'indicator_label')},
        ),
        migrations.AlterModelOptions(
            name='indicatortarget',
            options={
                'ordering': ['partner__code', 'objective_number', 'activity_code'],
                'verbose_name': 'Indicator Target',
                'verbose_name_plural': 'Indicator Targets',
            },
        ),
    ]
