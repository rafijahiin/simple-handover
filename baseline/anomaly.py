"""Adapter: run the vendored FSW anomaly engine over our Kobo submissions.

Our `KoboSubmission.raw_data` is nested Kobo JSON keyed by xform FIELD NAMES
(`grp_admin/dc_code`, `b109` as a space-separated code string, a geopoint packed
as "lat lon alt acc"). The engine (see baseline/fsw_rules.py) is written against
flat records where select_multiple answers are split into `Question/Choice`
columns and a few identity fields are resolvable. This module bridges the two:

  * flatten group keys,
  * decode the select_one fields whose rules read the answer as TEXT
    (consent, b103 living arrangement, b105 duration category),
  * expand every select_multiple into `Label/ChoiceLabel` columns so the
    mutually-exclusive / "Other"-without-specify / Q9.5>5 rules can see them,
  * inject the enumerator NAME (from the roster, never the Kobo login),
    the GPS lat/lon/precision (parsed from the geopoint), and a total expenses,
  * pin an EXPLICIT field map (README: lock resolved keys so a wording change
    cannot silently remap a field).

Raw Kobo data is never modified — we build throwaway dicts for the scan.
"""
import logging

from django.core.cache import cache

from submissions.flatten import flatten_group_keys
from submissions.models import FormType, KoboSubmission

from .codes import is_non_answer as codes_is_non_answer
from .collectors import collector_name
from .fsw_rules import FieldMap, build_fsw_engine
from .populations import resolve_population
from .schema import load_schema

logger = logging.getLogger(__name__)

POPULATIONS = ('fsw', 'hijra')
CACHE_SECONDS = 300  # 5 minutes; invalidated on new baseline ingest (see signals)


def _cache_key(population):
    return f'baseline:{population}:anomalies:v1'


# ── Exclusive multiselect options — EXPLICIT per-question configuration ──────
# Keyed by our stable xform field name -> the choice CODES that are exclusive
# for that question. The engine flags only when one of these is selected
# together with a non-exclusive option on the SAME question. Nothing is
# inferred from text: the old generic regex treated "Never share needles or
# syringes" (a correct HIV-knowledge answer) as a 'none' choice and produced
# floods of false conflicts. Deliberately NOT configured: the "Don't know"
# codes (98) — co-selection with partial answers is common respondent
# behaviour, not a data-entry conflict (confirmed by the manual FSW audit).
# Decision rule (from the full-choice-list audit of both forms, 2026-07-12):
#   CONFIGURED — options that CONTRADICT any co-selection: "None"-type answers,
#     awareness questions' "aware of none / don't know any" (naming one right
#     after is a conflict), "Never received such information" + naming a source,
#     "Did not need assistance" + citing an access barrier.
#   NOT configured — "Don't know" on health-KNOWLEDGE lists (q3_2/3/4/10:
#     partial knowledge + DK is common respondent behaviour, per the manual
#     audit) and "Did not know where to go"-style REASONS (legitimately
#     co-selectable with other reasons).
EXCLUSIVE_CHOICE_CODES: dict[str, dict[str, list[str]]] = {
    'fsw': {
        'b109': ['0'],     # other income sources — "None"
        'q2_13': ['98'],   # laws/rulings awareness — "Aware of none"
        'q2_14': ['98'],   # social schemes awareness — "Aware of none"
        'q2_21': ['00'],   # legal assistance — "No such need arose"
        'q3_13': ['11'],   # SRH info sources — "Never received such information"
        'q8_4': ['0'],     # stress events — "None of the above"
        'q9_6': ['10'],    # Wellness Centre concerns — "No concerns"
    },
    'hijra': {
        'q2_12': ['98'],        # policy/law names — "Don't know any" (aware of none)
        # q2_13/q2_15 carry TWO negatives each: "Don't know anything about this"
        # AND an absence assertion ("No such policy exists" / "No shelter
        # benefits for our community"). Both are exclusive, so a respondent
        # hedging between the two negatives is NOT flagged (exclusive+exclusive
        # has no non-exclusive co-selection); either negative + a POSITIVE
        # benefit is a genuine conflict.
        'q2_13': ['98', '3'],   # employment benefits — DK / "No such policy exists"
        'q2_15': ['98', '2'],   # shelter benefits — DK / "No shelter benefits…"
        'q2_21': ['00'],        # legal assistance — "Did not need such assistance"
        'q3_11': ['12'],        # SRH info sources — "Never received such information"
        'q9_6': ['08'],         # Wellness Centre concerns — "No concerns"
    },
}


