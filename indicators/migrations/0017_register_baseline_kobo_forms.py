"""
Register the two D5 baseline KoboToolbox forms in the KoboFormMapping registry.

Both are CIPRB-conducted (the baseline study is CIPRB's, not Bandhu's/PHD's),
distinguished by population. Live asset UIDs from the 2026-06-26 deploy.

Idempotent (update_or_create by form_slug).
"""
from django.db import migrations


BASELINE_FORMS = [
    ('ciprb_baseline_hijra_v1', 'CIPRB Baseline — Hijra / Gender-diverse Population', 'aBT7aCL9p4FGcW4WwXZcr6'),
    ('ciprb_baseline_fsw_v1',   'CIPRB Baseline — Female Sex Workers (Brothel & Street)', 'aVsJ7VJ35k8GshpQpnXygC'),
]


def _forward(apps, schema_editor):
    Partner = apps.get_model('partners', 'Partner')
    KoboFormMapping = apps.get_model('indicators', 'KoboFormMapping')
    ciprb = {p.code: p for p in Partner.objects.all()}.get('CIPRB')
    for slug, label, uid in BASELINE_FORMS:
        KoboFormMapping.objects.update_or_create(
            form_slug=slug,
            defaults={
                'form_label': label,
                'partner': ciprb,
                'kobo_asset_uid': uid,
                'is_active': True,
            },
        )


def _reverse(apps, schema_editor):
    KoboFormMapping = apps.get_model('indicators', 'KoboFormMapping')
    KoboFormMapping.objects.filter(
        form_slug__in=[slug for slug, _, _ in BASELINE_FORMS],
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('indicators', '0016_phd_service_log_source_form'),
        ('partners', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(_forward, _reverse),
    ]
