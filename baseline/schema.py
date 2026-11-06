"""Baseline form schema — turns coded Kobo answers into readable question/answer
text for the verification card and the insights aggregation.

`form_schema.json` is a trimmed projection of the two deployed key-population
XLSForms (Hijra / FSW): per population it holds `labels` (field -> question),
`choices` (field -> {code: answer label}) and `sections` (field -> section
title). Rebuild it from a live Kobo dump with the repo's _build_form_schema.py.
"""
import json
import os
from functools import lru_cache

_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), 'form_schema.json')

# Kobo meta / routing / free-text-noise keys never shown in the answer review.
_HIDE_PREFIXES = ('_', 'formhub', 'meta')
_HIDE_EXACT = {
    'organisation', 'population', 'survey_round', 'start_time', 'start', 'end',
    'today', 'deviceid', 'device_id', '__version__', 'instanceID', 'instanceName',
}


@lru_cache(maxsize=1)
def load_schema():
    try:
        with open(_SCHEMA_PATH, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _pop_key(population):
    pop = (population or '').lower()
    return 'fsw' if pop == 'fsw' else 'hijra'


def pop_schema(population):
    return load_schema().get(_pop_key(population), {})


def field_label(population, field):
    """Question text for a field code; falls back to the raw code."""
    return (pop_schema(population).get('labels', {}) or {}).get(field, field)


def value_label(population, field, value):
    """Answer label for a coded value. Handles select_multiple (space-joined
    codes) and passes through free text / numbers unchanged."""
    if value is None:
        return ''
    cmap = (pop_schema(population).get('choices', {}) or {}).get(field)
    text = str(value).strip()
    if not cmap or not text:
        return text
    parts = text.split()
    if len(parts) > 1:  # select_multiple
        labelled = [cmap.get(p, p) for p in parts]
        return ', '.join(labelled)
    return cmap.get(text, text)


def _hidden(key):
    if key in _HIDE_EXACT:
        return True
    return any(key.startswith(p) for p in _HIDE_PREFIXES)


def humanize(population, raw):
    """Full answer set as readable rows, grouped by questionnaire section.

    Returns [{section, field, question, value, answer}] for every answered,
    non-meta field. Sections and rows follow the real questionnaire order (a
    section sorts by its first field's position in the form; rows within a
    section keep form order), so the review reads top-to-bottom like the paper
    instrument.
    """
    schema = pop_schema(population)
    labels = schema.get('labels', {}) or {}
    sections = schema.get('sections', {}) or {}
    idx = {name: i for i, name in enumerate(schema.get('order', []) or [])}
    rows = []
    for key, val in (raw or {}).items():
        if _hidden(key) or val in ('', None, []):
            continue
        rows.append({
            'section': sections.get(key, 'Other'),
            'field': key,
            'question': labels.get(key, key),
            'value': str(val),
            'answer': value_label(population, key, val),
            '_i': idx.get(key, 10 ** 6),
        })
    sec_first = {}
    for r in rows:
        s = r['section']
        sec_first[s] = min(sec_first.get(s, r['_i']), r['_i'])
    rows.sort(key=lambda r: (sec_first.get(r['section'], 10 ** 6), r['_i']))
    for r in rows:
        r.pop('_i', None)
    return rows


def headline(population, raw):
    """The handful of fields worth surfacing on the collapsed verification card.
    Maps a stable set of concepts to each form's differing field codes."""
    pop = _pop_key(population)
    # concept -> (field candidates, in priority order)
    concept_fields = {
        'hijra': {
            'Age': ['s2_age', 'a205_age'],
            'Gender identity': ['a302_gender'],
            'District': ['a201_district', 'district'],
            'Area': ['a204_area'],
            'Religion': ['a206_religion'],
            'Marital status': ['a208_marital'],
            'Education': ['a209_education'],
            'Main occupation': ['b111_main_occupation'],
            'Mobile phone': ['a211_mobile'],
            'Has NID': ['a212_nid'],
        },
        'fsw': {
            'Age': ['s1_age', 'a203'],
            'District': ['district'],
            'Site': ['site_code'],
            'Religion': ['a204'],
            'Marital status': ['a206'],
            'Education': ['a207'],
            'Living children': ['a213'],
            'Mobile phone': ['a208'],
            'Has NID': ['a209'],
        },
    }[pop]
    out = []
    for concept, fields in concept_fields.items():
        for fld in fields:
            if raw.get(fld) not in (None, ''):
                out.append({'label': concept, 'value': value_label(population, fld, raw.get(fld))})
                break
    return out
