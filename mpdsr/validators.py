"""MPDSR logic-error flagging.

Per Animesh's QA-gate slide (deck slide 9): when an MPDSR maternal death is
submitted with implausible values, the manager approval queue should flag
the row with an amber advisory so the manager can scrutinise + reject with
a note. This module computes the flag tags from a raw Kobo payload.

Each flag tag is a short stable string the frontend can translate. The
flags are advisory only — they do not block submission or approval.
"""
from __future__ import annotations

import datetime
from typing import Any

from django.utils import timezone

# ─── Flag tag constants (stable identifiers, do not rename) ─────────────────

FLAG_AGE_LOW = 'AGE_LOW'         # mother's age < 14 on a maternal death
FLAG_AGE_HIGH = 'AGE_HIGH'       # mother's age > 55 on a maternal death
FLAG_CAUSE_EMPTY = 'CAUSE_EMPTY' # cause_of_death blank/null on maternal death
FLAG_DATE_FUTURE = 'DATE_FUTURE' # date_of_death in the future
FLAG_DATE_OLD = 'DATE_OLD'       # date_of_death > 2 years ago

ALL_FLAGS = (
    FLAG_AGE_LOW, FLAG_AGE_HIGH, FLAG_CAUSE_EMPTY,
    FLAG_DATE_FUTURE, FLAG_DATE_OLD,
)

# Thresholds — named constants per coding-style.md (no magic numbers).
_AGE_LOW_THRESHOLD = 14
_AGE_HIGH_THRESHOLD = 55
_DATE_OLD_YEARS = 2


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_date(value: Any) -> datetime.date | None:
    if value is None or value == '':
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    s = str(value).strip()
    # Try ISO first, then a couple of common shapes.
    for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%d-%m-%Y', '%d/%m/%Y'):
        try:
            return datetime.datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    return None


def compute_logic_flags(
    *,
    death_type: str,
    age_years: int | None,
    cause_of_death: str | None,
    date_of_death: datetime.date | None,
) -> list[str]:
    """Return the list of flag tags raised for this set of values.

    Only flags relevant to the death type are raised — age and cause checks
    are maternal-only per spec; date checks apply to all MPDSR cases.
    """
    flags: list[str] = []
    is_maternal = (death_type or '').lower() == 'maternal'

    if is_maternal:
        age = _safe_int(age_years)
        if age is not None and age < _AGE_LOW_THRESHOLD:
            flags.append(FLAG_AGE_LOW)
        if age is not None and age > _AGE_HIGH_THRESHOLD:
            flags.append(FLAG_AGE_HIGH)
        if not (cause_of_death or '').strip():
            flags.append(FLAG_CAUSE_EMPTY)

    today = timezone.now().date()
    if date_of_death:
        if date_of_death > today:
            flags.append(FLAG_DATE_FUTURE)
        # 2 years old cutoff — late reporting.
        cutoff = today - datetime.timedelta(days=365 * _DATE_OLD_YEARS)
        if date_of_death < cutoff:
            flags.append(FLAG_DATE_OLD)

    return flags


def compute_flags_from_submission(submission) -> list[str]:
    """Compute logic flags directly from a pending KoboSubmission.

    Used by the manager approval queue so the amber advisory appears before
    the MPDSRCase row is materialised at approval time. Mirrors the field
    extraction in MPDSRCaseManager.get_or_create_from_submission to keep the
    pre- and post-approval flags consistent.
    """
    raw = submission.raw_data or {}
    sub = (raw.get('form_type') or '').strip().lower()

    # Maternal forms: F4 explicit; F1/F2 carry death_type field; everything
    # else (F3/F5/F6) is perinatal and skips age/cause checks.
    if sub == 'f4':
        death_type = 'maternal'
    elif sub in ('f3', 'f5', 'f6'):
        death_type = 'perinatal'
    else:
        dt_raw = (raw.get(f'{sub}_death_type') or raw.get('death_type') or '').lower()
        death_type = 'perinatal' if dt_raw in ('stillbirth', 'neonatal', 'perinatal') else 'maternal'

    age_raw = (
        raw.get(f'{sub}_mother_age') if sub else None
    ) or raw.get('f1_mother_age') or raw.get('f2_mother_age') \
        or raw.get('f3_mother_age') or raw.get('f4_mother_age') \
        or raw.get('f5_mother_age') or raw.get('f6_mother_age')

    cause = (
        raw.get('f4_probable_cause') or raw.get('f5_probable_cause')
        or raw.get('f6_contributing_factors') or raw.get('f2_cause_of_death')
        or ''
    )

    # date_of_death — try common field names, then fall back to submitted_at.
    date_raw = (
        raw.get('date_of_death')
        or raw.get(f'{sub}_date_of_death') if sub else None
    ) or raw.get('f1_date_of_death') or raw.get('f2_date_of_death') \
        or raw.get('f4_date_of_death') or raw.get('f5_date_of_death')

    date_of_death = _parse_date(date_raw)
    if date_of_death is None:
        submitted = submission.submitted_at
        if hasattr(submitted, 'date'):
            date_of_death = submitted.date()
        elif isinstance(submitted, datetime.date):
            date_of_death = submitted

    return compute_logic_flags(
        death_type=death_type,
        age_years=_safe_int(age_raw),
        cause_of_death=cause,
        date_of_death=date_of_death,
    )
