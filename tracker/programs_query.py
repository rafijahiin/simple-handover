"""
Registry of programs form types and helper queries for the Reporting Progress Tracker.
Maps form type keys → (ModelClass, human label, Bangla label, category).
"""
from __future__ import annotations

import datetime
import logging

logger = logging.getLogger(__name__)

# ── Form type registry ─────────────────────────────────────────────────────────
# key: (model_import_path, label_en, label_bn, category)
# Model classes are imported lazily to avoid circular import issues.

PROGRAMS_REGISTRY: dict[str, tuple[str, str, str, str]] = {
    # key:                (model_name,              label_en,                label_bn,                category)
    # ── PHD new forms ─────────────────────────────────────────────────────────
    'client_registration':('Client',                'FSW Registrations',     'যৌনকর্মী নিবন্ধন',      'Clinical'),
    'clinic_visit':       ('ClinicVisit',            'Clinic Visits',         'ক্লিনিক পরিদর্শন',      'Clinical'),
    'hiv_sti_test':       ('HIVSTITestResult',       'HIV / STI Tests',       'এইচআইভি পরীক্ষা',       'Clinical'),
    'referral':           ('Referral',               'Referrals',             'রেফারেল',                'Community'),
    'phd_counselling':    ('PHDCounsellingReport',   'Counselling Reports',   'কাউন্সেলিং রিপোর্ট',     'Community'),
    'group_education':    ('GroupEducationSession',  'Group Education',       'দলগত স্বাস্থ্য শিক্ষা', 'Community'),
    'training_event':     ('TrainingEvent',          'Events & Trainings',    'ইভেন্ট ও প্রশিক্ষণ',    'Operations'),
    'iec_material':       ('IECMaterial',            'IEC Materials',         'আইইসি উপকরণ',           'Operations'),
    'stock_entry':        ('StockEntry',             'Stock Entries',         'স্টক এন্ট্রি',           'Operations'),
    'gbv_corner':         ('GBVCornerRecord',        'GBV Corners',           'জিবিভি কর্নার',          'Operations'),
    # ── Bandhu / shared forms ─────────────────────────────────────────────────
    'adr_record':         ('ADRRecord',              'ADR Records',           'পার্শ্বপ্রতিক্রিয়া',   'Clinical'),
    'autoclave_log':      ('AutoclaveLog',           'Autoclave Logs',        'অটোক্লেভ লগ',           'Clinical'),
    'antenatal_card':     ('AntenatalCard',          'Antenatal Cards',       'প্রসব পূর্ব যত্ন',      'Clinical'),
    'htc_counselling':    ('HTCCounselling',         'HTC Counselling',       'এইচটিসি পরামর্শ',       'Clinical'),
    'individual_counselling': ('IndividualCounselling', 'Individual Counselling', 'ব্যক্তিগত পরামর্শ',  'Community'),
    'mh_screening':       ('MHScreening',            'MH Screenings',         'মানসিক স্বাস্থ্য',      'Clinical'),
    'gbv_case':           ('GBVCase',                'GBV Cases',             'জিবিভি কেস',             'Community'),
    'outreach_session':   ('OutreachSession',        'Outreach Sessions',     'আউটরিচ সেশন',           'Community'),
    'wellness_logbook':   ('WellnessLogbookEntry',   'Wellness Logbook (F-01)','ওয়েলনেস লগবুক',        'Community'),
    'hygiene_kit':        ('SafetyHygieneKit',       'Hygiene Kits',          'হাইজিন কিট',             'Community'),
    'coord_meeting':      ('CoordMeeting',           'Coord. Meetings',       'সমন্বয় সভা',            'Operations'),
    'mobile_camp':        ('MobileHealthCamp',       'Mobile Health Camps',   'মোবাইল ক্যাম্প',        'Operations'),
}

LEGACY_REGISTRY: dict[str, tuple[str, str, str]] = {
    'mpdsr':    ('MPDSR Cases',        'MPDSR কেস',              'Legacy'),
    'fistula':  ('Fistula Campaign',   'ফিস্টুলা ক্যাম্পেইন',   'Legacy'),
    'activity': ('Activity Reports',   'কার্যক্রম রিপোর্ট',      'Legacy'),
    'baseline': ('Baseline Survey',    'বেসলাইন সমীক্ষা',        'Legacy'),
}

CATEGORY_ORDER = ['Clinical', 'Community', 'Operations', 'Legacy']

