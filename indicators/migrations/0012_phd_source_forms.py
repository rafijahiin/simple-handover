"""
Wire each PHD SL indicator to its source Kobo form so the Target Config
'Source Form' column stops showing '—'.

Adds 3 KoboFormMapping rows for the consolidated PHD forms, then assigns
each SL target's source_form FK:

  SL1  (FSWs HIV/STI screened)        → Patient Services
  SL2  (GBV survivors identified)     → Patient Services
  SL3  (FSWs MH counselling)          → Patient Services
  SL4  (outreach sessions)            → Activity & Operations
  SL5a-e (commodities)                → Activity & Operations  (Stock register)
  SL6  (HIV+/STI+ referred)           → Patient Services
  SL7  (GBV→MHPSS referrals)          → Patient Services
  SL8  (functional centres — static)  → (no form)
  SL9  (mobile camps)                 → Activity & Operations
  SL10-13 (training/orientation/peers) → Activity & Operations
  SL14 (coord meetings)               → Activity & Operations
  SL15a-c (boards/signs/billboards)   → Activity & Operations
  SL16 (GBV corners)                  → Activity & Operations
"""
from django.db import migrations
import uuid


PHD_FORM_MAPPINGS = [
    # (slug, label, kobo_uid_env)
    ('phd_registration_v1',      'PHD-1 — FSW Registration (Mother List)',
        'aGWfLrP2yNXqnAiBKuvVgv'),
    ('phd_patient_services_v1',  'PHD-2 — Patient Services',
        'apsQ6HRBRh9eyZJx7R35Jv'),
    ('phd_activity_ops_v1',      'PHD-3 — Activity & Operations',
        'aHTK33qJJN8HavF8Ww53yC'),
]

# Activity code → source form slug
SL_TO_FORM = {
    'SL1':   'phd_patient_services_v1',
    'SL2':   'phd_patient_services_v1',
    'SL3':   'phd_patient_services_v1',
    'SL4':   'phd_activity_ops_v1',
    'SL5a':  'phd_activity_ops_v1',
    'SL5b':  'phd_activity_ops_v1',
    'SL5c':  'phd_activity_ops_v1',
    'SL5d':  'phd_activity_ops_v1',
    'SL5e':  'phd_activity_ops_v1',
    'SL6':   'phd_patient_services_v1',
    'SL7':   'phd_patient_services_v1',
    # SL8 — no form, it's the static ServiceCenter registry
    'SL9':   'phd_activity_ops_v1',
    'SL10':  'phd_activity_ops_v1',
    'SL11':  'phd_activity_ops_v1',
    'SL12':  'phd_activity_ops_v1',
    'SL13':  'phd_activity_ops_v1',
    'SL14':  'phd_activity_ops_v1',
    'SL15a': 'phd_activity_ops_v1',
    'SL15b': 'phd_activity_ops_v1',
    'SL15c': 'phd_activity_ops_v1',
    'SL16':  'phd_activity_ops_v1',
}


def _forward(apps, schema_editor):
    KoboFormMapping = apps.get_model('indicators', 'KoboFormMapping')
    IndicatorTarget = apps.get_model('indicators', 'IndicatorTarget')
    Partner         = apps.get_model('partners', 'Partner')

    phd = Partner.objects.filter(code='PHD').first()
    if phd is None:
        return

    # 1. Create the 3 PHD form mappings (idempotent via update_or_create)
    forms_by_slug = {}
    for slug, label, kobo_uid in PHD_FORM_MAPPINGS:
        form, _ = KoboFormMapping.objects.update_or_create(
            form_slug=slug,
            defaults={
                'form_label':     label,
                'partner':        phd,
                'kobo_asset_uid': kobo_uid,
                'is_active':      True,
            },
        )
        forms_by_slug[slug] = form

    # 2. Link each PHD SL target to its form
    for activity_code, form_slug in SL_TO_FORM.items():
        form = forms_by_slug[form_slug]
        IndicatorTarget.objects.filter(
            partner=phd,
            activity_code=activity_code,
        ).update(source_form=form)


def _reverse(apps, schema_editor):
    IndicatorTarget = apps.get_model('indicators', 'IndicatorTarget')
    KoboFormMapping = apps.get_model('indicators', 'KoboFormMapping')
    Partner         = apps.get_model('partners', 'Partner')

    phd = Partner.objects.filter(code='PHD').first()
    if phd is None:
        return
    IndicatorTarget.objects.filter(partner=phd).update(source_form=None)
    KoboFormMapping.objects.filter(
        form_slug__in=[s for s, _, _ in PHD_FORM_MAPPINGS],
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('indicators', '0011_phd_sl_targets_clean_rebuild'),
    ]

    operations = [
        migrations.RunPython(_forward, _reverse),
    ]
