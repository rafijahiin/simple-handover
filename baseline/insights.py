"""Baseline insights — data-driven aggregation over VERIFIED responses.

Reads the full answer set (raw_data) of approved BaselineResponse rows and
returns compact, chart-ready buckets for the /baseline dashboard. Field codes
differ between the two key-population instruments, so every dimension maps its
own (hijra, fsw) candidate fields; coded values are translated to labels via
schema.value_label so the charts read in plain language.
"""
from collections import Counter, defaultdict

from submissions.flatten import flatten_group_keys

from .codes import is_non_answer
from .income import resolve_income
from .populations import resolve_population
from .schema import value_label

# concept -> {population -> [field candidates in priority order]}
_AGE = {'hijra': ['s2_age', 'a205_age'], 'fsw': ['s1_age', 'a203']}
_DISTRICT = {'hijra': ['a201_district', 'district'], 'fsw': ['district']}
_EDUCATION = {'hijra': ['a209_education'], 'fsw': ['a207']}
_MARITAL = {'hijra': ['a208_marital'], 'fsw': ['a206']}
_RELIGION = {'hijra': ['a206_religion'], 'fsw': ['a204']}
_NID = {'hijra': ['a212_nid'], 'fsw': ['a209']}
_MOBILE = {'hijra': ['a211_mobile'], 'fsw': ['a208']}
# Income is NOT one question. Hijra asks it on two mutually exclusive branches
# (B101 = who you live with) and they measure different things — B106 is PERSONAL
# income after the dera's shared expenses, B107 is the HOUSEHOLD's earnings — so
# they are banded as separate series, never pooled. The old map read B104: the
# gross share before deductions, which the form does not call income, and which
# only the dera branch is asked (42 of 370). FSW B108 is income FROM SEX WORK,
# not total income — the chart title must say so.
_INCOME = {'hijra': ['b106_personal_income'], 'fsw': ['b108']}
_HH_INCOME = {'hijra': ['b107_total'], 'fsw': []}

AGE_BANDS = [(0, 19, '≤19'), (20, 24, '20–24'), (25, 29, '25–29'),
             (30, 34, '30–34'), (35, 39, '35–39'), (40, 49, '40–49'),
             (50, 200, '50+')]
INCOME_BANDS = [(0, 4999, '<5k'), (5000, 9999, '5k–10k'), (10000, 14999, '10k–15k'),
                (15000, 19999, '15k–20k'), (20000, 29999, '20k–30k'),
                (30000, 10 ** 9, '30k+')]


def _first(raw, fields):
    for f in fields:
        v = raw.get(f)
        if v not in (None, ''):
            return f, v
    return None, None


def _to_int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _band(value, bands):
    for lo, hi, label in bands:
        if lo <= value <= hi:
            return label
    return None


def _labelled_counter(counter, order=None):
    """Counter -> [{name, value}] largest-first (or fixed order)."""
    if order:
        return [{'name': k, 'value': counter.get(k, 0)} for k in order if counter.get(k, 0)]
    return [{'name': k, 'value': v} for k, v in counter.most_common()]


