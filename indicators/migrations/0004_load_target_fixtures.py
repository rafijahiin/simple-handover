"""
Data migration — load the 44 confirmed IndicatorTarget rows from the SIDA
frameworks plus the CIPRB placeholders.

Counts:
  PHD    — 22 rows (1 overall + 21 SIDA activity targets, including 5 1.5
           commodity rows and 4 3.1 material rows and 2 2.1 staff rows)
  Bandhu — 19 rows (Obj 1/2/4, with 1.4 and 1.5 splitting into 2 rows each)
  CIPRB  — 3 rows (Fistula Corner, Fistula Campaign, Baseline — all NULL
           target_value, display as "Not Set" in UI until supervisor sets
           values post-workshop)

All targets seeded idempotently via update_or_create on
(partner, activity_code, indicator_label). Re-running this migration
(or re-applying after schema reset) will not duplicate rows.
"""
from django.db import migrations


# Order: PHD overall first, then PHD Obj 1, 2, 3 / Bandhu Obj 1, 2, 4 /
# CIPRB placeholders. The UI's group renderer is order-independent
# (sorts by partner + objective_number + activity_code) — the order
# here is just for review readability.
SEED_DATA = [
    # ── PHD overall (obj=0) ──────────────────────────────────────────────
    ('PHD', 0, 'OVERALL', 'Brothels covered (overall indicator)',
        'Number of brothels covered by PHD services',
        11, 'brothels'),

    # ── PHD Objective 1 — Service Delivery ───────────────────────────────
    ('PHD', 1, '1.1',  'HIV/STI screening + FP counselling for FSWs',
        'FSWs receiving HIV/STI screening and FP counselling',
        3484, 'individuals'),
    ('PHD', 1, '1.2',  'Screen and support GBV survivors; activate referral mechanisms',
        'GBV survivors identified and referred for services',
        100, 'survivors'),
    ('PHD', 1, '1.3',  'Individual and group mental health counselling',
        'FSWs receiving mental health counselling sessions',
        1000, 'individuals'),
    ('PHD', 1, '1.4',  'Targeted outreach and health education',
        'Outreach sessions conducted (FSWs and clients reached)',
        897, 'sessions'),
    ('PHD', 1, '1.5a', 'Ensure availability of essential SRHR / GBV supplies',
        'Condoms — uninterrupted supply at service centers',
        679380, 'pcs'),
    ('PHD', 1, '1.5b', 'Ensure availability of essential SRHR / GBV supplies',
        'Syphilis screening kits — uninterrupted supply',
        140, 'boxes'),
    ('PHD', 1, '1.5c', 'Ensure availability of essential SRHR / GBV supplies',
        'Hepatitis B screening kits — uninterrupted supply',
        176, 'boxes'),
    ('PHD', 1, '1.5d', 'Ensure availability of essential SRHR / GBV supplies',
        'Hepatitis C screening kits — uninterrupted supply',
        176, 'boxes'),
    ('PHD', 1, '1.5e', 'Ensure availability of essential SRHR / GBV supplies',
        'HIV screening kits — uninterrupted supply',
        70, 'boxes'),
    ('PHD', 1, '1.6',  'Referral support for ART, diagnostics, and treatment',
        'HIV/STI positive cases referred and enrolled in treatment',
        190, 'cases'),
    ('PHD', 1, '1.7',  'Establish and strengthen community-friendly centers',
        'Functional brothel-based SRHR service centers',
        9, 'centers'),
    ('PHD', 1, '1.8',  'Mobile outreach health services',
        'Mobile health camps conducted',
        40, 'camps'),

    # ── PHD Objective 2 — Capacity Building ──────────────────────────────
    ('PHD', 2, '2.1a', 'Advocacy orientation / workshop for health managers and supervisors',
        'DGFP managers oriented on inclusive SRHR and GBV response',
        33, 'managers'),
    ('PHD', 2, '2.1b', 'Advocacy orientation / workshop for health managers and supervisors',
        'District / Upazila level GOB staff and service providers oriented',
        140, 'staff'),
    ('PHD', 2, '2.2',  'Training for midwives and service providers',
        'Medical Assistants / Midwives / counsellors trained',
        10, 'participants'),
    ('PHD', 2, '2.3',  'Training for peer educators and community leaders',
        'Peer educators and community leaders trained',
        33, 'participants'),
    ('PHD', 2, '2.4',  'Quarterly coordination meetings',
        'Coordination meetings conducted',
        18, 'meetings'),

    # ── PHD Objective 3 — Community Awareness ────────────────────────────
    ('PHD', 3, '3.1a', 'Install billboards and communication materials',
        'Message boards installed',
        66, 'pcs'),
    ('PHD', 3, '3.1b', 'Install billboards and communication materials',
        'Posters installed',
        200, 'pcs'),
    ('PHD', 3, '3.1c', 'Install billboards and communication materials',
        'Signboards installed',
        11, 'pcs'),
    ('PHD', 3, '3.1d', 'Install billboards and communication materials',
        'Billboards installed',
        11, 'pcs'),

    # ── Bandhu Objective 1 — Service Delivery ────────────────────────────
    ('Bandhu', 1, '1.1',  'HIV/STI screening + FP counselling for KP',
        'KP individuals receiving HIV/STI screening, counselling, and FP',
        4000, 'individuals'),
    ('Bandhu', 1, '1.2',  'Screen GBV survivors; provide first-line support and referrals',
        'GBV survivors screened, supported, and referred',
        200, 'survivors'),
    ('Bandhu', 1, '1.3',  'Individual and group MHPSS counselling sessions',
        'MHPSS counselling sessions delivered',
        75, 'sessions'),
    ('Bandhu', 1, '1.4a', 'Targeted outreach and health education sessions',
        'Outreach and health education sessions conducted',
        400, 'sessions'),
    ('Bandhu', 1, '1.4b', 'Targeted outreach and health education sessions',
        'KP members reached via outreach and education sessions',
        5000, 'individuals'),
    ('Bandhu', 1, '1.5a', 'Ensure SRHR / GBV supplies at service centers',
        'Service centers maintaining uninterrupted essential commodities',
        5, 'centers'),
    ('Bandhu', 1, '1.5b', 'Ensure SRHR / GBV supplies at service centers',
        'KP receiving STI and HIV testing services',
        2000, 'tests'),
    ('Bandhu', 1, '1.6',  'KP Clinic (Dhaka) — logistics/maintenance supported',
        'KP clinics supported with logistics, supplies, and maintenance',
        1, 'clinics'),
    ('Bandhu', 1, '1.7',  'Referral support for ART enrolment, diagnostics, and treatment',
        'KP clients referred and linked to ART / diagnostics / treatment',
        175, 'individuals'),
    ('Bandhu', 1, '1.8',  'Establish and strengthen community-friendly drop-in centers',
        'Drop-in centers established or strengthened',
        5, 'centers'),
    ('Bandhu', 1, '1.9',  'Mobile outreach health services for key populations',
        'KP individuals receiving health services through mobile camps',
        200, 'individuals'),

    # ── Bandhu Objective 2 — Capacity Building ───────────────────────────
    ('Bandhu', 2, '2.1',  'Structured orientation for health sector managers and supervisors',
        'Government health sector managers and supervisors oriented',
        150, 'participants'),
    ('Bandhu', 2, '2.2',  'Training for midwives and service providers',
        'Midwives and frontline providers trained',
        150, 'participants'),
    ('Bandhu', 2, '2.3',  'Quarterly GOB-NGO coordination meetings',
        'Coordination meetings between GOB staff, midwives, and NGOs',
        12, 'meetings'),
    ('Bandhu', 2, '2.4',  'Quarterly CBO and network coordination meetings',
        'Coordination meetings among CBOs and community networks',
        10, 'meetings'),
    ('Bandhu', 2, '2.5',  'Training for community leaders and peer educators (LGBTQ)',
        'Community leaders and peer educators trained',
        125, 'participants'),
    ('Bandhu', 2, '2.6',  'Support day observances (e.g. World AIDS Day, Human Rights Day)',
        'National and international observance events supported',
        2, 'events'),

    # ── Bandhu Objective 4 — Community Awareness ─────────────────────────
    # (Obj 3 deliberately absent — Bandhu skips it. Do not auto-renumber.)
    ('Bandhu', 4, '4.1',  'Develop and disseminate inclusive IEC / SBCC materials',
        'IEC / SBCC materials and multimedia products developed and disseminated',
        50000, 'materials'),
    ('Bandhu', 4, '4.3',  'E-billboards / public messaging displays at district hospitals',
        'E-billboards installed across district / upazila hospitals',
        4, 'installations'),

    # ── CIPRB placeholders — target NULL until supervisor confirms ───────
    ('CIPRB', 1, 'F.C',    'Fistula Corner — diagnosis records at District Hospital',
        'Fistula cases diagnosed at District Hospital Fistula Corner',
        None, 'cases'),
    ('CIPRB', 1, 'F.Camp', 'Fistula Campaign — house-visit campaign records',
        'Suspected fistula cases identified via house visits',
        None, 'visits'),
    ('CIPRB', 1, 'B',      'Baseline assessment — CIPRB-managed survey data',
        'Baseline assessment records entered',
        None, 'surveys'),
]


