"""
Register the 10 live CIPRB KoboToolbox forms in the KoboFormMapping registry.

When the CIPRB Phase-2 forms were deployed to KoboToolbox (and CIPRB 10 —
MPDSR Response Plan — added later), the deploy created the Kobo assets but
never added matching KoboFormMapping rows, so the registry only held two old
`spondon_fistula_*` placeholders. This seeds one row per real `ciprb_*` form,
pinned to the CIPRB partner, with its live asset UID — so indicators can
reference the correct source form and the registry reflects reality.

Idempotent (update_or_create by form_slug). UIDs verified live 2026-06-15.
"""
from django.db import migrations


CIPRB_FORMS = [
    ('ciprb_fistula_questions_v1',       'CIPRB 1 — Fistula Question Bank',                   'aH86Euq2AeJ8S9VYdry4PC'),
    ('ciprb_mpdsr_community_maternal_v1', 'CIPRB 2 — MPDSR Form 01 (Community Maternal Death)', 'apvPk7qq94nry2aW3z7y4H'),
    ('ciprb_mpdsr_community_neonatal_v1', 'CIPRB 3 — MPDSR Form 02 (Community Neonatal Death)', 'awQXeYhuLoLrM38fwSrF8y'),
    ('ciprb_mpdsr_facility_maternal_v1',  'CIPRB 4 — MPDSR Form 04 (Facility Maternal Death)',  'aVQbxhGnDHNCe6AazSJByM'),
    ('ciprb_mpdsr_facility_neonatal_v1',  'CIPRB 5 — MPDSR Form 05 (Facility Neonatal Death)',  'a6pg47mTt8E56igHnK8SSD'),
    ('ciprb_social_autopsy_v1',           'CIPRB 6 — Social Autopsy (Maternal Death)',          'a6vQiCJ3tz4MRxKqdMHCbA'),
    ('ciprb_notification_slip_01_v1',     'CIPRB 7 — Death Notification Slip 01',               'aSnEgQT6DUooVanZXubhAF'),
    ('ciprb_notification_slip_02_v1',     'CIPRB 8 — Death Notification Slip 02',               'aaCnfRHHgkukkhDgXwUnXX'),
    ('ciprb_near_miss_v1',                'CIPRB 9 — Maternal Near Miss audit',                 'aTzdRTvhZ8yUQCGhA8UG5R'),
    ('ciprb_mpdsr_response_plan_v1',      'CIPRB 10 — MPDSR Response Plan',                     'auFCf7bfBDtrP6xeW5F2KJ'),
]


def _forward(apps, schema_editor):
    Partner = apps.get_model('partners', 'Partner')
    KoboFormMapping = apps.get_model('indicators', 'KoboFormMapping')
    ciprb = {p.code: p for p in Partner.objects.all()}.get('CIPRB')
    for slug, label, uid in CIPRB_FORMS:
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
        form_slug__in=[slug for slug, _, _ in CIPRB_FORMS],
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('indicators', '0014_bandhu_18_indicators'),
        ('partners', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(_forward, _reverse),
    ]
