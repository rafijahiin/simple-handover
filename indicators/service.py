"""
Indicator compute service — Step 3 wired contract.

Two public entry points:

  get_partner_indicator_progress(partner_code, period_start, period_end)
      → list of progress dicts, one per IndicatorTarget row for that
        partner. Used by the org dashboard pages + the homepage roll-up.

  get_indicator_progress(org, code, period_start, period_end)
      → single-row variant for the legacy SingleIndicatorProgressView
        endpoint at /api/indicators/progress/<code>/.

Each dict has the Step 3 shape:

  {
      activity_code:    str,         # canonical fixture code, e.g. '1.4a'
      objective_number: int,         # 0, 1, 2, 3, 4
      activity_label:   str,
      indicator_label:  str,
      target_value:     float | None,
      unit:             str,
      achievement:      int | float, # always a number — 0 if no records
      percentage:       float | None,# null if target is null (Not Set)
                                     # 0 if target > 0 and achievement = 0
                                     # rounded to 1 decimal otherwise
      unlinked:         bool,        # True if no compute function exists
                                     # yet for this activity_code (module
                                     # not built) — UI shows a small
                                     # "Module pending" tag
  }

Colour-band assignment (for the progress bar) lives in the frontend:
  >= 75      → green  #00B050
  40 .. 74.9 → yellow #FFC000
  <  40      → red    #FF0000
  None       → grey "Not Set"
"""
import logging
from django.core.cache import cache

from . import bandhu, ciprb, phd

logger = logging.getLogger(__name__)

# 60s, not 1h: indicator achievements are cached (the per-page compute hits each
# (partner, code) repeatedly), but a 1-hour window meant a manager's approval
# didn't show on the dashboard for up to an hour. The cache is the default
# per-worker LocMemCache, so there's no reliable cross-worker invalidation on
# approval — a short TTL is what makes new approvals appear promptly everywhere.
CACHE_TTL = 60

# Per-partner compute-function registries. CIPRB activities (F.C, F.Camp, B)
# now have compute fns backed by fistula.FistulaCornerCase,
# fistula.FistulaCampaignVisit, and baseline.BaselineSurvey respectively.
_REGISTRIES: dict[str, tuple[dict, set]] = {
    'Bandhu': (bandhu.ACTIVITY_REGISTRY, bandhu.ORG_ONLY_CODES),
    'PHD':    (phd.ACTIVITY_REGISTRY,    phd.ORG_ONLY_CODES),
    'CIPRB':  (ciprb.ACTIVITY_REGISTRY,  ciprb.ORG_ONLY_CODES),
}


def _ver_key(partner_code: str) -> str:
    return f'indicator-ver:{partner_code}'


def _partner_version(partner_code: str) -> int:
    """Per-partner cache version, folded into every achievement cache key.
    Bumping it (on approval) invalidates ALL of that partner's cached
    achievements at once — no pattern-delete needed, so it works on any cache
    backend. With a SHARED cache (Redis) the bump is visible to every worker, so
    an approval clears the stale numbers everywhere instantly; with the default
    per-worker LocMemCache it only clears the current worker, and CACHE_TTL is
    the cross-worker backstop."""
    key = _ver_key(partner_code)
    v = cache.get(key)
    if v is None:
        cache.add(key, 1, None)        # set only if still absent (race-safe)
        v = cache.get(key) or 1
    return v


def bump_partner_version(partner_code: str) -> None:
    """Invalidate every cached achievement for one partner — call when a
    submission's approval state changes so the dashboard recomputes at once."""
    key = _ver_key(partner_code)
    try:
        cache.incr(key)
    except ValueError:                 # key absent/expired
        cache.set(key, 2, None)


def _cache_key(partner_code: str, activity_code: str, period_start, period_end) -> str:
    return (f'indicator-v3:{partner_code}:{_partner_version(partner_code)}:'
            f'{activity_code}:{period_start}:{period_end}')


