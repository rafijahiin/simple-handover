"""
Static demo data for the three report generators.

Derived from the UNFPA Bangladesh Country Programme Evaluation 2022–2026
(CPE Draft 2, November 2025) at CIPRB implementation-partner scale.

Purpose
-------
Allow stakeholders to preview the infographic, newsletter, and presentation
reports before live field submissions have accumulated in the database.

The dict returned by get_demo_data() is structurally identical to the output
of collect_programme_data(), so it flows through the same generator pipeline
as real approved submissions.

Remove or archive this module once ≥ 12 months of live data are available.
"""
from __future__ import annotations

from datetime import date

# ── Period ─────────────────────────────────────────────────────────────────────
# Calendar year 2024 — the reference period cited in the CPE report.

DEMO_PERIOD_START = date(2024, 1, 1)
DEMO_PERIOD_END   = date(2024, 12, 31)
DEMO_PERIOD_LABEL = 'January – December 2024'
DEMO_ORGANISATION = 'PHD + Bandhu (CIPRB/UNFPA RCH)'

# ── Activity counts ────────────────────────────────────────────────────────────
# Calibrated from mock monthly figures × 12.
#   PHD-only  : antenatal_cards, mobile_camps
#   Bandhu-only: hygiene_kits
#   Shared     : all other keys

DEMO_COUNTS: dict[str, int] = {
    # Clinical
    'clinic_visits':            2_940,   # PHD 1,068 + Bandhu 1,872
    'hiv_sti_tests':            2_724,   # PHD   288 + Bandhu 2,436
    'adr_records':                264,   # PHD    96 + Bandhu   168
    'autoclave_logs':             132,   # PHD    48 + Bandhu    84
    'antenatal_cards':            804,   # PHD only
    'htc_counselling':          1_560,   # PHD   216 + Bandhu 1,344
    'individual_counselling':   2_652,   # PHD   384 + Bandhu 2,268
    'mh_screenings':              720,   # PHD   180 + Bandhu   540
    # Community
    'gbv_cases':                  564,   # PHD   108 + Bandhu   456
    'outreach_sessions':        2_148,   # PHD   540 + Bandhu 1,608
    'group_education':          1_272,   # PHD   336 + Bandhu   936
    'referrals':                  924,   # PHD   252 + Bandhu   672
    'hygiene_kits':             1_344,   # Bandhu only
    # Operations
    'training_events':             96,   # PHD    36 + Bandhu    60
    'coord_meetings':              96,   # PHD    48 + Bandhu    48
    'mobile_camps':                24,   # PHD only
}

# 2,940+2,724+264+132+804+1,560+2,652+720+564+2,148+1,272+924+1,344+96+96+24 = 18,264
DEMO_TOTAL = sum(DEMO_COUNTS.values())

# CPE Table 8 (2024): 522 fistula cases identified nationally; CIPRB share ~43.
DEMO_FISTULA_CASES = 43
# MPDSR cases investigated by PHD + Bandhu across priority districts.
DEMO_MPDSR_CASES   = 20

# ── Narrative ─────────────────────────────────────────────────────────────────
# Written from CPE findings; passed verbatim to all three generators.
# Generators parse headings (\n\n separated) to build formatted sections.