def _exclusive_label_map(schema, population):
    """EXCLUSIVE_CHOICE_CODES (field name + codes) -> the engine's shape
    ({sanitized parent LABEL -> set of sanitized choice LABELS}), resolved
    through the same schema the record shaper uses so the two can't drift."""
    labels = schema.get('labels', {})
    choices = schema.get('choices', {})
    out = {}
    for field, codes in EXCLUSIVE_CHOICE_CODES.get(population, {}).items():
        parent = _san(labels.get(field, field))
        cmap = choices.get(field, {})
        opts = {_san(cmap[c]) for c in codes if c in cmap}
        if opts:
            out[parent] = opts
        else:
            logger.warning('exclusive-option config: %s/%s has no matching choices '
                           '— check EXCLUSIVE_CHOICE_CODES against the form',
                           population, field)
    return out


# Minimum plausible interview length. CIPRB's rule: under 40 minutes is rushed —
# one line for both instruments. Do not "helpfully" split this per population.
SHORT_MINUTES = {'hijra': 40, 'fsw': 40}


# Monthly expense is split across these category fields (FSW); the engine wants a
# total. These are the SIX the deployed FSW form actually asks (B110: rent,
# sardarni commission, broker, fees, debt, family) — b110_food/other/children/
# health were in this tuple but exist on NEITHER form, so they had never matched
# anything. Hijra asks a single pre-totalled figure instead (b105_shared_exp),
# pinned directly in its field map.
_EXPENSE_FIELDS = ('b110_broker', 'b110_commission', 'b110_debt',
                   'b110_family', 'b110_fees', 'b110_rent')


def _san(label):
    """The engine uses '/' as the Question/Choice separator, but Kobo choice and
    question labels contain slashes ("Small business/trade", "Hepatitis B/C").
    Neutralise them so a group isn't fragmented at the wrong slash. Must be applied
    identically wherever a label becomes part of a column key (see _fsw_field_map)."""
    return str(label).replace('/', '-')


def _num(v):
    try:
        return float(str(v).replace(',', '').strip())
    except (TypeError, ValueError):
        return None


def _parse_geopoint(value):
    """Kobo packs a geopoint as "lat lon altitude accuracy". Return
    (lat, lon, accuracy_m) or (None, None, None)."""
    if not value:
        return None, None, None
    parts = str(value).split()
    if len(parts) < 2:
        return None, None, None
    lat, lon = _num(parts[0]), _num(parts[1])
    acc = _num(parts[3]) if len(parts) >= 4 else None
    return lat, lon, acc


def _shape_record(sub, schema, population, decode_fields):
    """One KoboSubmission -> a flat dict the engine understands. Pure; the
    submission's raw_data is left untouched. `decode_fields` are the select_one
    fields whose rule logic reads the answer as free text (consent, living
    arrangement, duration category) — those are decoded to their label."""
    raw = flatten_group_keys(sub.raw_data or {})
    labels = schema.get('labels', {})
    choices = schema.get('choices', {})
    types = schema.get('types', {})

    rec = {}
    for field, value in raw.items():
        t = str(types.get(field, ''))
        if t.startswith('select_multiple'):
            # Expand "1 3" -> {"<label>/<choice1>": "1", "<label>/<choice3>": "1"}.
            parent = _san(labels.get(field, field))
            cmap = choices.get(field, {})
            for code in str(value).split() if value not in (None, '') else []:
                rec[f'{parent}/{_san(cmap.get(str(code), code))}'] = '1'
        elif t.startswith('select_one') and field in decode_fields:
            rec[field] = choices.get(field, {}).get(str(value), value)
        else:
            rec[field] = value

    # Identity + metadata the engine resolves by exact key.
    dc = raw.get('dc_code')
    rec['_uuid'] = raw.get('_uuid') or raw.get('submission_id') or str(sub.id)
    rec['__version__'] = raw.get('__version__') or ''
    rec['site_code'] = raw.get('site_code') or ''
    rec['enumerator_name'] = (
        collector_name(population, dc)
        or (f'Collector {dc}' if dc not in (None, '') else 'Unknown')
    )

    # GPS from the geopoint, falling back to the parsed model columns.
    lat, lon, acc = _parse_geopoint(raw.get('location') or raw.get('geopoint')
                                    or raw.get('gps'))
    if lat is None and sub.latitude is not None and sub.longitude is not None:
        lat, lon = float(sub.latitude), float(sub.longitude)
    rec['latitude'], rec['longitude'] = lat, lon
    if acc is not None:
        rec['gps_precision'] = acc

    # Total monthly expenses across the category fields (only if any present).
    exp = [x for x in (_num(raw.get(f)) for f in _EXPENSE_FIELDS) if x is not None]
    if exp:
        rec['expenses_total'] = sum(exp)
    return rec


