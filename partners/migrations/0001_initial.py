"""
Create Partner table and seed the three implementing partners.

Per IDMS handoff:
  CIPRB  = #0072BC (blue)
  Bandhu = #00B050 (green)
  PHD    = #ED7D31 (orange)

UNFPA is NOT seeded here — it is the funder/supervisor org, not an
implementing partner. UNFPA users continue to use the Organisation enum.
"""
import uuid

from django.db import migrations, models


SEED_DATA = [
    {
        'code':        'CIPRB',
        'name':        'Centre for Injury Prevention and Research, Bangladesh',
        'name_bangla': 'বাংলাদেশ ইনজুরি প্রিভেনশন অ্যান্ড রিসার্চ সেন্টার',
        'color_hex':   '#0072BC',
    },
    {
        'code':        'Bandhu',
        'name':        'Bandhu Social Welfare Society',
        'name_bangla': 'বন্ধু সামাজিক কল্যাণ সমিতি',
        'color_hex':   '#00B050',
    },
    {
        'code':        'PHD',
        'name':        'Partners in Health and Development',
        'name_bangla': 'পার্টনার্স ইন হেলথ অ্যান্ড ডেভেলপমেন্ট',
        'color_hex':   '#ED7D31',
    },
]


def _forward(apps, schema_editor):
    Partner = apps.get_model('partners', 'Partner')
    for row in SEED_DATA:
        Partner.objects.update_or_create(code=row['code'], defaults=row)


def _reverse(apps, schema_editor):
    Partner = apps.get_model('partners', 'Partner')
    Partner.objects.filter(code__in=[r['code'] for r in SEED_DATA]).delete()


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='Partner',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('code', models.CharField(db_index=True, max_length=20, unique=True,
                    help_text="Canonical short code: 'CIPRB' | 'Bandhu' | 'PHD'.")),
                ('name', models.CharField(max_length=200)),
                ('name_bangla', models.CharField(blank=True, max_length=200)),
                ('color_hex', models.CharField(default='#00658C', max_length=7,
                    help_text='Hex color for map and dashboard accents. '
                              "CIPRB=#0072BC (blue), Bandhu=#00B050 (green), PHD=#ED7D31 (orange).")),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Partner',
                'verbose_name_plural': 'Partners',
                'ordering': ['code'],
            },
        ),
        migrations.RunPython(_forward, _reverse),
    ]