# ── Per-org form type lists ────────────────────────────────────────────────────
# Defines which form types each organisation actually uses.
# PHD: maternal/reproductive health — ANC and Mobile Camps are PHD-only.
# Bandhu: key populations (FSW, TG, MSM) — Hygiene Kit is Bandhu-only.
# Shared forms (clinic_visit, outreach, counselling, etc.) appear in both lists.
# Used by ProgramsSummaryView to avoid querying irrelevant form types per org.

ORG_FORM_TYPES: dict[str, list[str]] = {
    'PHD': [
        # Clinical — from Patient Services form
        'client_registration', 'clinic_visit', 'hiv_sti_test',
        # Community — from Patient Services + Activity & Ops
        'referral', 'phd_counselling', 'group_education',
        # Operations — from Activity & Ops form
        'training_event', 'iec_material', 'stock_entry', 'gbv_corner',
    ],
    'Bandhu': [
        # Only the models Bandhu's 2 Kobo forms actually write to (per
        # bandhu_handlers.py). The Service Log → ClinicVisit (F-05),
        # HIVSTITestResult (F-06), GBVCase (F-02), IndividualCounselling
        # (F-03/Counseling), Referral (Referral/F-08). The Activity & Ops
        # form → OutreachSession (F-04), MobileHealthCamp (F-10),
        # TrainingEvent/CoordMeeting (F-12), IECMaterial (F-14).
        # (Autoclave / ADR / MH-screening / HTC-counselling / group-education
        # / hygiene-kit are NOT Bandhu tools — removed.)
        # F-01 Wellness Logbook is Bandhu's PRIMARY record — every per-client
        # service is logged here (they file no separate F-05/F-06), so it must
        # lead the intake panel or their biggest dataset stays invisible.
        'wellness_logbook',
        # Clinical
        'clinic_visit', 'hiv_sti_test',
        # Community
        'individual_counselling', 'gbv_case', 'referral', 'outreach_session',
        # Operations
        'mobile_camp', 'training_event', 'coord_meeting', 'iec_material',
    ],
}


def _get_programs_model(model_name: str):
    """Lazily import a programs model by class name."""
    from programs import models as pm
    return getattr(pm, model_name)


def count_programs(form_type_key: str, organisation: str,
                   year: int, month: int, approved_only: bool = True) -> int:
    """Count programs submissions for a period.

    approved_only=True (default) → APPROVED rows only, as the indicators, alerts
    and progress tracker require. approved_only=False → every submission that
    came in (PENDING + MANAGER_APPROVED + APPROVED, excluding REJECTED), for the
    "what's being submitted" intake panel, which is about field activity, not
    sign-off."""
    if form_type_key not in PROGRAMS_REGISTRY:
        return 0
    model_name = PROGRAMS_REGISTRY[form_type_key][0]
    try:
        model = _get_programs_model(model_name)
        qs = model.objects.filter(
            created_at__year=year,
            created_at__month=month,
        )
        if approved_only:
            qs = qs.filter(approval_status='APPROVED')
        else:
            qs = qs.exclude(approval_status='REJECTED')
        if organisation:
            qs = qs.filter(organisation=organisation)
        return qs.count()
    except Exception as exc:
        logger.debug('count_programs(%s, %s): %s', form_type_key, organisation, exc)
        return 0


def available_program_months(organisation: str, form_type_keys: list[str],
                             limit: int = 12) -> list[dict]:
    """Distinct (year, month) that have ANY submission for this partner across
    the given form types, newest first. Powers the intake panel's month picker
    so a partner whose data is all from last month is not stranded on an empty
    current month. Counts all statuses (intake view)."""
    from django.db.models import DateField
    from django.db.models.functions import TruncMonth
    months: set[tuple[int, int]] = set()
    for key in form_type_keys:
        if key not in PROGRAMS_REGISTRY:
            continue
        try:
            model = _get_programs_model(PROGRAMS_REGISTRY[key][0])
            qs = model.objects.exclude(approval_status='REJECTED')
            if organisation:
                qs = qs.filter(organisation=organisation)
            for d in qs.annotate(m=TruncMonth('created_at')).values_list('m', flat=True).distinct():
                if d:
                    months.add((d.year, d.month))
        except Exception as exc:
            logger.debug('available_program_months(%s, %s): %s', key, organisation, exc)
    ordered = sorted(months, reverse=True)[:limit]
    return [{'year': y, 'month': m} for y, m in ordered]