def _fsw_field_map(schema):
    """Explicit, pinned map from engine roles to the FSW form's field names."""
    b109_label = _san(schema.get('labels', {}).get('b109', 'b109'))
    return FieldMap(
        record_id='_uuid',
        enumerator='enumerator_name',
        site='site_code',
        version='__version__',
        consent='consent',
        interview_start='interview_start',
        interview_end='interview_end_actual',     # the in-form end stamp only
        age_screening='s1_age',
        age_demographic='a203',
        children_total='a213',
        children_with_respondent='a214',
        children_other_location='a215',
        living_arrangement='b103',
        sex_work_start_age='b104',
        sex_work_years='b105',
        sex_work_income='b108',
        other_income_none=f'{b109_label}/None',
        expenses_total='expenses_total',
        latitude='latitude',
        longitude='longitude',
        gps_precision='gps_precision',
        observation=None,                          # FSW form has no observation field
        headers=(),                                # filled by build_fsw_engine
    )


def _hijra_field_map(schema):
    """The Hijra instrument is structured differently (gender-diverse, not
    sex-work-by-brothel), so the sex-work / living-children fields do not exist;
    those FieldMap roles are None and their rules skip. The population-agnostic
    checks — consent, timing, form version, age (screening vs demographic), GPS,
    duplicates, burst, select-multiple, income, and the free-text observation —
    all apply, and cover the same data-quality risks (esp. missing in-form end
    times on an outdated form)."""
    return FieldMap(
        record_id='_uuid',
        enumerator='enumerator_name',
        site='site_code',
        version='__version__',
        consent='consent',
        interview_start='interview_start',
        interview_end='interview_end_actual',
        age_screening='s2_age',
        age_demographic='a205_age',
        children_total=None,
        children_with_respondent=None,
        children_other_location=None,
        living_arrangement='b101_live_with',
        sex_work_start_age=None,
        sex_work_years=None,
        # B104 is the TYPED gross share, which is where a missing zero can occur —
        # the published indicators deliberately read B106/B107 instead, via
        # baseline/income.py. Do not "fix" this to B106: a calculate cannot be
        # mistyped, so pointing the rule at it would detect nothing.
        sex_work_income='b104_share',              # monthly money received
        other_income_none=None,
        # Was pinned to 'expenses_total' — a key _shape_record only builds from the
        # FSW b110_* block, so it never existed on a Hijra record and the rule was
        # silently dead while the console displayed the role as resolved. Hijra asks
        # one pre-totalled figure (dera branch only, so ~42 records).
        expenses_total='b105_shared_exp',
        latitude='latitude',
        longitude='longitude',
        gps_precision='gps_precision',
        observation='c2',                          # free-text interviewer observation
        headers=(),
    )


FIELD_MAP_BUILDERS = {'fsw': _fsw_field_map, 'hijra': _hijra_field_map}


def _decode_fields(field_map):
    """The select_one fields the engine reads as free text — decode these to
    labels so 'alone' / 'more than 10 years' / 'No' match."""
    return {f for f in (field_map.consent, field_map.living_arrangement,
                        field_map.sex_work_years) if f}


def _submissions(population):
    qs = KoboSubmission.objects.filter(form_type=FormType.BASELINE)
    return [s for s in qs if resolve_population(flatten_group_keys(s.raw_data or {}),
                                                default='') == population]


