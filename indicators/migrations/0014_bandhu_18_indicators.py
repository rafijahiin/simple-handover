"""
Final Bandhu indicator set — 18 indicators (framework review outcome).

Two changes from 0013:
  1. Retire 1.4b "KP reached via outreach" (4,000) — it duplicated 1.1
     "KP receiving services" (4,000). The framework lists the reach figure
     a second time under the outreach activity; only outreach SESSIONS
     (1.4a) remains.
  2. Merge the two billboard lines into one. The framework lists public
     messaging displays as a single indicator (40 printed + 16 e-billboards
     = 56 displays), so 4.2 (printed) and 4.3 (e-billboard) collapse into a
     single 4.2 row.

Result: 18 indicators — Obj 1 (10), Obj 2 (6), Obj 4 (2).

Clean-rebuild pattern (delete all Bandhu rows, recreate) so production lands
deterministically on the 18-row set regardless of prior state.
"""
from django.db import migrations

_MONTHS = ['2026-06', '2026-07', '2026-08', '2026-09']


def _monthly(j, jl, a, s):
    return [{'month': m, 'target': v} for m, v in zip(_MONTHS, (j, jl, a, s))]


# (objective, code, activity_label, indicator_label, target, unit, (Jun,Jul,Aug,Sep))
BANDHU_INDICATORS = [
    # ── Objective 1 — Service Delivery (10) ─────────────────────────────
    (1, '1.1',  'Integrated SRHR/HIV services via wellness centres & GOB facilities',
        'KP individuals receiving HIV/STI screening, counselling and FP',
        4000, 'individuals', (800, 1200, 1200, 800)),
    (1, '1.2',  'Screen GBV survivors; first-line support and referral',
        'GBV survivors screened, supported and referred',
        120, 'survivors', (25, 35, 35, 25)),
    (1, '1.3',  'Individual and group MHPSS counselling',
        'Individuals receiving MHPSS counselling',
        48, 'persons', (8, 15, 15, 10)),
    (1, '1.4a', 'Outreach sessions on SRHR, HIV prevention and GBV awareness',
        'Outreach and health-education sessions conducted',
        480, 'sessions', (80, 140, 140, 120)),
    (1, '1.5a', 'Provide STI and HTC services to the target group',
        'KP receiving STI services',
        2000, 'services', (400, 600, 600, 400)),
    (1, '1.5b', 'Provide STI and HTC services to the target group',
        'KP receiving HIV testing services',
        2000, 'tests', (400, 600, 600, 400)),
    (1, '1.6',  'Operationalise the Key Population (KP) Clinic in Dhaka',
        'KP clinics supported with logistics, supplies and maintenance',
        1, 'clinics', (1, 0, 0, 0)),
    (1, '1.7',  'Referral / transport support for ART enrolment',
        'KP clients referred and linked to ART, diagnostics and treatment',
        25, 'individuals', (3, 8, 8, 6)),
    (1, '1.8',  'Establish community-friendly drop-in centres (8 districts)',
        'Community-friendly service centres (Drop-in Centres) established/strengthened',
        8, 'centres', (8, 0, 0, 0)),
    (1, '1.9',  'Community-based mobile health camps for key populations',
        'Mobile outreach health camps conducted',
        40, 'camps', (5, 15, 15, 5)),

    # ── Objective 2 — Capacity Building (6) ─────────────────────────────
    (2, '2.1',  'Orientation for local health managers on inclusive SRHR / GBV',
        'Government health sector managers and supervisors oriented',
        192, 'participants', (48, 144, 0, 0)),
    (2, '2.2',  'Training for midwives, FWVs, FWAs, SACMOs and nurses',
        'Midwives and frontline service providers trained',
        192, 'participants', (48, 144, 0, 0)),
    (2, '2.3',  'District-level GOB–NGO coordination meetings',
        'Coordination meetings between GOB staff, midwives and NGOs',
        16, 'meetings', (4, 12, 0, 0)),
    (2, '2.4',  'Quarterly district coordination meetings with CBOs & networks',
        'Coordination meetings among CBOs and community networks',
        16, 'meetings', (4, 12, 0, 0)),
    (2, '2.5',  'Training for community leaders and peer educators',
        'Community leaders and peer educators trained on HIV prevention & ART',
        160, 'participants', (0, 160, 0, 0)),
    (2, '2.6',  'Observance events (World AIDS Day, anti-GBV day, etc.)',
        'National and international observance events supported',
        2, 'events', (0, 1, 0, 1)),

    # ── Objective 4 — Community Awareness (2) ───────────────────────────
    # (Objective 3 deliberately absent — Bandhu skips it. Do not renumber.)
    (4, '4.1',  'Develop and disseminate inclusive IEC/SBCC materials',
        'Inclusive IEC/SBCC materials and multimedia products disseminated',
        16800, 'materials', (4200, 4200, 4200, 4200)),
    (4, '4.2',  'Install public messaging displays (printed + e-billboards)',
        'Public messaging displays installed (40 printed + 16 e-billboards)',
        56, 'displays', (0, 0, 56, 0)),
]


def _forward(apps, schema_editor):
    IndicatorTarget = apps.get_model('indicators', 'IndicatorTarget')
    Partner         = apps.get_model('partners', 'Partner')

    bandhu = Partner.objects.filter(code='Bandhu').first()
    if bandhu is None:
        return

    IndicatorTarget.objects.filter(partner=bandhu).delete()

    for obj_num, code, activity, label, target, unit, months in BANDHU_INDICATORS:
        IndicatorTarget.objects.create(
            partner=bandhu,
            objective_number=obj_num,
            activity_code=code,
            activity_label=activity,
            indicator_label=label,
            target_value=target,
            unit=unit,
            monthly_targets=_monthly(*months),
            is_active=True,
        )


def _reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('indicators', '0013_bandhu_targets_from_mis_doc'),
    ]

    operations = [
        migrations.RunPython(_forward, _reverse),
    ]