def compute_insights(responses):
    """`responses`: iterable of BaselineResponse. Returns a chart-ready dict."""
    pop_counts = Counter()
    round_counts = Counter()
    district_by_pop = defaultdict(Counter)
    age_band = defaultdict(Counter)
    education = defaultdict(Counter)
    marital = defaultdict(Counter)
    religion = defaultdict(Counter)
    income_band = defaultdict(Counter)
    hh_income_band = defaultdict(Counter)
    ages = defaultdict(list)
    nid_yes = defaultdict(int)
    nid_total = defaultdict(int)
    mobile_yes = defaultdict(int)
    mobile_total = defaultdict(int)
    districts_seen = set()

    for r in responses:
        # Flatten Kobo's 'group/field' keys, and take population from the FORM
        # rather than the stored column (older rows misfiled FSW as Hijra).
        raw = flatten_group_keys(r.raw_data or {})
        pop = resolve_population(raw, default=(r.population or 'hijra'))
        pop_counts[pop] += 1
        round_counts[r.survey_round or 'baseline'] += 1

        # Age — prefer the model column, fall back to raw.
        age = r.age if r.age else _to_int(_first(raw, _AGE.get(pop, []))[1])
        if age:
            ages[pop].append(age)
            band = _band(age, AGE_BANDS)
            if band:
                age_band[pop][band] += 1

        # District — prefer the model column.
        dist = (r.district or '').strip() or _first(raw, _DISTRICT.get(pop, []))[1]
        if dist:
            fld, val = _first(raw, _DISTRICT.get(pop, []))
            label = value_label(pop, fld, dist) if fld else str(dist)
            label = (label or str(dist)).title() if label and label.islower() else label
            district_by_pop[pop][label] += 1
            districts_seen.add(label)

        f_edu, v_edu = _first(raw, _EDUCATION.get(pop, []))
        if v_edu is not None:
            education[pop][value_label(pop, f_edu, v_edu)] += 1
        f_mar, v_mar = _first(raw, _MARITAL.get(pop, []))
        if v_mar is not None:
            marital[pop][value_label(pop, f_mar, v_mar)] += 1
        f_rel, v_rel = _first(raw, _RELIGION.get(pop, []))
        if v_rel is not None:
            religion[pop][value_label(pop, f_rel, v_rel)] += 1

        # Which income question applies depends on the FORM's branch, not on which
        # field happens to hold a value — see baseline/income.py. A refusal
        # ("99 = Prefer not to say" on B108) is a CODE, not taka: banding it counted
        # people who declined as earning under 5k. See baseline/codes.py.
        personal, household = resolve_income(pop, raw)
        for value, bucket, field in ((personal, income_band, _INCOME.get(pop, [''])[0]),
                                     (household, hh_income_band, None)):
            if value is None or value < 0:
                continue
            if field and is_non_answer(pop, field, value):
                continue
            b = _band(value, INCOME_BANDS)
            if b:
                bucket[pop][b] += 1

        f_nid, v_nid = _first(raw, _NID.get(pop, []))
        if v_nid is not None:
            nid_total[pop] += 1
            if str(v_nid).strip() == '1':  # 1 = Yes on both forms
                nid_yes[pop] += 1
        f_mob, v_mob = _first(raw, _MOBILE.get(pop, []))
        if v_mob is not None:
            mobile_total[pop] += 1
            if str(v_mob).strip() in ('1', '2'):  # 1/2 = owns a phone, 3 = No
                mobile_yes[pop] += 1

    def _pct(num, den):
        return round(100 * num / den) if den else None

    def _avg(vals):
        return round(sum(vals) / len(vals), 1) if vals else None

    total = sum(pop_counts.values())
    age_order = [b[2] for b in AGE_BANDS]
    income_order = [b[2] for b in INCOME_BANDS]

    def _dim(counter_by_pop, order=None):
        return {pop: _labelled_counter(counter_by_pop.get(pop, Counter()), order)
                for pop in ('hijra', 'fsw')}

    return {
        'total': total,
        'population': [
            {'name': 'Hijra / Gender-diverse', 'key': 'hijra', 'value': pop_counts.get('hijra', 0)},
            {'name': 'Female Sex Worker', 'key': 'fsw', 'value': pop_counts.get('fsw', 0)},
        ],
        'round': _labelled_counter(round_counts),
        'kpis': {
            pop: {
                'n': pop_counts.get(pop, 0),
                'avg_age': _avg(ages.get(pop, [])),
                'nid_pct': _pct(nid_yes.get(pop, 0), nid_total.get(pop, 0)),
                'mobile_pct': _pct(mobile_yes.get(pop, 0), mobile_total.get(pop, 0)),
            } for pop in ('hijra', 'fsw')
        },
        'districts_count': len(districts_seen),
        'age_band': _dim(age_band, age_order),
        'district': _dim(district_by_pop),
        'education': _dim(education),
        'marital': _dim(marital),
        'religion': _dim(religion),
        'income_band': _dim(income_band, income_order),
        'hh_income_band': _dim(hh_income_band, income_order),
        # Coverage, so a relevance-gated field can never again shrink a published
        # denominator invisibly: B104 was answered by 42 of 370 Hijra and the chart
        # said nothing about the missing 328.
        'income_covered': {
            pop: {'n': sum(income_band.get(pop, Counter()).values()),
                  'hh_n': sum(hh_income_band.get(pop, Counter()).values()),
                  'total': pop_counts.get(pop, 0)}
            for pop in ('hijra', 'fsw')
        },
    }
