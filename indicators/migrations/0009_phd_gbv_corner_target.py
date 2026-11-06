"""
Add the PHD SL#16 indicator — GBV corners established and operational at
government health facilities (target 44).

This is one of PHD's five confirmed headline indicators but was absent from
the original SIDA target fixture (0004). The compute function + GBV-corner
Kobo form land in a follow-up; until then the row is "unlinked" and shows
0 / 44 (the dashboard renders it as a "form pending" ring). Adding the target
row now means the headline card and the 16-indicator table both display it
against a real target immediately, and it lights up automatically once the
form is wired.

Placed under objective_number 2 (Capacity Building / system strengthening) —
the least-wrong of the existing objective groups for facility-level GBV
service establishment. Seeded idempotently via update_or_create.
"""
from django.db import migrations


PHD_GBV_CORNER = {
    'partner_code':    'PHD',
    'objective_number': 2,
    'activity_code':   '2.5',
    'activity_label':  'Establish GBV corners at government health facilities',
    'indicator_label': 'GBV corners established and operational at DH / UHC',
    'target_value':    44,
    'unit':            'corners',
}


def _forward(apps, schema_editor):
    IndicatorTarget = apps.get_model('indicators', 'IndicatorTarget')
    Partner = apps.get_model('partners', 'Partner')

    partner = Partner.objects.filter(code=PHD_GBV_CORNER['partner_code']).first()
    if partner is None:
        # Partner not seeded yet — nothing to do; a later run will pick it up.
        return

    IndicatorTarget.objects.update_or_create(
        partner=partner,
        activity_code=PHD_GBV_CORNER['activity_code'],
        indicator_label=PHD_GBV_CORNER['indicator_label'],
        defaults={
            'objective_number': PHD_GBV_CORNER['objective_number'],
            'activity_label':   PHD_GBV_CORNER['activity_label'],
            'target_value':     PHD_GBV_CORNER['target_value'],
            'unit':             PHD_GBV_CORNER['unit'],
            'is_active':        True,
        },
    )


def _reverse(apps, schema_editor):
    IndicatorTarget = apps.get_model('indicators', 'IndicatorTarget')
    Partner = apps.get_model('partners', 'Partner')
    partner = Partner.objects.filter(code=PHD_GBV_CORNER['partner_code']).first()
    if partner is None:
        return
    IndicatorTarget.objects.filter(
        partner=partner,
        activity_code=PHD_GBV_CORNER['activity_code'],
        indicator_label=PHD_GBV_CORNER['indicator_label'],
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('indicators', '0008_indicatortarget_monthly_targets'),
    ]

    operations = [
        migrations.RunPython(_forward, _reverse),
    ]