def _current_version(records):
    """The live form version = the one INTRODUCED most recently, i.e. whose first
    submission is the latest.

    It used to be a majority vote, which inverts the rule the moment a new form is
    deployed: the newest version starts with the fewest submissions, so the version
    everyone should be leaving wins the vote and the enumerators who already updated
    get flagged as 'old form version'. Live proof on 2026-07-17: two Hijra records
    were already on the deployed form and both were flagged, while 283 on an older
    form were treated as current. Telling the field team to re-download makes this
    worse every day, because compliance looks like the anomaly.

    Deploys are monotonic — a version cannot be introduced before the one it
    replaced — so the newest first-seen submission identifies the live form without
    an outbound call to Kobo. A straggler who submits on an old form today does not
    move that version's FIRST-seen timestamp, so it cannot reclaim 'current'. When
    nobody has submitted on a newly deployed form yet, the previous version stays
    current and nobody is flagged — conservative, and it self-corrects on the first
    submission from an updated device.
    """
    first_seen = {}
    counts = {}
    for r in records:
        v = r.get('__version__')
        if not v:
            continue
        counts[v] = counts.get(v, 0) + 1
        t = str(r.get('_submission_time') or '')
        if t and (v not in first_seen or t < first_seen[v]):
            first_seen[v] = t
    if not counts:
        return None
    dated = [v for v in counts if v in first_seen]
    if not dated:
        # No usable timestamps — fall back to the majority rather than nothing.
        return max(counts, key=lambda v: counts[v])
    return max(dated, key=lambda v: (first_seen[v], counts[v]))


def non_answer_policy(population):
    """The engine's `is_non_answer(field, value)` hook, bound to this population.

    baseline/codes.py is the single source of truth for which numeric questions
    declare a code, and it is guarded against the live form labels by
    test_non_answer_codes_match_the_live_forms. The engine used to keep a private,
    field-blind REFUSAL_CODES = {98, 99} that contradicted it.
    """
    def is_non_answer(field, value):
        return bool(field) and codes_is_non_answer(population, field, value)
    return is_non_answer


def dead_pins(field_map, headers):
    """Pinned roles whose column does not exist on the shaped record.

    A FieldMap role can fail in two ways. An UNRESOLVED role (None) is visible —
    the console prints null. A DEAD PIN is not: the role names a column that is
    never built, every rule that reads it quietly skips, and `resolved_fields`
    displays the name as though it were working. Hijra's expenses_total was pinned
    to 'expenses_total', a key _shape_record only ever builds from the FSW b110_*
    block, so the expense check did nothing for 370 interviews and looked healthy
    while doing it. That is the most dangerous failure shape in the map, so it is
    now surfaced in the report and asserted in the tests.
    """
    hs = set(headers)
    return sorted(role for role, col in field_map.__dict__.items()
                  if role != 'headers' and col and col not in hs)


def build_report(population='fsw', *, force=False):
    """Scan every submission of `population` and return the engine report
    (cached 5 min). Adds `population`, `current_version`, and `resolved_fields`."""
    if population not in FIELD_MAP_BUILDERS:
        raise ValueError(f'unknown population {population!r}')
    key = _cache_key(population)
    if not force:
        cached = cache.get(key)
        if cached is not None:
            return cached

    schema = load_schema().get(population, {})
    field_map = FIELD_MAP_BUILDERS[population](schema)
    decode = _decode_fields(field_map)
    records = [_shape_record(s, schema, population, decode)
               for s in _submissions(population)]
    headers = sorted({k for r in records for k in r})
    current_version = _current_version(records)

    engine, field_map = build_fsw_engine(
        headers,
        field_map=field_map,
        exclusive_options=_exclusive_label_map(schema, population),
        short_minutes=SHORT_MINUTES.get(population, 40),
        is_non_answer=non_answer_policy(population),
    )
    report = engine.scan(records)
    report['population'] = population
    report['current_version'] = current_version
    report['resolved_fields'] = {k: v for k, v in field_map.__dict__.items()
                                 if k != 'headers'}
    report['dead_pins'] = dead_pins(field_map, headers)
    if report['dead_pins']:
        logger.warning(
            '%s: field-map roles pinned to columns that do not exist — every rule '
            'reading them is silently dead: %s', population, report['dead_pins'])
    # Lightweight per-record index so the API can filter flags AND the scanned
    # denominator by the same record-scoped criteria (enumerator/site/date/version).
    report['records_index'] = [{
        'record_id': r.get('_uuid'),
        'population': population,
        'enumerator': r.get('enumerator_name'),
        'site': str(r.get('site_code') or ''),
        'version': r.get('__version__') or '',
        'date': str(r.get('interview_start') or '')[:10],
    } for r in records]

    cache.set(key, report, CACHE_SECONDS)
    return report


def invalidate_cache():
    for population in POPULATIONS:
        cache.delete(_cache_key(population))