def last_submission_programs(form_type_key: str,
                             organisation: str) -> datetime.datetime | None:
    """Return the created_at of the most recent approved submission, or None."""
    if form_type_key not in PROGRAMS_REGISTRY:
        return None
    model_name = PROGRAMS_REGISTRY[form_type_key][0]
    try:
        model = _get_programs_model(model_name)
        qs = model.objects.filter(approval_status='APPROVED')
        if organisation:
            qs = qs.filter(organisation=organisation)
        obj = qs.order_by('-created_at').first()
        return obj.created_at if obj else None
    except Exception:
        return None


def has_recent_programs(form_type_key: str, organisation: str,
                        cutoff: datetime.datetime) -> bool:
    """Return True if at least one submission exists after cutoff."""
    if form_type_key not in PROGRAMS_REGISTRY:
        return True   # unknown type: don't flag as gap
    model_name = PROGRAMS_REGISTRY[form_type_key][0]
    try:
        model = _get_programs_model(model_name)
        qs = model.objects.filter(created_at__gte=cutoff)
        if organisation:
            qs = qs.filter(organisation=organisation)
        return qs.exists()
    except Exception:
        return True


def daily_reporting_activity(organisation: str, threshold_dt, today_start):
    """Field-reporting activity from the PROGRAMS submission models, for the
    daily-reporting health widget.

    Counts SUBMISSIONS regardless of approval status (only REJECTED is excluded)
    — because daily reporting answers "did the field team submit today?", which
    is independent of whether a manager has approved the record yet. A record
    submitted this morning but still PENDING/MANAGER_APPROVED in the queue IS a
    report, and must not read as silence. This matches the gap-alert engine
    (has_recent_programs, which never filtered on approval) and the caller's
    intent; the earlier APPROVED-only filter under-reported every partner while a
    review backlog existed.

    Client REGISTRATIONS COUNT (both orgs, same rule). Registering a client is
    real field-reporting work — for PHD it IS the main daily activity (FSW
    registration), and excluding it made PHD read 0 while it had a pending
    registration backlog, even though Bandhu (auto-approved registrations, service
    records elsewhere) showed a number. The rule is per-TYPE and identical for
    both partners, never per-org.

    Only PHDCounsellingReport is EXCLUDED — it is a self-reported MONTHLY desk
    aggregate (one row = a whole month's counselling summary), not a per-event
    field submission, so it would misrepresent daily activity. (The old "43 off a
    batch of registrations" inflation was a bulk-load artefact, not normal field
    reporting; a real daily registration IS a report and should show.) The legacy
    KoboSubmission table holds none of the partners' current data, so without this
    the widget reads 0/silent for PHD/Bandhu/CIPRB forever.

    Returns (recent_count, today_count, today_centre_codes, last_submitted_at).
    """
    from django.apps import apps
    # Monthly desk aggregates only — never a per-org exclusion. Client
    # registrations count as field reporting for BOTH PHD and Bandhu.
    EXCLUDE = {'PHDCounsellingReport'}
    recent_count = today_count = 0
    today_codes: set[str] = set()
    last = None
    # The CIPRB surveillance models (MPDSR cases / actions / near-miss /
    # death-notifications / fistula) live in the mpdsr + fistula apps, NOT the
    # programs app — so a programs-only scan left the CIPRB daily-reporting tile
    # permanently silent regardless of real CIPRB submissions. Add them
    # explicitly; each carries organisation/created_at/approval_status, so the
    # field guard below still applies (aggregate/legacy tables without the triple
    # are skipped automatically).
    models = list(apps.get_app_config('programs').get_models())
    for _app_label, _model_name in (
        ('mpdsr',   'MPDSRCase'),
        ('mpdsr',   'MPDSRAction'),
        ('mpdsr',   'MaternalNearMissCase'),
        ('mpdsr',   'MPDSRDeathNotification'),
        ('fistula', 'CIPRBFistulaCase'),
    ):
        try:
            models.append(apps.get_model(_app_label, _model_name))
        except Exception:
            pass
    for model in models:
        if model.__name__ in EXCLUDE:
            continue
        fields = {f.name for f in model._meta.get_fields()}
        if not {'organisation', 'created_at', 'approval_status'} <= fields:
            continue
        try:
            # Submission-based: any record that arrived and was not rejected is a
            # report (PENDING / MANAGER_APPROVED / APPROVED all count). Approval
            # is the manager's separate QA step, not a precondition for "reported".
            base = model.objects.exclude(approval_status='REJECTED')
            if organisation:
                base = base.filter(organisation=organisation)
            recent_count += base.filter(created_at__gte=threshold_dt).count()
            today_qs = base.filter(created_at__gte=today_start)
            today_count += today_qs.count()
            if 'center' in fields:
                today_codes.update(
                    c for c in today_qs.values_list('center__code', flat=True) if c
                )
            obj = base.order_by('-created_at').values_list('created_at', flat=True).first()
            if obj and (last is None or obj > last):
                last = obj
        except Exception as exc:
            logger.debug('daily_reporting_activity(%s, %s): %s',
                         organisation, model.__name__, exc)
    return recent_count, today_count, today_codes, last


