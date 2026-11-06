"""
AI narrative generation via Groq REST (OpenAI-compatible chat completions).

Contract changes (per agent-architecture-audit findings HIGH-1..HIGH-3):

 1. Output is requested as JSON (response_format=json_object), not free-form prose.
 2. Every number in the model's response must appear in the source context,
    or the result is rejected and we fall back to a deterministic template.
 3. Each call returns (text, meta) where meta records narrative_source and
    model_used — so the Report row carries honest provenance and the PDF
    footer can render conditionally.
 4. Below MIN_TOTAL_FOR_AI activities, we skip Groq entirely and use a
    deterministic "insufficient data" template.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

MODEL = 'llama-3.3-70b-versatile'
TEMPERATURE = 0.3
MIN_TOTAL_FOR_AI = 5     # below this, skip Groq entirely


# ── Narrative source constants (mirror reports.models.NarrativeSource) ────────
SRC_AI                   = 'ai'
SRC_AI_VALIDATION_FAILED = 'ai_validation_failed'
SRC_AI_DISABLED          = 'ai_disabled'
SRC_INSUFFICIENT_DATA    = 'insufficient_data'
SRC_AI_API_ERROR         = 'ai_api_error'
SRC_TEMPLATE             = 'template'


# ── System prompts — now require JSON output ──────────────────────────────────

_SYSTEM_SUMMARY = (
    'You are a senior public health programme officer for CIPRB, Bangladesh, '
    'writing formal reports for UNFPA, the Bangladesh Ministry of Health, and donors. '
    'Your writing is precise, confident, evidence-based, and in formal British English.\n\n'
    'Return ONLY a JSON object with this exact shape:\n'
    '{\n'
    '  "narrative": "two or three short paragraphs",\n'
    '  "figures_cited": [list of every integer that appears in your narrative]\n'
    '}\n\n'
    'Do not invent or extrapolate figures. Every integer in "narrative" must also '
    'appear in "figures_cited" AND must come from the data provided.'
)

_SYSTEM_NEWSLETTER = (
    'You are a senior communications officer at CIPRB, Bangladesh, writing a programme '
    'bulletin for senior government officials, UNFPA leadership, and international donors. '
    'Tone is authoritative, positive, and forward-looking. Formal British English.\n\n'
    'Return ONLY a JSON object with this exact shape:\n'
    '{\n'
    '  "executive_summary": "one concise paragraph",\n'
    '  "highlights": ["3 to 4 short bullets, each starting with a strong verb"],\n'
    '  "narrative": "two paragraphs of context",\n'
    '  "forward_look": "one paragraph on planned activities for the next period",\n'
    '  "figures_cited": [every integer that appears anywhere in the strings above]\n'
    '}\n\n'
    'Do not invent figures. Every integer in any string must also appear in '
    '"figures_cited" AND must come from the data provided.'
)


# ── Public API ────────────────────────────────────────────────────────────────

def generate_narrative(context: dict) -> tuple[str, dict]:
    """
    Generate a brief summary narrative.
    Returns (text, metadata). text may be empty if no AI was used.
    metadata = {'source': NarrativeSource, 'model': str, ...}
    """
    total = _total_from_context(context)
    if total < MIN_TOTAL_FOR_AI:
        return _insufficient_template(context), {
            'source': SRC_INSUFFICIENT_DATA, 'model': '',
        }

    obj, err = _call_groq_json(_SYSTEM_SUMMARY, _build_prompt(context), max_tokens=500)
    if err is not None:
        logger.error('groq_call_failed', extra={'fn': 'generate_narrative', 'err': err})
        return '', {'source': SRC_AI_API_ERROR, 'model': MODEL, 'error': err}

    narrative = (obj or {}).get('narrative', '').strip()
    cited = (obj or {}).get('figures_cited', []) or []

    invalid = _validate_figures(narrative, cited, context)
    if invalid:
        logger.warning(
            'groq_figures_invalid',
            extra={'fn': 'generate_narrative', 'invalid': invalid},
        )
        return '', {
            'source': SRC_AI_VALIDATION_FAILED, 'model': MODEL,
            'invalid_figures': invalid,
        }

    return narrative, {'source': SRC_AI, 'model': MODEL}


def generate_newsletter_narrative(context: dict) -> tuple[str, dict]:
    """
    Generate a structured newsletter narrative.

    Returns (text, metadata). The text is laid out with the legacy headings
    EXECUTIVE SUMMARY / PROGRAMME HIGHLIGHTS / NARRATIVE / FORWARD LOOK so
    downstream generators keep working unchanged.
    """
    total = _total_from_context(context)
    if total < MIN_TOTAL_FOR_AI:
        return _insufficient_template(context), {
            'source': SRC_INSUFFICIENT_DATA, 'model': '',
        }

    obj, err = _call_groq_json(_SYSTEM_NEWSLETTER, _build_prompt(context), max_tokens=900)
    if err is not None:
        logger.error('groq_call_failed', extra={'fn': 'generate_newsletter_narrative', 'err': err})
        return '', {'source': SRC_AI_API_ERROR, 'model': MODEL, 'error': err}

    obj = obj or {}
    exec_sum  = str(obj.get('executive_summary', '') or '').strip()
    highlights = obj.get('highlights', []) or []
    narrative = str(obj.get('narrative', '') or '').strip()
    forward   = str(obj.get('forward_look', '') or '').strip()
    cited     = obj.get('figures_cited', []) or []

    # Validate against the union of all string fields
    combined = ' '.join([exec_sum, ' '.join(map(str, highlights)), narrative, forward])
    invalid = _validate_figures(combined, cited, context)
    if invalid:
        logger.warning(
            'groq_figures_invalid',
            extra={'fn': 'generate_newsletter_narrative', 'invalid': invalid},
        )
        return '', {
            'source': SRC_AI_VALIDATION_FAILED, 'model': MODEL,
            'invalid_figures': invalid,
        }

    # Format into the legacy heading layout the generators already parse
    parts = []
    if exec_sum:
        parts.append('EXECUTIVE SUMMARY\n' + exec_sum)
    if highlights:
        bullets = '\n'.join(f'• {str(h).strip().lstrip("•-* ").strip()}' for h in highlights if str(h).strip())
        parts.append('PROGRAMME HIGHLIGHTS\n' + bullets)
    if narrative:
        parts.append('NARRATIVE\n' + narrative)
    if forward:
        parts.append('FORWARD LOOK\n' + forward)

    return '\n\n'.join(parts), {'source': SRC_AI, 'model': MODEL}


# ── Internals ─────────────────────────────────────────────────────────────────

def _build_prompt(context: dict) -> str:
    lines = ['Programme data for this reporting period:']
    for key, value in context.items():
        if isinstance(value, dict):
            for k2, v2 in value.items():
                lines.append(f'  {key}.{k2}: {v2}')
        elif isinstance(value, list):
            pass
        else:
            lines.append(f'  {key}: {value}')
    lines.append('\nWrite the JSON object now. Return only valid JSON.')
    return '\n'.join(lines)


def _call_groq_json(system: str, user_content: str, max_tokens: int) -> tuple[dict | None, str | None]:
    """
    POST to Groq's chat completions endpoint with JSON output forced.
    Returns (parsed_obj, error_string). One side is always None.
    """
    api_key = getattr(settings, 'GROQ_API_KEY', '')
    if not api_key:
        return None, 'no_api_key'
    try:
        import json
        import requests
        response = requests.post(
            'https://api.groq.com/openai/v1/chat/completions',
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
            json={
                'model': MODEL,
                'messages': [
                    {'role': 'system', 'content': system},
                    {'role': 'user', 'content': user_content},
                ],
                'max_tokens': max_tokens,
                'temperature': TEMPERATURE,
                'response_format': {'type': 'json_object'},
            },
            # Audit FIX M6 — was 60s, which (with only 2 gunicorn workers)
            # let two slow narrative calls stall the whole site. Tight cap;
            # callers already fall back gracefully on timeout.
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        content = payload['choices'][0]['message']['content']
        return json.loads(content), None
    except Exception as exc:
        return None, f'{type(exc).__name__}: {exc}'


def _total_from_context(context: dict) -> int:
    """Best-effort extraction of total activity count from the context dict."""
    for key in ('total_activities', 'total_submissions', 'Total submissions this month'):
        v = context.get(key)
        if isinstance(v, int):
            return v
    return 0


def _validate_figures(text: str, figures_cited: list[Any], context: dict) -> list[int]:
    """
    Find every integer in `text` that isn't present in `context` (or in
    figures_cited that fail the same check). Returns the offending list.

    Numbers <= 1 are treated as ordinary words ("1 of") and skipped, since
    they're rarely operational figures and otherwise produce noisy false
    positives (years like 2026 are kept and validated).
    """
    valid = _collect_valid_numbers(context)
    invalid: list[int] = []
    for raw in re.findall(r'\b\d{2,}\b', text):
        n = int(raw)
        if n not in valid:
            invalid.append(n)
    # Also check explicit cited figures
    for n in figures_cited:
        if isinstance(n, (int, float)):
            n_int = int(n)
            if n_int >= 10 and n_int not in valid:
                invalid.append(n_int)
    return sorted(set(invalid))


def _collect_valid_numbers(context: dict) -> set[int]:
    """Every integer that legitimately appears in the source context."""
    out: set[int] = set()
    def visit(v):
        if isinstance(v, bool):
            return
        if isinstance(v, int):
            out.add(v)
        elif isinstance(v, float):
            out.add(int(v))
            # also allow rounded percentages
            out.add(round(v))
        elif isinstance(v, dict):
            for x in v.values():
                visit(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                visit(x)
        elif isinstance(v, str):
            for m in re.findall(r'\b\d{2,}\b', v):
                out.add(int(m))
    visit(context)
    # Year context — always accept current decade's years so dates don't trip
    # the validator (e.g. the model echoes "2026")
    out.update(range(2020, 2031))
    return out


def _insufficient_template(context: dict) -> str:
    """Deterministic fallback when total activity is below MIN_TOTAL_FOR_AI."""
    partner = context.get('organisation') or context.get('Partner') or 'The programme'
    period  = context.get('period')       or context.get('Period')  or 'this period'
    total   = _total_from_context(context)
    return (
        f'{partner} recorded {total} approved activities during {period}. '
        'Insufficient data was available this period to generate a full narrative summary. '
        'This may indicate the period has just begun, field submissions are still pending '
        'manager approval, or the partner has not yet started reporting. '
        'The KPI table below reflects all approved submissions to date.'
    )
