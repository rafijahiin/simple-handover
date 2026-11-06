"""
Correct PHD indicator targets to match PHD_SIDA_Activities_Indicators_Output_Outcome.docx
exactly. Previous fixture had several wrong values.

Changes:
  1.1  : 3484 → 3500  (doc: "3,500 FSWs")
  1.3  : 1000 → 100   (doc: "100 FSWs" — was 10x too high)
  1.6  : 190  → 135   (doc: "135 cases")
  1.8  : 40   → 90    (doc: "90 camps")
  2.1a : 33   → 30    (doc: "1 event [30 participants]")
  2.3  : 33   → 20    (doc: "1 event [20 Peer Educators]")
  3.1a : 66   → 99    (doc: "Message board: 99 pcs")
  3.1b : 200  → 9     (doc: "Signboard: 9 Pcs" — poster row removed, SIDA doc has no poster target)
  3.1c : 11   → 11    (billboards unchanged)

Add missing SL7 row: GBV survivors referred for MHPSS (target 50).
Rename 3.1b indicator_label from "Posters installed" to "Signboards installed"
  (3.1b was posters; source doc has no poster target — now maps to Signboards).
"""
from django.db import migrations


UPDATES = [
    # (partner_code, activity_code, old_label_fragment, new_target, new_label)
    ('PHD', '1.1', 'FSWs receiving HIV/STI',           3500,  None),
    ('PHD', '1.3', 'mental health',                     100,   None),
    ('PHD', '1.6', 'referred and enrolled',             135,   None),
    ('PHD', '1.8', 'Mobile health camps',                90,   None),
    ('PHD', '2.1a', 'DGFP managers',                    30,   None),
    ('PHD', '2.3',  'Peer educators',                   20,   None),
    ('PHD', '3.1a', 'Message boards',                   99,   None),
    # 3.1b was "Posters" (200) — doc has no poster target; repurpose to Signboards (9)
    ('PHD', '3.1b', 'Posters',                           9,   'Signboards installed'),
]

NEW_ROW = {
    'partner_code':     'PHD',
    'objective_number': 1,
    'activity_code':    '1.7.mhpss',
    'activity_label':   'Referral support MHPSS',
    'indicator_label':  'GBV survivors referred for MHPSS services',
    'target_value':     50,
    'unit':             'survivors',
}


def _forward(apps, schema_editor):
    IndicatorTarget = apps.get_model('indicators', 'IndicatorTarget')
    Partner         = apps.get_model('partners', 'Partner')

    phd = Partner.objects.filter(code='PHD').first()
    if phd is None:
        return

    for partner_code, act_code, label_frag, new_target, new_label in UPDATES:
        qs = IndicatorTarget.objects.filter(
            partner=phd,
            activity_code=act_code,
            indicator_label__icontains=label_frag,
        )
        upd = {'target_value': new_target}
        if new_label:
            upd['indicator_label'] = new_label
        qs.update(**upd)

    # Add SL7 row if not present
    IndicatorTarget.objects.get_or_create(
        partner=phd,
        activity_code=NEW_ROW['activity_code'],
        indicator_label=NEW_ROW['indicator_label'],
        defaults={
            'objective_number': NEW_ROW['objective_number'],
            'activity_label':   NEW_ROW['activity_label'],
            'target_value':     NEW_ROW['target_value'],
            'unit':             NEW_ROW['unit'],
            'is_active':        True,
        },
    )


def _reverse(apps, schema_editor):
    pass  # non-destructive reverse — originals are re-applied by 0004


class Migration(migrations.Migration):

    dependencies = [
        ('indicators', '0009_phd_gbv_corner_target'),
    ]

    operations = [
        migrations.RunPython(_forward, _reverse),
    ]