def _compute_achievement(partner_code: str, activity_code: str, period_start, period_end):
    """Return (achievement, unlinked) for a single (partner, code) pair.

    Always returns a numeric achievement (never None). On unlinked codes
    returns (0, True). On compute errors, logs and returns (0, False) —
    the failure is silent at the row level so the page still renders.
    """
    registry, org_only = _REGISTRIES.get(partner_code, ({}, set()))
    fn = registry.get(activity_code)
    if fn is None:
        return 0, True

    cache_key = _cache_key(partner_code, activity_code, period_start, period_end)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached, False

    try:
        if activity_code in org_only:
            value = fn(partner_code)
        else:
            if period_start is None or period_end is None:
                # Defensive — should not happen for non-org-only codes.
                logger.warning(
                    'Missing period args for non-org-only code %s/%s — returning 0',
                    partner_code, activity_code,
                )
                return 0, False
            value = fn(partner_code, period_start, period_end)
    except Exception:
        logger.exception(
            'Error computing achievement for %s/%s', partner_code, activity_code,
        )
        return 0, False

    cache.set(cache_key, value, CACHE_TTL)
    return value, False


def _percentage(achievement, target_value) -> float | None:
    """Step 3 percentage rules.

    - target None         → None (UI renders grey "Not Set" pill)
    - target > 0          → round(achievement / target * 100, 1)
                             (achievement=0 yields 0.0)
    - target == 0         → 0    (defensive; should not occur in fixture)
    """
    if target_value is None:
        return None
    if target_value > 0:
        return round((float(achievement) / float(target_value)) * 100, 1)
    return 0.0


# ─── Monthly cadence (Animesh's spec) ────────────────────────────────────────
#
# Each indicator carries two parallel metrics:
#   - OVERALL  — achievement vs full-programme target_value, 21 May → 20 Nov
#   - MONTHLY  — this calendar month's achievement vs this month's slice
#
# Both targets are SET BY UNFPA via the Target Config screen. The monthly
# slice lives in IndicatorTarget.monthly_targets as a JSON list of
# {month, target} entries. No auto-derivation — if a month isn't in the
# JSON, the monthly tile renders 'Not set' until UNFPA fills it.


def _month_window(today):
    """Return (month_start, month_end) date objects for the calendar month
    containing `today`. Inclusive on both ends."""
    import calendar, datetime
    start = today.replace(day=1)
    last_day = calendar.monthrange(today.year, today.month)[1]
    end = today.replace(day=last_day)
    return start, end


def _month_target(target_row, today) -> float | None:
    """Find this month's target.

    UNFPA sets the monthly split explicitly — same model as the overall
    target_value. No auto-derivation. If `monthly_targets` JSON doesn't
    contain an entry for today's YYYY-MM, the month renders as 'Not set'
    in the UI (orange pill) until UNFPA fills it in via Target Config.
    """
    key = today.strftime('%Y-%m')
    rows = target_row.monthly_targets or []
    for entry in rows:
        if isinstance(entry, dict) and entry.get('month') == key:
            try:
                return float(entry['target'])
            except (TypeError, ValueError, KeyError):
                continue
    return None


def _compute_monthly(partner_code: str, activity_code: str, today):
    """Run the indicator's compute fn over the current calendar month only.
    Returns (month_achievement, unlinked)."""
    month_start, month_end = _month_window(today)
    return _compute_achievement(partner_code, activity_code, month_start, month_end)


def _row_dict(target_row, achievement, unlinked: bool,
              today=None, partner_code: str | None = None) -> dict:
    """Convert an IndicatorTarget ORM row + computed achievement into the
    Step 3 progress dict shape, plus Animesh's monthly cadence fields.

    `today` and `partner_code` are required to compute monthly fields. If
    omitted, monthly_* come back as None (legacy callers stay correct).
    """
    target_val = float(target_row.target_value) if target_row.target_value is not None else None
    out = {
        'activity_code':    target_row.activity_code,
        'objective_number': target_row.objective_number,
        'activity_label':   target_row.activity_label,
        'indicator_label':  target_row.indicator_label,
        'target_value':     target_val,
        'unit':             target_row.unit,
        'achievement':      achievement,
        'percentage':       _percentage(achievement, target_val),
        'unlinked':         unlinked,
        # Monthly cadence — UNFPA-set, no auto fallback.
        'month_label':      today.strftime('%Y-%m') if today else None,
        'month_target':     None,
        'month_achievement': None,
        'month_percentage': None,
    }
    if today and partner_code:
        out['month_target'] = _month_target(target_row, today)
        ma, _ = _compute_monthly(partner_code, target_row.activity_code, today)
        out['month_achievement'] = ma
        out['month_percentage'] = _percentage(ma, out['month_target'])
    return out


# ─── Public API ───────────────────────────────────────────────────────────────

