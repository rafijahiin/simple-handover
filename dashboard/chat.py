"""
AI Programme Officer — chat backend.

Gathers live programme context from the database and answers natural-language
questions from managers and CIPRB/UNFPA staff using Groq / LLaMA 3.3 70B.

Entry point: answer_question(question, partner, user) → str
"""
from __future__ import annotations

import logging
from datetime import date

from django.utils import timezone

logger = logging.getLogger(__name__)

# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM = """\
You are the AI Programme Officer for CIPRB's UNFPA-funded Reproductive and \
Child Health (RCH) programme in Bangladesh.

You assist PHD managers, Bandhu managers, CIPRB senior staff, and UNFPA focal \
persons. You have access to real-time programme data provided in the context below.

Programme:
- PHD: maternal/reproductive health — Cox's Bazar (Rohingya + host community), \
Chattogram, Sylhet. PHD-only forms: antenatal cards, mobile health camps.
- Bandhu Social Welfare Society: key populations (FSW, TG, MSM) — Dhaka, \
Chittagong, Sylhet, Narayanganj, Comilla. Bandhu-only: hygiene kits.
- Shared forms: clinic visits, HIV/STI tests, HTC counselling, MH screenings, \
outreach sessions, GBV cases, individual counselling, group education, referrals, \
ADR records, autoclave logs, training events, coordination meetings.

