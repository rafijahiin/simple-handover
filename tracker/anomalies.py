"""
Anomaly detection service — pure functions returning structured findings.

Each detector returns a list of finding dicts with the shape:

    {
        'type':         str   # mom_drop | pace_behind | submission_gap | backlog
        'severity':     str   # info | warning | critical
        'partner':      str | None
        'indicator':    str | None     # activity_code if applicable
        'title':        str   # one-line headline
        'message':      str   # plain-English description
        'value':        Any   # the figure that triggered the alert
        'baseline':     Any   # what value was expected
        'detected_at':  str   # ISO datetime
    }

Findings are computed on demand (no persistence). The /api/tracker/
anomalies/ view caches the result briefly so dashboards that poll
every 30-60 s don't re-scan the database on every request.

Tuning thresholds:
    MOM_DROP_PCT          40 — flag if this month's submissions are
                                 ≥40 % below last month's
    PACE_BEHIND_PCT       50 — flag if an indicator's % achieved is
                                 below 50 % of the linear pace at
                                 the current point in the programme
    SUBMISSION_GAP_HOURS  48 — flag if no submissions from a partner
                                 in 48 hours (matches the IDMS handoff)
    BACKLOG_THRESHOLD     20 — flag if a partner has > 20 pending
                                 review items
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone as _tz
from typing import Any

from django.utils import timezone

# Thresholds — tuneable via settings if needed.
MOM_DROP_PCT = 40
PACE_BEHIND_PCT = 50
SUBMISSION_GAP_HOURS = 48
BACKLOG_THRESHOLD = 20

# Programme window — used to compute linear-pace expected % for indicator
# checks. Pulled from the IDMS handoff inception → workshop window.
PROGRAMME_START = datetime(2026, 5, 21, tzinfo=_tz.utc)
PROGRAMME_END   = datetime(2026, 11, 20, tzinfo=_tz.utc)


def _now() -> datetime:
    return timezone.now()


def _iso(dt: datetime) -> str:
    return dt.isoformat()


# ─── 1. MoM drop in submissions ──────────────────────────────────────────────

def detect_mom_drop(partner: str | None = None) -> list[dict[str, Any]]:
    """Flag partners whose this-month submission count is ≥ 40 % below
    last month. Single severity = warning; an extreme drop (≥ 70 %)
    escalates to critical."""
    from submissions.models import KoboSubmission, SubmissionStatus

    now = _now()
    this_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_end = this_start - timedelta(seconds=1)
    last_start = last_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    partners = [partner] if partner else ('CIPRB', 'Bandhu', 'PHD')
    findings: list[dict[str, Any]] = []

    for p in partners:
        base = KoboSubmission.objects.filter(
            partner=p,
            status__in=[SubmissionStatus.APPROVED, SubmissionStatus.PENDING],
        )
        this_n = base.filter(submitted_at__gte=this_start).count()
        last_n = base.filter(
            submitted_at__gte=last_start, submitted_at__lte=last_end,
        ).count()
        if last_n == 0:
            # No baseline — cannot compute % drop. Skip silently.
            continue
        drop_pct = ((last_n - this_n) / last_n) * 100
        if drop_pct < MOM_DROP_PCT:
            continue
        severity = 'critical' if drop_pct >= 70 else 'warning'
        findings.append({
            'type':       'mom_drop',
            'severity':   severity,
            'partner':    p,
            'indicator':  None,
            'title':      f'{p} submissions down {drop_pct:.0f}% MoM',
            'message': (
                f'{p} received {this_n} submissions this month vs '
                f'{last_n} last month — a {drop_pct:.0f}% drop. '
                f'Review field-team submission cadence with the focal person.'
            ),
            'value':      this_n,
            'baseline':   last_n,
            'detected_at': _iso(now),
        })
    return findings


# ─── 2. Indicator pace behind ────────────────────────────────────────────────

def detect_indicator_pace_behind(partner: str | None = None) -> list[dict[str, Any]]:
    """Flag indicators whose % achieved is below the linear-pace baseline
    for the current point in the programme. Skips unlinked indicators
    (no compute function wired) and indicators with target_value = None."""
    from indicators.service import get_partner_indicator_progress

    now = _now()
    total_window = (PROGRAMME_END - PROGRAMME_START).total_seconds()
    elapsed = max(0, (now - PROGRAMME_START).total_seconds())
    linear_pace_pct = (elapsed / total_window) * 100 if total_window > 0 else 0

    # If we're less than 10% into the programme, suppress all pace checks
    # — every indicator will look behind at week 1.
    if linear_pace_pct < 10:
        return []

    partners = [partner] if partner else ('CIPRB', 'Bandhu', 'PHD')
    findings: list[dict[str, Any]] = []

    for p in partners:
        try:
            rows = get_partner_indicator_progress(p, PROGRAMME_START.date(), PROGRAMME_END.date())
        except Exception:
            continue
        for r in rows:
            if r['unlinked'] or r['target_value'] is None or r['percentage'] is None:
                continue
            # Pace ratio: actual % / linear-pace %. A ratio below
            # PACE_BEHIND_PCT/100 means the indicator is behind.
            ratio = (r['percentage'] / linear_pace_pct) * 100 if linear_pace_pct > 0 else 100
            if ratio >= PACE_BEHIND_PCT:
                continue
            severity = 'critical' if ratio < 25 else 'warning'
            findings.append({
                'type':       'pace_behind',
                'severity':   severity,
                'partner':    p,
                'indicator':  r['activity_code'],
                'title':      f'{p} {r["activity_code"]} behind pace',
                'message': (
                    f'{r["indicator_label"]} is at {r["percentage"]:.0f}% achieved '
                    f'with {linear_pace_pct:.0f}% of the programme window elapsed '
                    f'(ratio {ratio:.0f}%).'
                ),
                'value':      r['percentage'],
                'baseline':   linear_pace_pct,
                'detected_at': _iso(now),
            })
    return findings


# ─── 3. 48-hour submission gap ───────────────────────────────────────────────

def detect_submission_gap(partner: str | None = None) -> list[dict[str, Any]]:
    """Flag partners with no submissions in the last 48 hours."""
    from submissions.models import KoboSubmission, SubmissionStatus

    now = _now()
    cutoff = now - timedelta(hours=SUBMISSION_GAP_HOURS)
    partners = [partner] if partner else ('CIPRB', 'Bandhu', 'PHD')
    findings: list[dict[str, Any]] = []

    for p in partners:
        latest = (
            KoboSubmission.objects
            .filter(partner=p, status__in=[SubmissionStatus.APPROVED, SubmissionStatus.PENDING])
            .order_by('-submitted_at').first()
        )
        if latest is None:
            # No submissions ever — suppress (not an anomaly, it's an empty state).
            continue
        if latest.submitted_at >= cutoff:
            continue
        hours_silent = (now - latest.submitted_at).total_seconds() / 3600
        findings.append({
            'type':       'submission_gap',
            'severity':   'warning',
            'partner':    p,
            'indicator':  None,
            'title':      f'{p} silent for {hours_silent:.0f}h',
            'message': (
                f'No submissions from {p} since '
                f'{latest.submitted_at.strftime("%d %b %Y, %H:%M")}. '
                f'Telegram the focal person to verify field-team connectivity.'
            ),
            'value':      hours_silent,
            'baseline':   SUBMISSION_GAP_HOURS,
            'detected_at': _iso(now),
        })
    return findings


# ─── 4. Approval backlog ─────────────────────────────────────────────────────

def detect_backlog(partner: str | None = None) -> list[dict[str, Any]]:
    """Flag partners with > 20 pending review items."""
    from submissions.models import KoboSubmission, SubmissionStatus

    partners = [partner] if partner else ('CIPRB', 'Bandhu', 'PHD')
    findings: list[dict[str, Any]] = []
    now = _now()

    for p in partners:
        pending = KoboSubmission.objects.filter(
            partner=p, status=SubmissionStatus.PENDING,
        ).count()
        if pending <= BACKLOG_THRESHOLD:
            continue
        severity = 'critical' if pending > BACKLOG_THRESHOLD * 2 else 'warning'
        findings.append({
            'type':       'backlog',
            'severity':   severity,
            'partner':    p,
            'indicator':  None,
            'title':      f'{p} approval backlog: {pending}',
            'message': (
                f'{pending} submissions awaiting manager review for {p} '
                f'(threshold {BACKLOG_THRESHOLD}). Stale approvals delay '
                f'indicator updates and donor reporting.'
            ),
            'value':      pending,
            'baseline':   BACKLOG_THRESHOLD,
            'detected_at': _iso(now),
        })
    return findings


# ─── Aggregator ──────────────────────────────────────────────────────────────

def detect_all(partner: str | None = None) -> list[dict[str, Any]]:
    """Run every detector and return a flat list of findings, sorted by
    severity (critical → warning → info) then by detection time."""
    findings: list[dict[str, Any]] = []
    findings.extend(detect_mom_drop(partner))
    findings.extend(detect_indicator_pace_behind(partner))
    findings.extend(detect_submission_gap(partner))
    findings.extend(detect_backlog(partner))

    rank = {'critical': 0, 'warning': 1, 'info': 2}
    findings.sort(key=lambda f: (rank.get(f['severity'], 9), f['detected_at']))
    return findings