def get_partner_indicator_progress(partner_code: str, period_start, period_end,
                                   today=None) -> list[dict]:
    """Return progress dicts for every active IndicatorTarget under this partner.

    Rows are ordered by objective_number then activity_code so the frontend
    can render groups directly. Bandhu's missing Objective 3 is *not*
    auto-renumbered — that gap is intentional and the UI respects it.

    `today` enables monthly-cadence fields (Animesh spec). Pass the request
    date; the view layer does this.
    """
    from .models import IndicatorTarget

    targets = (
        IndicatorTarget.objects
        .filter(partner__code=partner_code, is_active=True)
        .order_by('objective_number', 'activity_code')
    )

    results = []
    for t in targets:
        achievement, unlinked = _compute_achievement(
            partner_code, t.activity_code, period_start, period_end,
        )
        results.append(_row_dict(t, achievement, unlinked,
                                 today=today, partner_code=partner_code))
    return results


PHD_REGISTRY_CODE = 'SL1R'
PHD_REGISTRY_TARGET = 3500   # mirrors SL1's programme "FSWs reached" target


def get_phd_registry_kpi(period_start, period_end, today) -> dict:
    """PHD headline "FSWs reached" = the Mother List registry (distinct
    approved, non-stub PHD clients), measured like Bandhu 1.1.

    Returned as a single IndicatorProgress-shaped row (code SL1R) so the PHD
    headline card can read it exactly like any other indicator. It is NOT an
    IndicatorTarget row, so it never enters get_partner_indicator_progress() —
    the SIDA framework table, the home roll-up, and the indicator mean stay
    unchanged. SL1 remains the narrower screening-service indicator.
    """
    cumulative, _ = _compute_achievement(
        'PHD', PHD_REGISTRY_CODE, period_start, period_end)
    month_ach, _ = _compute_monthly('PHD', PHD_REGISTRY_CODE, today)
    return {
        'activity_code':     PHD_REGISTRY_CODE,
        'objective_number':  0,
        'activity_label':    'Enrol FSWs onto the Mother List registry',
        'indicator_label':   'FSWs registered on the Mother List',
        'target_value':      float(PHD_REGISTRY_TARGET),
        'unit':              'FSWs',
        'achievement':       cumulative,
        'percentage':        _percentage(cumulative, PHD_REGISTRY_TARGET),
        'unlinked':          False,
        'month_label':       today.strftime('%Y-%m') if today else None,
        'month_target':      None,   # no UNFPA-set monthly slice for the registry
        'month_achievement': month_ach,
        'month_percentage':  None,
    }


def get_indicator_progress(partner_code: str, activity_code: str,
                           period_start=None, period_end=None,
                           today=None) -> dict:
    """Single-row variant for /api/indicators/progress/<code>/.

    Looks up the IndicatorTarget row by (partner_code, activity_code) and
    returns the same Step 3 progress dict. If no matching target row
    exists, returns a degenerate dict with target_value=None, unlinked=True
    so the endpoint still 200s (the legacy contract).
    """
    from .models import IndicatorTarget

    target_obj = IndicatorTarget.objects.filter(
        partner__code=partner_code,
        activity_code=activity_code,
        is_active=True,
    ).first()

    achievement, unlinked = _compute_achievement(
        partner_code, activity_code, period_start, period_end,
    )

    if target_obj is None:
        return {
            'activity_code':    activity_code,
            'objective_number': 0,
            'activity_label':   '',
            'indicator_label':  activity_code,
            'target_value':     None,
            'unit':             'count',
            'achievement':      achievement,
            'percentage':       None,
            'unlinked':         True,
            'month_label':      today.strftime('%Y-%m') if today else None,
            'month_target':     None,
            'month_achievement': None,
            'month_percentage': None,
        }
    return _row_dict(target_obj, achievement, unlinked,
                     today=today, partner_code=partner_code)


def invalidate_indicator_cache(partner_code: str, activity_code: str,
                               period_start=None, period_end=None) -> None:
    """Call this after a manager approves a submission that may affect
    the achievement count for an indicator."""
    key = _cache_key(partner_code, activity_code, period_start, period_end)
    cache.delete(key)


# ─── Legacy alias ─────────────────────────────────────────────────────────────

# Older callers (programs/views.py, dashboard/views.py) may still import
# `get_all_indicators_for_org`. Keep the name as a thin alias to preserve
# import compatibility until those callers are updated.
get_all_indicators_for_org = get_partner_indicator_progress