def _forward(apps, schema_editor):
    IndicatorTarget = apps.get_model('indicators', 'IndicatorTarget')
    Partner = apps.get_model('partners', 'Partner')

    partners_by_code = {p.code: p for p in Partner.objects.all()}

    for row in SEED_DATA:
        partner_code, obj_num, act_code, act_label, ind_label, target, unit = row
        partner = partners_by_code.get(partner_code)
        if partner is None:
            raise RuntimeError(
                f'Partner {partner_code!r} not found — partners/0001_initial '
                f'must run before this data migration.'
            )
        IndicatorTarget.objects.update_or_create(
            partner=partner,
            activity_code=act_code,
            indicator_label=ind_label,
            defaults={
                'objective_number': obj_num,
                'activity_label':   act_label,
                'target_value':     target,
                'unit':             unit,
                'is_active':        True,
            },
        )


def _reverse(apps, schema_editor):
    IndicatorTarget = apps.get_model('indicators', 'IndicatorTarget')
    Partner = apps.get_model('partners', 'Partner')

    partners_by_code = {p.code: p for p in Partner.objects.all()}
    for row in SEED_DATA:
        partner_code, _, act_code, _, ind_label, _, _ = row
        partner = partners_by_code.get(partner_code)
        if partner is None:
            continue
        IndicatorTarget.objects.filter(
            partner=partner,
            activity_code=act_code,
            indicator_label=ind_label,
        ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('indicators', '0003_restructure_target_and_add_koboformmapping'),
    ]

    operations = [
        migrations.RunPython(_forward, _reverse),
    ]
