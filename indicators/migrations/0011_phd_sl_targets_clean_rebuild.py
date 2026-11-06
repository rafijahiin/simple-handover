"""
Clean rebuild of PHD indicator targets from PHD_SIDA_Activities_Indicators_Output_Outcome.docx.

Deletes ALL old PHD IndicatorTarget rows (the 3.1/objective-numbered scheme is dead)
and inserts SL1 through SL16 exactly as the SIDA framework document specifies.

SL5 and SL15 each split into sub-rows (one per commodity / material type).
"""
from django.db import migrations


PHD_SL_INDICATORS = [
    # (sl_code, activity, indicator_label, target, unit)
    ('SL1',  'Provide counselling, screening and management for HIV, syphilis, Hepatitis B & C and FP counselling',
     'Number of FSWs receiving HIV/STI screening and FP counselling',
     3500, 'FSWs'),

    ('SL2',  'Screen and support GBV survivors and activate referral mechanisms',
     'Number of GBV survivors identified and referred for services',
     100, 'survivors'),

    ('SL3',  'Provide group mental health counselling',
     'Number of FSWs receiving mental health counselling sessions',
     100, 'FSWs'),

    ('SL4',  'Conduct targeted outreach and health education',
     'Number of outreach sessions conducted and FSWs / clients reached',
     897, 'sessions'),

    # SL5 — commodities (5 sub-rows)
    ('SL5a', 'Ensure availability of essential SRHR and GBV supplies',
     'Condoms distributed', 300000, 'pieces'),
    ('SL5b', 'Ensure availability of essential SRHR and GBV supplies',
     'Syphilis Screening Kits', 140, 'boxes'),
    ('SL5c', 'Ensure availability of essential SRHR and GBV supplies',
     'Hepatitis B Screening Kits', 176, 'boxes'),
    ('SL5d', 'Ensure availability of essential SRHR and GBV supplies',
     'Hepatitis C Screening Kits', 176, 'boxes'),
    ('SL5e', 'Ensure availability of essential SRHR and GBV supplies',
     'HIV Screening Kits', 40, 'boxes'),

    ('SL6',  'Referral support for HIV, Syphilis, Hepatitis B & C, diagnostics and treatment',
     'Number of HIV/STI positive cases successfully referred and enrolled in treatment',
     135, 'cases'),

    ('SL7',  'Referral support MHPSS',
     'Number of GBV survivors referred for MHPSS',
     50, 'survivors'),

    ('SL8',  'Establish and strengthen community-friendly centers',
     'Number of functional brothel-based SRHR service centers',
     9, 'centers'),

    ('SL9',  'Mobile outreach health services',
     'Number of mobile health camps conducted',
     90, 'camps'),

    ('SL10', 'Advocacy orientation for DGFP/DGHS/DGNM focal points on inclusive SRHR and survivor-centered GBV prevention',
     'Focal points oriented on inclusive SRHR and GBV response',
     30, 'participants'),

    ('SL11', 'Orientation for health managers and supervisors on inclusive SRHR and survivor-centered GBV prevention',
     'Managers oriented on inclusive SRHR and GBV response (District/Upazila GOB staff)',
     140, 'participants'),

    ('SL12', 'Training for midwives and service providers',
     'Providers trained on inclusive SRHR and GBV response (MAs / Midwives / Counsellors)',
     10, 'participants'),

    ('SL13', 'Training for peer educators and community leaders',
     'Peer educators and community leaders trained',
     20, 'participants'),

    ('SL14', 'Quarterly coordination meetings',
     'Number of coordination meetings conducted',
     18, 'meetings'),

    # SL15 — awareness materials (3 sub-rows)
    ('SL15a', 'Install billboards and communication materials',
     'Message boards installed', 99, 'pieces'),
    ('SL15b', 'Install billboards and communication materials',
     'Signboards installed', 9, 'pieces'),
    ('SL15c', 'Install billboards and communication materials',
     'Billboards installed', 11, 'pieces'),

    ('SL16', 'Establish GBV corners at health facilities',
     'GBV corners established and fully equipped at DH and UHCs',
     44, 'corners'),
]


def _forward(apps, schema_editor):
    IndicatorTarget = apps.get_model('indicators', 'IndicatorTarget')
    Partner         = apps.get_model('partners', 'Partner')

    phd = Partner.objects.filter(code='PHD').first()
    if phd is None:
        return

    # Delete EVERY existing PHD indicator row — clean slate
    IndicatorTarget.objects.filter(partner=phd).delete()

    # Insert SL1..SL16 exactly as the SIDA doc specifies
    # objective_number = 0 for all (the old 1/2/3 objective grouping is gone;
    # SL ordering is the only grouping that matters now)
    for sl_code, activity, label, target, unit in PHD_SL_INDICATORS:
        IndicatorTarget.objects.create(
            partner=phd,
            objective_number=0,
            activity_code=sl_code,
            activity_label=activity,
            indicator_label=label,
            target_value=target,
            unit=unit,
            is_active=True,
        )


def _reverse(apps, schema_editor):
    pass  # forward is destructive; no clean reverse


class Migration(migrations.Migration):

    dependencies = [
        ('indicators', '0010_phd_targets_from_sida_doc'),
    ]

    operations = [
        migrations.RunPython(_forward, _reverse),
    ]