DEMO_NARRATIVE = """\
Annual Programme Summary — PHD & Bandhu Social Welfare Society (2024)

Programme Overview
PHD and Bandhu Social Welfare Society collectively delivered 18,264 approved \
programme activities during the 2024 reporting year across Cox's Bazar, Dhaka, \
Chittagong, Sylhet, Narayanganj, and Comilla — the six priority districts covered \
under CIPRB's UNFPA-funded Reproductive and Child Health (RCH) programme.

Clinical Services
Clinic visits (2,940) and HIV/STI tests (2,724) led the activity count, reflecting \
the scale of both partners' service delivery. PHD recorded 804 antenatal cards, \
contributing to national progress toward Bangladesh's 69.8% skilled birth attendance \
target (DHS 2022). HTC counselling (1,560 sessions) and mental health screenings (720) \
addressed psychosocial needs — particularly among Rohingya and host communities in \
Cox's Bazar.

Community Outreach
Community-level reach remained strong: 2,148 outreach sessions, 2,652 individual \
counselling engagements, and 1,344 hygiene kit distributions reached key populations — \
including female sex workers, transgender persons, and men who have sex with men — \
served by Bandhu across urban sites. 564 GBV cases were documented and referred \
through the protection pathway.

Fistula and MPDSR
43 obstetric fistula cases were identified and referred for corrective surgery, \
contributing to the national total of 522 documented by UNFPA partners in 2024 \
(CPE Table 8). 20 maternal and perinatal death surveillance (MPDSR) cases were \
recorded and investigated across both organisations, supporting national cause-of-death \
disaggregation across all 64 districts.

Performance Context
Against Bangladesh's national maternal mortality ratio of 136 per 100,000 live births \
(CPE Annex 8, 2024) and with 73% of Upazila Health Complexes now operational with \
midwifery services, CIPRB's field activities continue to close service gaps through \
PHD's maternal health mandate and Bandhu's key-population HIV/STI response. \
Family planning met need stands at 73.9% nationally (DHS 2022); CIPRB's FP \
referral and counselling activities directly support progress toward this target.

Note: This report uses illustrative data from the UNFPA Bangladesh CPE 2022–2026 \
(Draft 2, November 2025). It demonstrates the IDMS reporting pipeline. Live field \
submissions will replace this content once the system is in active use.
"""

# ── Label map (mirrors generators/data.py — do not rename keys) ───────────────

_LABEL_MAP: dict[str, str] = {
    'clinic_visits':          'Clinic Visits',
    'hiv_sti_tests':          'HIV/STI Tests',
    'adr_records':            'ADR Records',
    'autoclave_logs':         'Autoclave Logs',
    'antenatal_cards':        'Antenatal Cards',
    'htc_counselling':        'HTC Counselling',
    'individual_counselling': 'Individual Counselling',
    'mh_screenings':          'MH Screenings',
    'gbv_cases':              'GBV Cases',
    'outreach_sessions':      'Outreach Sessions',
    'group_education':        'Group Education',
    'referrals':              'Referrals',
    'hygiene_kits':           'Hygiene Kits',
    'training_events':        'Training Events',
    'coord_meetings':         'Coord. Meetings',
    'mobile_camps':           'Mobile Camps',
}


def get_demo_data() -> dict:
    """
    Return a data dict structurally identical to collect_programme_data() output,
    populated with CPE-derived demo numbers.

    Consumed by: build_infographic(), build_newsletter(), build_presentation()
    """
    top_kpis = [
        {'label': 'Total Activities',   'value': DEMO_TOTAL},
        {'label': 'Clinic Visits',      'value': DEMO_COUNTS['clinic_visits']},
        {'label': 'Outreach Sessions',  'value': DEMO_COUNTS['outreach_sessions']},
        {'label': 'GBV Cases',          'value': DEMO_COUNTS['gbv_cases']},
    ]

    # Top-8 form types ascending (highest last — matches horizontal bar orientation)
    all_items = [(_LABEL_MAP[k], v) for k, v in DEMO_COUNTS.items()]
    chart_data = sorted(all_items, key=lambda x: x[1])[-8:]

    return {
        'period_start':      DEMO_PERIOD_START,
        'period_end':        DEMO_PERIOD_END,
        'period_label':      DEMO_PERIOD_LABEL,
        'organisation':      DEMO_ORGANISATION,
        'total_submissions': DEMO_TOTAL,
        'counts':            DEMO_COUNTS,
        'fistula_cases':     DEMO_FISTULA_CASES,
        'mpdsr_cases':       DEMO_MPDSR_CASES,
        'top_kpis':          top_kpis,
        'chart_data':        chart_data,
        # Sample values for the geography / trend / workforce fields. These
        # mirror what collect_programme_data() now computes live, so the demo
        # exercises the identical generator code path.
        'pending':           37,
        'active_workers':    38,
        'mom_pct':           8.4,
        'monthly_trend':     [1_180, 1_320, 1_410, 1_390, 1_520, 1_488,
                              1_610, 1_575, 1_640, 1_590, 1_702, DEMO_TOTAL // 12],
        'top_districts':     [
            ("Cox's Bazar", 4_860),
            ('Dhaka',       3_120),
            ('Chittagong',  2_740),
            ('Sylhet',      2_510),
            ('Narayanganj', 2_460),
            ('Comilla',     2_574),
        ],
    }
