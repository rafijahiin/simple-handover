"""
CIPRB (Centre for Injury Prevention and Research, Bangladesh) indicator
compute functions.

Three activity codes from the fixture:

  F.C    — Fistula Corner: women diagnosed at District Hospital.
           Counted from fistula.CIPRBFistulaCase (current_stage diagnosed
           and later) — the SAME source as the CIPRB dashboard funnel, so
           the tracker and dashboard never disagree. Target_value is NULL
           in the seed (workshop confirms).

  F.Camp — Fistula Campaign: suspected fistula cases identified via house
           visits. Counted from fistula.CIPRBFistulaCase (all stages =
           the dashboard funnel's 'suspected' total).

  B      — Baseline assessment: CIPRB-managed survey instrument. Maps
           to baseline.BaselineSurvey rows (already exists) — kept here
           as a passthrough for completeness even though the legacy
           Baseline webhook auto-approves at the FormType level.
"""
from django.db.models import Q

APPROVED = 'APPROVED'


# Monotonic pipeline stages, oldest → latest. A case at a later stage has
# passed through every earlier one (mirrors fistula.views.fistula_aggregates,
# the single source of truth for the CIPRB dashboard funnel + KPI band).
_STAGES = ['suspected', 'diagnosed', 'referred', 'repaired', 'rehabilitated']


def compute_F_C(org, period_start, period_end):
    """Fistula Corner — diagnosed cases at District Hospital.

    Reads the SAME source as the CIPRB dashboard (CIPRBFistulaCase, the
    Fistula Question Bank), not the legacy FistulaCornerCase. 'Diagnosed' is
    cumulative across diagnosed → rehabilitated, so this equals the dashboard
    funnel's 'diagnosed' count. Counts all cases (the funnel is all-time, like
    the dashboard) so the tracker and dashboard never disagree."""
    from fistula.ciprb_models import CIPRBFistulaCase
    return CIPRBFistulaCase.objects.filter(
        approval_status='APPROVED',
        current_stage__in=_STAGES[1:],  # diagnosed and later
    ).count()


def compute_F_Camp(org, period_start, period_end):
    """Fistula Campaign — suspected cases identified via house visits.

    Same source as the dashboard (CIPRBFistulaCase). 'Suspected' is the whole
    cohort (every case is suspected first), so this equals the dashboard
    funnel's 'suspected' total."""
    from fistula.ciprb_models import CIPRBFistulaCase
    return CIPRBFistulaCase.objects.filter(
        approval_status='APPROVED',
        current_stage__in=_STAGES,  # all identified cases
    ).count()


def compute_Baseline(org, period_start, period_end):
    """Verified baseline interviews entered during the period.

    This imported `BaselineSurvey` — a model that has not existed since the
    baseline app was rebuilt around `BaselineResponse` — and the ImportError
    fallback silently returned 0. The home page's flagship indicator therefore
    read "Baseline assessment records entered: 0" against 684 verified
    interviews for the whole collection period. A drifted import must fail
    loudly, not report zero: the fallback is gone.

    BaselineResponse rows exist only after CIPRB verification, so this counts
    verified interviews — consistent with the approved-records-only rule.
    De-duplicated re-submissions are excluded.
    """
    from baseline.models import BaselineResponse
    return BaselineResponse.objects.filter(
        created_at__date__range=(period_start, period_end),
        is_duplicate=False,
    ).count()


# ─── Activity-code registry ──────────────────────────────────────────────────
# CIPRB rows in the fixture: F.C, F.Camp, B. All have target_value=NULL
# until the workshop confirms — the compute fns still run so the dashboard
# can show "X diagnosed / Not Set" rather than "Module pending".

ACTIVITY_REGISTRY = {
    'F.C':    compute_F_C,
    'F.Camp': compute_F_Camp,
    'B':      compute_Baseline,
}

# All CIPRB activities take (org, period_start, period_end) — no org-only codes.
ORG_ONLY_CODES: set[str] = set()
