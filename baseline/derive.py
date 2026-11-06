"""Single source for the fields BaselineResponse derives from a Kobo payload.

Used by BaselineResponseManager (at INGEST) and by the CSV export (at READ), so an
export can never disagree with the dashboard.

WHY IT EXISTS: rows ingested before the flatten/population fixes stored derived
columns computed from UNFLATTENED raw_data and a GUESSED population — so
`population` said 'hijra' for every FSW interview and district/age/outcome were
blank. Deriving again at read time repairs those rows on the fly, instead of
requiring a bulk UPDATE of production data.

Returns plain strings/ints only — no model imports, so this stays import-safe.
"""
from submissions.flatten import flatten_group_keys

from .populations import resolve_population

# Age is asked under different names per instrument (screening vs module A2).
_AGE_FIELDS = ('s2_age', 's1_age', 'a205_age', 'a203_age', 'a203')


def _safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def derive_fields(raw, fallback_district=''):
    """raw_data (nested or flat) -> the derived BaselineResponse columns.

    `population` is None when the source form cannot be identified — callers
    decide, so nothing is silently mislabelled.
    """
    raw = flatten_group_keys(raw or {})

    age = None
    for f in _AGE_FIELDS:
        age = _safe_int(raw.get(f))
        if age is not None:
            break

    round_raw = str(raw.get('survey_round') or '').lower()

    return {
        'population': resolve_population(raw),
        'survey_round': 'endline' if 'endline' in round_raw else 'baseline',
        # The dedup key. Both live forms collect `submission_id` (collector + area
        # + the moment the form was opened); neither collects questionnaire_serial,
        # which is kept only as a fallback for older payloads. Reading the dead
        # field alone left every row un-deduped and `duplicates` stuck at 0.
        'serial': str(raw.get('submission_id')
                      or raw.get('questionnaire_serial') or '').strip(),
        'district': str(raw.get('district') or fallback_district or '').strip(),
        'site_code': str(raw.get('cluster_site_code') or raw.get('site_code') or '').strip(),
        'age': age,
        'interview_outcome': str(raw.get('c3') or raw.get('interview_outcome') or '').strip(),
    }