def programs_last_by_centre(organisation: str):
    """Map centre_code → most recent non-REJECTED submission datetime across the
    programs + CIPRB surveillance models, in one aggregate pass per model.

    Powers the per-centre "hours silent" drill-down. Without it that drill-down
    read only the legacy KoboSubmission table, so for PHD/Bandhu — whose field
    data lives entirely in the programs models — every non-today centre showed
    "hours silent = —" even when it had submitted recently. Same status rule as
    daily_reporting_activity (submission-based, exclude REJECTED) and the same
    EXCLUDE set (monthly desk aggregates only; Client registrations count)."""
    from django.apps import apps
    from django.db.models import Max
    EXCLUDE = {'PHDCounsellingReport'}
    result: dict[str, datetime.datetime] = {}
    models = list(apps.get_app_config('programs').get_models())
    for _app_label, _model_name in (
        ('mpdsr',   'MPDSRCase'),
        ('mpdsr',   'MPDSRAction'),
        ('mpdsr',   'MaternalNearMissCase'),
        ('mpdsr',   'MPDSRDeathNotification'),
        ('fistula', 'CIPRBFistulaCase'),
    ):
        try:
            models.append(apps.get_model(_app_label, _model_name))
        except Exception:
            pass
    for model in models:
        if model.__name__ in EXCLUDE:
            continue
        fields = {f.name for f in model._meta.get_fields()}
        if not {'organisation', 'created_at', 'approval_status'} <= fields:
            continue
        if 'center' not in fields:
            continue
        try:
            qs = model.objects.exclude(approval_status='REJECTED')
            if organisation:
                qs = qs.filter(organisation=organisation)
            for row in qs.values('center__code').annotate(last=Max('created_at')):
                code, last = row['center__code'], row['last']
                if not code or last is None:
                    continue
                if code not in result or last > result[code]:
                    result[code] = last
        except Exception as exc:
            logger.debug('programs_last_by_centre(%s, %s): %s',
                         organisation, model.__name__, exc)
    return result


def count_legacy(form_type_key: str, organisation: str,
                 year: int, month: int) -> int:
    """Count approved legacy KoboSubmission records."""
    try:
        from submissions.models import KoboSubmission, SubmissionStatus
        qs = KoboSubmission.objects.filter(
            form_type=form_type_key,
            status=SubmissionStatus.APPROVED,
            submitted_at__year=year,
            submitted_at__month=month,
        )
        if organisation:
            qs = qs.filter(partner=organisation)
        return qs.count()
    except Exception:
        return 0


def last_submission_legacy(form_type_key: str,
                           organisation: str) -> datetime.datetime | None:
    """Return the submitted_at of the most recent approved legacy submission."""
    try:
        from submissions.models import KoboSubmission, SubmissionStatus
        qs = KoboSubmission.objects.filter(
            form_type=form_type_key,
            status=SubmissionStatus.APPROVED,
        )
        if organisation:
            qs = qs.filter(partner=organisation)
        obj = qs.order_by('-submitted_at').first()
        return obj.submitted_at if obj else None
    except Exception:
        return None


def has_recent_legacy(form_type_key: str, organisation: str,
                      cutoff: datetime.datetime) -> bool:
    try:
        from submissions.models import KoboSubmission
        qs = KoboSubmission.objects.filter(
            form_type=form_type_key,
            submitted_at__gte=cutoff,
        )
        if organisation:
            qs = qs.filter(partner=organisation)
        return qs.exists()
    except Exception:
        return True
