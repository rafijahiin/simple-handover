"""
Programme data aggregation for report generation.
Queries approved submissions across all programs models for a given date range.
All generators consume the dict returned by collect_programme_data().
"""
from __future__ import annotations

import logging
from datetime import date

logger = logging.getLogger(__name__)

# Human-readable labels for each form type key
LABEL_MAP: dict[str, str] = {
    'registrations':          'Registrations',
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


def _count_model(model, period_start: date, period_end: date, organisation: str = '') -> int:
    """Safely count approved SubmissionBase records for a period."""
    try:
        qs = model.objects.filter(
            approval_status='APPROVED',
            created_at__date__gte=period_start,
            created_at__date__lte=period_end,
        )
        if organisation:
            qs = qs.filter(organisation=organisation)
        return qs.count()
    except Exception as exc:
        logger.debug('_count_model failed for %s: %s', model.__name__, exc)
        return 0


def collect_programme_data(
    period_start: date,
    period_end: date,
    organisation: str = '',
) -> dict:
    """
    Aggregate all programme metrics for a reporting period.

    Returns a structured dict that is consumed by all three generators
    (infographic PDF, newsletter PDF, PPTX).
    """
    from programs.models import (
        Client,
        ClinicVisit, HIVSTITestResult, ADRRecord, AutoclaveLog, AntenatalCard,
        HTCCounselling, IndividualCounselling, MHScreening,
        GBVCase,
        OutreachSession, GroupEducationSession,
        Referral,
        SafetyHygieneKit,
        TrainingEvent, CoordMeeting, MobileHealthCamp,
    )

    # Client (FSW / mother registration) is a submission too — omitting it made
    # the report read "7 field submissions" while the dashboard counted 23.
    # Include it everywhere the dashboard does, so report totals reconcile.
    _models = [
        Client,
        ClinicVisit, HIVSTITestResult, ADRRecord, AutoclaveLog, AntenatalCard,
        HTCCounselling, IndividualCounselling, MHScreening, GBVCase,
        OutreachSession, GroupEducationSession, Referral, SafetyHygieneKit,
        TrainingEvent, CoordMeeting, MobileHealthCamp,
    ]

    def _m(model):
        return _count_model(model, period_start, period_end, organisation)

    counts = {
        'registrations':          _m(Client),
        'clinic_visits':          _m(ClinicVisit),
        'hiv_sti_tests':          _m(HIVSTITestResult),
        'adr_records':            _m(ADRRecord),
        'autoclave_logs':         _m(AutoclaveLog),
        'antenatal_cards':        _m(AntenatalCard),
        'htc_counselling':        _m(HTCCounselling),
        'individual_counselling': _m(IndividualCounselling),
        'mh_screenings':          _m(MHScreening),
        'gbv_cases':              _m(GBVCase),
        'outreach_sessions':      _m(OutreachSession),
        'group_education':        _m(GroupEducationSession),
        'referrals':              _m(Referral),
        'hygiene_kits':           _m(SafetyHygieneKit),
        'training_events':        _m(TrainingEvent),
        'coord_meetings':         _m(CoordMeeting),
        'mobile_camps':           _m(MobileHealthCamp),
    }

    total = sum(counts.values())

    # --- Real values for the fields the generators used to fabricate ---
    # Previously the infographic/PPTX fell back to hardcoded constants
    # (8.4% MoM, "Cox's Bazar 156", 38 workers, 12 pending) whenever these
    # keys were absent — which was always, on a live report. Compute them
    # for real here so generated files reflect the actual database; demo
    # reports supply their own rich sample values via reports/demo_data.py.

    # Pending review (snapshot within the period).
    pending = 0
    for _model in _models:
        try:
            pq = _model.objects.filter(
                approval_status='PENDING',
                created_at__date__gte=period_start,
                created_at__date__lte=period_end,
            )
            if organisation:
                pq = pq.filter(organisation=organisation)
            pending += pq.count()
        except Exception:
            continue

    # Active field workers — distinct submitter identities in the period.
    worker_ids: set = set()
    for _model in _models:
        try:
            wq = _model.objects.filter(
                approval_status='APPROVED',
                created_at__date__gte=period_start,
                created_at__date__lte=period_end,
            ).exclude(submitted_by_kobo_user='')
            if organisation:
                wq = wq.filter(organisation=organisation)
            worker_ids.update(
                wq.values_list('submitted_by_kobo_user', flat=True).distinct()
            )
        except Exception:
            continue
    active_workers = len(worker_ids)

    # Month-on-month % change vs the immediately preceding equal-length window.
    from datetime import timedelta
    mom_pct = 0.0
    try:
        window = (period_end - period_start) + timedelta(days=1)
        prev_end = period_start - timedelta(days=1)
        prev_start = prev_end - window + timedelta(days=1)
        prev_total = sum(
            _count_model(m, prev_start, prev_end, organisation) for m in _models
        )
        if prev_total > 0:
            mom_pct = round((total - prev_total) / prev_total * 100, 1)
        elif total > 0:
            mom_pct = 100.0
    except Exception as exc:
        logger.debug('mom_pct computation skipped: %s', exc)

    # 12-month trajectory of total approved programme records (sparkline).
    monthly_trend: list[int] = []
    try:
        import calendar as _cal
        anchor_y, anchor_m = period_end.year, period_end.month
        for i in range(11, -1, -1):
            total_idx = (anchor_y * 12 + (anchor_m - 1)) - i
            my, mm = total_idx // 12, total_idx % 12 + 1
            ms = date(my, mm, 1)
            me = date(my, mm, _cal.monthrange(my, mm)[1])
            monthly_trend.append(
                sum(_count_model(m, ms, me, organisation) for m in _models)
            )
    except Exception as exc:
        logger.debug('monthly_trend computation skipped: %s', exc)
        monthly_trend = []

    # Top districts by submission volume — sourced from KoboSubmission, which
    # carries the district field (MPDSR / fistula / baseline geography).
    top_districts: list[tuple] = []
    districts_active = 0
    try:
        from submissions.models import KoboSubmission, SubmissionStatus
        from django.db.models import Count as _Count
        dq = KoboSubmission.objects.filter(
            status=SubmissionStatus.APPROVED,
            submitted_at__date__gte=period_start,
            submitted_at__date__lte=period_end,
        ).exclude(district='')
        if organisation:
            dq = dq.filter(partner=organisation)
        # True distinct-district coverage — NOT len(top_districts), which is
        # capped at 6 and would under-report "X/19 districts covered".
        districts_active = dq.values('district').distinct().count()
        rows = (
            dq.values('district')
              .annotate(n=_Count('id'))
              .order_by('-n')[:6]
        )
        top_districts = [(r['district'], r['n']) for r in rows]
    except Exception as exc:
        logger.debug('top_districts computation skipped: %s', exc)
        top_districts = []

    # --- Fistula legacy data ---
    # FIX: previously summed a non-existent field `cases_identified`, which
    # raised FieldError caught by the broad except → fistula_cases was always
    # 0 in every report. The model's confirmed-case field is
    # `confirmed_fistula_cases`.
    fistula_cases = 0
    try:
        from fistula.models import FistulaCampaign
        from django.db.models import Sum as _Sum
        fq = FistulaCampaign.objects.filter(
            campaign_date__gte=period_start,
            campaign_date__lte=period_end,
        )
        if organisation:
            fq = fq.filter(partner=organisation)
        fistula_cases = fq.aggregate(t=_Sum('confirmed_fistula_cases'))['t'] or 0
    except Exception as exc:
        logger.debug('fistula aggregation skipped: %s', exc)

    # --- MPDSR legacy data (from submissions app) ---
    mpdsr_cases = 0
    try:
        from submissions.models import KoboSubmission, FormType, SubmissionStatus
        mq = KoboSubmission.objects.filter(
            form_type=FormType.MPDSR,
            status=SubmissionStatus.APPROVED,
            submitted_at__date__gte=period_start,
            submitted_at__date__lte=period_end,
        )
        if organisation:
            mq = mq.filter(partner=organisation)
        mpdsr_cases = mq.count()
    except Exception as exc:
        logger.debug('mpdsr aggregation skipped: %s', exc)

    # Per-partner submission totals for the board partner-split slide — real
    # counts per org, replacing the deck's hardcoded 369/287 demo numbers.
    by_partner: dict[str, int] = {}
    for _code in ('PHD', 'Bandhu', 'CIPRB'):
        by_partner[_code] = sum(
            _count_model(m, period_start, period_end, _code) for m in _models
        )

    # --- Top-4 KPI tiles ---
    top_kpis = [
        {'label': 'Total Activities',   'value': total},
        {'label': 'Clinic Visits',      'value': counts['clinic_visits']},
        {'label': 'Outreach Sessions',  'value': counts['outreach_sessions']},
        {'label': 'GBV Cases',          'value': counts['gbv_cases']},
    ]

    # --- Chart data: top 8 form types sorted ascending (highest at top in horizontal chart) ---
    all_items = [(LABEL_MAP[k], v) for k, v in counts.items()]
    chart_data = sorted(all_items, key=lambda x: x[1])[-8:]   # ascending → highest at top
    if not chart_data:
        chart_data = [(LABEL_MAP[k], 0) for k in list(LABEL_MAP)[:4]]

    # --- Period label ---
    ps, pe = period_start, period_end
    if ps.year == pe.year and ps.month == pe.month:
        period_label = f"{ps.day}–{pe.day} {pe.strftime('%b %Y')}"
    elif ps.year == pe.year:
        period_label = f"{ps.day} {ps.strftime('%b')} – {pe.day} {pe.strftime('%b %Y')}"
    else:
        period_label = (
            f"{ps.day} {ps.strftime('%b %Y')} – {pe.day} {pe.strftime('%b %Y')}"
        )

    return {
        'period_start':      period_start,
        'period_end':        period_end,
        'period_label':      period_label,
        'organisation':      organisation or 'All Partners',
        'total_submissions': total,
        'counts':            counts,
        'fistula_cases':     fistula_cases,
        'mpdsr_cases':       mpdsr_cases,
        'top_kpis':          top_kpis,
        'chart_data':        chart_data,   # list of (label, value) tuples, ascending
        # Real values for the formerly-fabricated generator fields:
        'pending':           pending,
        'active_workers':    active_workers,
        'mom_pct':           mom_pct,
        'monthly_trend':     monthly_trend,
        'top_districts':     top_districts,
        'districts_active':  districts_active,
        'by_partner':        by_partner,
    }