Rules:
- Answer in 2–4 sentences unless the user asks for detail.
- Ground every claim in the data provided. Do not invent or extrapolate figures.
- If the data does not contain the answer, say so clearly and suggest what to check.
- Write in formal British English.
- Do not hedge with "as an AI" — you are a data-backed programme tool.
"""
# HARD RULE: Never include individual GBV case records, client names, or survivor details in context sent to Groq. Aggregate counts only.


# ── Context gathering ─────────────────────────────────────────────────────────

def _current_month() -> tuple[date, date]:
    """(first_day, last_day) of current calendar month."""
    today = timezone.now().date()
    import calendar
    last = calendar.monthrange(today.year, today.month)[1]
    return today.replace(day=1), today.replace(day=last)


def _previous_month() -> tuple[date, date]:
    """(first_day, last_day) of previous calendar month."""
    today = timezone.now().date()
    import calendar
    if today.month == 1:
        y, m = today.year - 1, 12
    else:
        y, m = today.year, today.month - 1
    last = calendar.monthrange(y, m)[1]
    return date(y, m, 1), date(y, m, last)


def _safe_count(model, org: str, start: date, end: date) -> int:
    try:
        qs = model.objects.filter(
            approval_status='APPROVED',
            created_at__date__gte=start,
            created_at__date__lte=end,
        )
        if org:
            qs = qs.filter(organisation=org)
        return qs.count()
    except Exception as exc:
        logger.error(
            'AI chat: DB query failed for %s [org=%r %s–%s]: %s',
            getattr(model, '__name__', model), org, start, end, exc,
        )
        return 0


def _gather_context(partner: str) -> dict:
    """
    Return a dict with current-month and previous-month programme totals,
    a category breakdown, and any active (unacknowledged) alerts.
    """
    from tracker.programs_query import ORG_FORM_TYPES, PROGRAMS_REGISTRY

    ps, pe     = _current_month()
    pp_s, pp_e = _previous_month()

    # Decide which form type keys to query
    if partner and partner in ORG_FORM_TYPES:
        keys = ORG_FORM_TYPES[partner]
    else:
        # Both orgs — union of all keys
        keys = list(PROGRAMS_REGISTRY.keys())

    # Import all programs models lazily
    try:
        from programs import models as pm
    except Exception as exc:
        logger.error(
            'AI chat: failed to import programs models — all counts will be zero: %s', exc
        )
        pm = None

    counts:      dict[str, int] = {}
    prev_counts: dict[str, int] = {}

    for key in keys:
        if key not in PROGRAMS_REGISTRY:
            continue
        model_name = PROGRAMS_REGISTRY[key][0]
        label      = PROGRAMS_REGISTRY[key][1]
        if pm is None:
            counts[label] = 0
            prev_counts[label] = 0
            continue
        try:
            model = getattr(pm, model_name)
        except AttributeError:
            continue
        counts[label]      = _safe_count(model, partner, ps, pe)
        prev_counts[label] = _safe_count(model, partner, pp_s, pp_e)

    total      = sum(counts.values())
    prev_total = sum(prev_counts.values())
    mom_pct    = (
        round((total - prev_total) / prev_total * 100, 1)
        if prev_total > 0 else (100.0 if total > 0 else 0.0)
    )

    # Active alerts
    alerts: list[str] = []
    try:
        from tracker.models import Alert
        from django.db.models import Q
        alert_qs = Alert.objects.filter(acknowledged=False)
        if partner:
            # Org isolation — a single-org manager must not see another team's
            # alerts in their AI chat context. Programme-wide alerts (blank
            # partner) stay visible to everyone.
            alert_qs = alert_qs.filter(Q(partner=partner) | Q(partner=''))
        for a in alert_qs.order_by('-created_at')[:6]:
            scope = f' [{a.partner}]' if a.partner else ''
            alerts.append(f'{a.get_severity_display().upper()}: {a.title}{scope}')
    except Exception as exc:
        logger.warning('AI chat: alert fetch failed: %s', exc)

    # Legacy fistula / MPDSR quick counts
    fistula = mpdsr = 0
    try:
        from submissions.models import KoboSubmission, SubmissionStatus, FormType
        qs = KoboSubmission.objects.filter(
            status=SubmissionStatus.APPROVED,
            submitted_at__date__gte=ps,
            submitted_at__date__lte=pe,
        )
        if partner:
            qs = qs.filter(partner=partner)
        fistula = qs.filter(form_type=FormType.FISTULA).count()
        mpdsr   = qs.filter(form_type=FormType.MPDSR).count()
    except Exception:
        pass

    return {
        'period':            ps.strftime('%B %Y'),
        'prev_period':       pp_s.strftime('%B %Y'),
        'partner':           partner or 'PHD + Bandhu (all)',
        'activities_this_month':  total,
        'activities_prev_month':  prev_total,
        'mom_change_pct':         mom_pct,
        'fistula_cases_this_month': fistula,
        'mpdsr_cases_this_month':   mpdsr,
        'activity_breakdown':      counts,
        'activity_breakdown_prev': prev_counts,
        'active_alerts':           alerts or ['No active alerts.'],
    }


def _build_context_text(ctx: dict) -> str:
    lines = [
        f"Reporting period: {ctx['period']}",
        f"Organisation filter: {ctx['partner']}",
        f"Total activities this month: {ctx['activities_this_month']}",
        f"Total activities previous month: {ctx['activities_prev_month']}",
        f"Month-on-month change: {ctx['mom_change_pct']:+.1f}%",
        f"Fistula cases (legacy) this month: {ctx['fistula_cases_this_month']}",
        f"MPDSR cases (legacy) this month: {ctx['mpdsr_cases_this_month']}",
        "",
        f"Activity breakdown — {ctx['period']} (this month, approved):",
    ]
    for label, val in ctx['activity_breakdown'].items():
        prev_val = ctx['activity_breakdown_prev'].get(label, 0)
        change = val - prev_val
        sign = '+' if change >= 0 else ''
        lines.append(f"  {label}: {val} ({sign}{change} vs previous month)")
    lines += [
        "",
        f"Activity breakdown — {ctx['prev_period']} (previous month, for reference):",
    ]
    for label, val in ctx['activity_breakdown_prev'].items():
        lines.append(f"  {label}: {val}")
    lines += [
        "",
        "Active programme alerts:",
    ]
    for a in ctx['active_alerts']:
        lines.append(f"  {a}")
    return '\n'.join(lines)


# ── Groq call ─────────────────────────────────────────────────────────────────

def answer_question(question: str, partner: str = '') -> str:
    """
    Gather live context and ask LLaMA 3.3 70B to answer the question.
    Returns a plain-text answer string.
    Returns a graceful fallback if the API is unavailable.
    """
    from django.conf import settings
    api_key = getattr(settings, 'GROQ_API_KEY', '')
    if not api_key:
        return (
            'The AI chat feature requires a GROQ_API_KEY environment variable. '
            'Please contact your system administrator.'
        )

    ctx  = _gather_context(partner)
    body = (
        f"Current programme data:\n\n{_build_context_text(ctx)}"
        f"\n\nQuestion: {question}"
    )

    # Audit FIX (CRITICAL) — was `from groq import Groq`, but the `groq`
    # package is NOT in requirements.txt, so this raised ImportError on every
    # call and the feature was permanently dead. Use the Groq OpenAI-compatible
    # REST endpoint via `requests`, matching the working pattern in
    # reports/ai_narrative.py and avoiding a new dependency. Timeout kept tight
    # (20s) so a slow LLM can't pin a gunicorn worker (only 2 workers).
    try:
        import requests
        response = requests.post(
            'https://api.groq.com/openai/v1/chat/completions',
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
            json={
                'model': 'llama-3.3-70b-versatile',
                'messages': [
                    {'role': 'system', 'content': _SYSTEM},
                    {'role': 'user',   'content': body},
                ],
                'max_tokens': 600,
                'temperature': 0.2,
            },
            timeout=20,
        )
        response.raise_for_status()
        return response.json()['choices'][0]['message']['content'].strip()
    except Exception as exc:
        logger.error('AI chat failed: %s', exc)
        return (
            'The AI Programme Officer is temporarily unavailable. '
            'Please check programme data directly in the dashboard.'
        )
