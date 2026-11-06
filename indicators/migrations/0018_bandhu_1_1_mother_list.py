"""
Bandhu 1.1 "KP reached" now measures the Mother List registry.

Rafi's M&E decision (2026-07-01): the 4,000 KP-reached target is measured by
the Mother List (F-1.1 registrations) — the register of KP individuals the
programme has enrolled — not the F-05/F-06 service sub-counts (which are already
tracked as 1.5a STI + 1.5b HIV testing). This updates the stored labels so the
detailed M&E indicator list matches the new computation (indicators/bandhu.py:
compute_I_BND_1_1). Target (4,000) and monthly split are unchanged.
"""
from django.db import migrations


def _forward(apps, schema_editor):
    IndicatorTarget = apps.get_model('indicators', 'IndicatorTarget')
    Partner         = apps.get_model('partners', 'Partner')

    bandhu = Partner.objects.filter(code='Bandhu').first()
    if bandhu is None:
        return

    IndicatorTarget.objects.filter(partner=bandhu, activity_code='1.1').update(
        activity_label='Enrol key-population individuals into the Mother List registry',
        indicator_label='KP individuals reached (Mother List registry)',
    )


def _reverse(apps, schema_editor):
    IndicatorTarget = apps.get_model('indicators', 'IndicatorTarget')
    Partner         = apps.get_model('partners', 'Partner')
    bandhu = Partner.objects.filter(code='Bandhu').first()
    if bandhu is None:
        return
    IndicatorTarget.objects.filter(partner=bandhu, activity_code='1.1').update(
        activity_label='Integrated SRHR/HIV services via wellness centres & GOB facilities',
        indicator_label='KP individuals receiving HIV/STI screening, counselling and FP',
    )


class Migration(migrations.Migration):

    dependencies = [
        ('indicators', '0017_register_baseline_kobo_forms'),
    ]

    operations = [
        migrations.RunPython(_forward, _reverse),
    ]
