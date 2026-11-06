"""
Reconcile Bandhu ServiceCenters to the canonical set from the MIS
Requirements document: 8 community-friendly Drop-In Centres (one per project
district) + 1 Dhaka Key Population Clinic.

The earlier seed created only 5 DICs (incl. a Dhaka DIC). This migration:
  - registers the new KP_CLINIC center_type choice,
  - upserts the canonical 9 centres (correct district / type / active),
  - deactivates any other Bandhu centre not in the canonical set so stale
    rows never inflate indicator 1.8 (8 DICs) or 1.6 (1 KP clinic).

Deactivation (is_active=False), not deletion — submissions may reference
these centres via FK.
"""
from django.db import migrations, models


# (code, name, name_bangla, center_type, district, upazila, lat, lng)
CANONICAL = [
    ('BND-DIC-01', 'Bandhu DIC Sunamganj',   'বন্ধু ডিআইসি সুনামগঞ্জ',  'DIC', 'Sunamganj',   'Sunamganj Sadar',   24.8817, 91.4053),
    ('BND-DIC-02', 'Bandhu DIC Bandarban',   'বন্ধু ডিআইসি বান্দরবান',  'DIC', 'Bandarban',   'Bandarban Sadar',   22.1953, 92.2184),
    ('BND-DIC-03', 'Bandhu DIC Chandpur',    'বন্ধু ডিআইসি চাঁদপুর',    'DIC', 'Chandpur',    'Chandpur Sadar',    23.2333, 90.6500),
    ('BND-DIC-04', 'Bandhu DIC Noakhali',    'বন্ধু ডিআইসি নোয়াখালী',  'DIC', 'Noakhali',    'Noakhali Sadar',    22.8697, 91.0994),
    ('BND-DIC-05', 'Bandhu DIC Chattogram',  'বন্ধু ডিআইসি চট্টগ্রাম',  'DIC', 'Chittagong',  'Kotwali',           22.3569, 91.7832),
    ('BND-DIC-06', 'Bandhu DIC Narayanganj', 'বন্ধু ডিআইসি নারায়ণগঞ্জ', 'DIC', 'Narayanganj', 'Narayanganj Sadar', 23.6238, 90.5000),
    ('BND-DIC-07', 'Bandhu DIC Habiganj',    'বন্ধু ডিআইসি হবিগঞ্জ',    'DIC', 'Habiganj',    'Habiganj Sadar',    24.3745, 91.4155),
    ('BND-DIC-08', 'Bandhu DIC Manikganj',   'বন্ধু ডিআইসি মানিকগঞ্জ',  'DIC', 'Manikganj',   'Manikganj Sadar',   23.8617, 90.0003),
    ('BND-KPC-01', 'Bandhu KP Clinic Dhaka', 'বন্ধু কেপি ক্লিনিক ঢাকা', 'KP_CLINIC', 'Dhaka',  'Dhaka Sadar',       23.7104, 90.4074),
]


def _forward(apps, schema_editor):
    ServiceCenter = apps.get_model('programs', 'ServiceCenter')
    canonical_codes = {row[0] for row in CANONICAL}

    for code, name, name_bn, ctype, district, upazila, lat, lng in CANONICAL:
        ServiceCenter.objects.update_or_create(
            code=code,
            defaults={
                'organisation': 'Bandhu',
                'name': name,
                'name_bangla': name_bn,
                'center_type': ctype,
                'district': district,
                'upazila': upazila,
                'latitude': lat,
                'longitude': lng,
                'is_active': True,
            },
        )

    # Deactivate any other Bandhu centre not in the canonical set.
    ServiceCenter.objects.filter(organisation='Bandhu').exclude(
        code__in=canonical_codes
    ).update(is_active=False)


def _reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('programs', '0011_gbvcornerrecord_approved_at_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='servicecenter',
            name='center_type',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('DIC', 'Drop-In Center'),
                    ('BROTHEL', 'Brothel-Based Center'),
                    ('SUB_DIC', 'Sub Drop-In Center'),
                    ('MOBILE', 'Mobile Outreach'),
                    ('KP_CLINIC', 'Key Population Clinic'),
                ],
            ),
        ),
        migrations.RunPython(_forward, _reverse),
    ]
