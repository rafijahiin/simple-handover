"""
Re-point PHD SL indicators' source_form to the LIVE merged Service Log.

Migration 0012 wired every PHD SL target's source_form FK to the now-
DECOMMISSIONED split forms phd_patient_services_v1 ('PHD-2 — Patient
Services') and phd_activity_ops_v1 ('PHD-3 — Activity & Operations'). The
live build uses ONE merged form, phd_service_log_v1 ('PHD 2 — Service Log'),
so Target Config's 'Source Form' column showed dead form names. This points
those targets at the merged form and retires the two legacy mappings.

Data-only migration (no schema change); fully reversible.
"""
from django.db import migrations


SERVICE_LOG = ('phd_service_log_v1', 'PHD 2 — Service Log', 'aDv2CZapM2eSqijKr2WZKc')

# slug -> (label, kobo_uid) — the split forms migration 0012 created.
LEGACY = {
    'phd_patient_services_v1': ('PHD-2 — Patient Services', 'apsQ6HRBRh9eyZJx7R35Jv'),
    'phd_activity_ops_v1':     ('PHD-3 — Activity & Operations', 'aHTK33qJJN8HavF8Ww53yC'),
}

# The exact code->form split migration 0012 applied (used to restore on reverse).
SL_TO_LEGACY = {
    'SL1': 'phd_patient_services_v1', 'SL2': 'phd_patient_services_v1',
    'SL3': 'phd_patient_services_v1', 'SL6': 'phd_patient_services_v1',
    'SL7': 'phd_patient_services_v1',
    'SL4': 'phd_activity_ops_v1', 'SL5a': 'phd_activity_ops_v1',
    'SL5b': 'phd_activity_ops_v1', 'SL5c': 'phd_activity_ops_v1',
    'SL5d': 'phd_activity_ops_v1', 'SL5e': 'phd_activity_ops_v1',
    'SL9': 'phd_activity_ops_v1', 'SL10': 'phd_activity_ops_v1',
    'SL11': 'phd_activity_ops_v1', 'SL12': 'phd_activity_ops_v1',
    'SL13': 'phd_activity_ops_v1', 'SL14': 'phd_activity_ops_v1',
    'SL15a': 'phd_activity_ops_v1', 'SL15b': 'phd_activity_ops_v1',
    'SL15c': 'phd_activity_ops_v1', 'SL16': 'phd_activity_ops_v1',
}


def _forward(apps, schema_editor):
    KoboFormMapping = apps.get_model('indicators', 'KoboFormMapping')
    IndicatorTarget = apps.get_model('indicators', 'IndicatorTarget')
    Partner = apps.get_model('partners', 'Partner')

    phd = Partner.objects.filter(code='PHD').first()
    if phd is None:
        return

    slug, label, uid = SERVICE_LOG
    service_log, _ = KoboFormMapping.objects.update_or_create(
        form_slug=slug,
        defaults={'form_label': label, 'partner': phd,
                  'kobo_asset_uid': uid, 'is_active': True},
    )

    # Re-point every PHD SL target that pointed at a decommissioned split form.
    for code in SL_TO_LEGACY:
        IndicatorTarget.objects.filter(
            partner=phd, activity_code=code,
        ).update(source_form=service_log)

    # Retire the dead split-form mappings so they drop out of the registry.
    KoboFormMapping.objects.filter(form_slug__in=list(LEGACY)).update(is_active=False)


def _reverse(apps, schema_editor):
    KoboFormMapping = apps.get_model('indicators', 'KoboFormMapping')
    IndicatorTarget = apps.get_model('indicators', 'IndicatorTarget')
    Partner = apps.get_model('partners', 'Partner')

    phd = Partner.objects.filter(code='PHD').first()
    if phd is None:
        return

    forms = {}
    for slug, (label, uid) in LEGACY.items():
        form, _ = KoboFormMapping.objects.update_or_create(
            form_slug=slug,
            defaults={'form_label': label, 'partner': phd,
                      'kobo_asset_uid': uid, 'is_active': True},
        )
        forms[slug] = form

    for code, slug in SL_TO_LEGACY.items():
        IndicatorTarget.objects.filter(
            partner=phd, activity_code=code,
        ).update(source_form=forms[slug])


class Migration(migrations.Migration):

    dependencies = [
        ('indicators', '0015_register_ciprb_kobo_forms'),
    ]

    operations = [
        migrations.RunPython(_forward, _reverse),
    ]
