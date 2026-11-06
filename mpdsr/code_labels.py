"""Canonical code to label decoding for the CIPRB indicator breakdowns.

Why this exists
---------------
The MPDSR case model stores whatever string the source form emitted. Three
things then collided on the dashboard:

1. The verbatim CIPRB forms use snake_case choice codes ('vaginal_spontaneous',
   'doctor_mbbs', 'upazila_hc'). Those were rendered raw, so CIPRB and UNFPA
   were reading database field names.
2. An earlier ingest path wrote already-humanised labels for the same concepts
   ('C-section', 'Home', 'Live birth', 'normal'). The same clinical fact
   therefore appears under two keys and is counted twice.
3. Free-text spelling drift produced phantom categories, most visibly
   'iterogenic' sitting beside 'Iatrogenic' as separate slices.

The fix is one normalisation layer applied at the aggregate, so every consumer
(dashboard, monthly report, export) gets the same clean vocabulary.

Source of truth
---------------
The canonical codes and English labels are the choice lists in
programs/management/commands/build_ciprb_forms.py, which is what built the
deployed forms. That module imports openpyxl, which is not installed in
production, so the vocabulary is mirrored here as plain data rather than
imported. test_code_labels.py asserts this mirror still covers every choice the
builder emits, so the two cannot drift apart silently.
"""

import re

UNKNOWN = 'Unknown'

# Values that mean "no answer" whatever the field. '99' is the forms' own
# not-known sentinel (see the anc_count list: 'Unknown (99)').
_NULLISH = {'', 'na', 'n a', 'none given', 'not known', 'unknown', '99', '999'}


def _norm(value):
    """Fold a raw stored value to a comparison key.

    Lowercase, strip, and flatten every separator so that 'C-section',
    'c_section' and 'C Section' all land on the same key.
    """
    s = str(value or '').strip().lower()
    s = re.sub(r'[\s_\-/]+', ' ', s)
    return s.strip()


# Each entry maps normalised input -> canonical English label. Both the form
# code and every legacy label variant seen in production point at one label, so
# duplicates merge instead of splitting the chart.
_MAPS = {
    'place_of_death': {
        'home': 'Home',
        'community clinic': 'Community Clinic',
        'union hfwc': 'Union Health & Family Welfare Centre',
        'upazila hc': 'Upazila Health Complex',
        'maternal centre': 'Maternal & Child Welfare Centre',
        'district hospital': 'District / Sadar hospital',
        'medical college': 'Medical College hospital',
        'private clinic': 'Private clinic / hospital',
        'ngo clinic': 'NGO clinic',
        'provider home': "Provider's chamber / home",
        'facility': 'Health facility',
        'health facility': 'Health facility',
        'in transit': 'In transit',
        'on the way': 'In transit',
        'transit': 'In transit',
        'other': 'Other',
    },
    'mode_of_delivery': {
        'vaginal spontaneous': 'Vaginal (spontaneous)',
        'normal': 'Vaginal (spontaneous)',
        'nvd': 'Vaginal (spontaneous)',
        'spontaneous': 'Vaginal (spontaneous)',
        'vaginal': 'Vaginal (spontaneous)',
        # F-01 spells it 'instrumental_vaginal', F-04 just 'instrumental'.
        'instrumental vaginal': 'Instrumental vaginal',
        'instrumental': 'Instrumental vaginal',
        'assisted vaginal': 'Instrumental vaginal',
        'csection': 'Caesarean section',
        'c section': 'Caesarean section',
        'caesarean section': 'Caesarean section',
        'destructive': 'Destructive operation',
        'not delivered': 'Not delivered',
        'undelivered': 'Not delivered',
    },
    'delivery_outcome': {
        'livebirth': 'Live birth',
        'live birth': 'Live birth',
        'stillbirth': 'Stillbirth',
        'still birth': 'Stillbirth',
        'abortion': 'Abortion',
        'not delivered': 'Not delivered',
        'undelivered': 'Not delivered',
        'na': 'Not delivered',
        'low birth weight': 'Live birth (low birth weight)',
        'other': 'Other',
    },
    'place_of_delivery': {
        'home': 'Home',
        'community clinic': 'Community Clinic',
        'union hfwc': 'Union Health & Family Welfare Centre',
        'upazila hc': 'Upazila Health Complex',
        'maternal centre': 'Maternal & Child Welfare Centre',
        'district hospital': 'District / Sadar hospital',
        'medical college': 'Medical College hospital',
        'private clinic': 'Private clinic / hospital',
        'private facility': 'Private clinic / hospital',
        'ngo clinic': 'NGO clinic',
        'provider home': "Provider's chamber / home",
        'gov facility': 'Government facility',
        'govt facility': 'Government facility',
        'in transit': 'In transit',
        'other': 'Other',
    },
    'person_assisted_delivery': {
        'doctor mbbs': 'Doctor (MBBS)',
        'doctor': 'Doctor (MBBS)',
        'nurse': 'Nurse',
        'fwv': 'Family Welfare Visitor (FWV)',
        'csba': 'CSBA',
        'ma': 'Medical Assistant (MA)',
        'ha': 'Health Assistant (HA)',
        'fwa': 'Family Welfare Assistant (FWA)',
        'dai': 'Dai (TBA)',
        'tba': 'Dai (TBA)',
        'palli chikitsok': 'Palli chikitsok (village doctor)',
        'ngo worker': 'NGO worker',
        'midwife': 'Midwife',
        'relatives': 'Relatives',
        'self': 'Self',
        'other': 'Other',
    },
    'anc_visits_count': {
        '0': 'None',
        'none': 'None',
        '1': '1 visit',
        '2': '2 visits',
        '3': '3 visits',
        '4': '4 or more',
        '4 plus': '4 or more',
    },
    # Fistula. 'iterogenic' is a misspelling that was rendering as its own
    # slice next to the correctly spelled value.
    'fistula_type': {
        'obstetric': 'Obstetric',
        'iatrogenic': 'Iatrogenic',
        'iterogenic': 'Iatrogenic',
        'iatrogenic fistula': 'Iatrogenic',
        'obstetric fistula': 'Obstetric',
        'congenital': 'Congenital',
        'traumatic': 'Traumatic',
        'tr': 'Traumatic',
    },
    'genital_fistula_type': {
        'vvf': 'Vesico-vaginal (VVF)',
        'rvf': 'Recto-vaginal (RVF)',
        'uvf': 'Urethro-vaginal (UVF)',
        'tr': 'Traumatic',
        'iatrogenic': 'Iatrogenic',
        'iterogenic': 'Iatrogenic',
        'uretero vaginal': 'Uretero-vaginal',
        'vesico uterine': 'Vesico-uterine',
        'vesico cervical': 'Vesico-cervical',
    },
}


def decode(field, raw):
    """Return the display label for one stored value.

    Unmapped values are title-cased rather than dropped, so a new choice added
    to a form still reads sensibly instead of vanishing from the chart.
    """
    key = _norm(raw)
    if key in _NULLISH:
        return UNKNOWN
    mapping = _MAPS.get(field)
    if mapping and key in mapping:
        return mapping[key]
    return str(raw).replace('_', ' ').strip().capitalize() or UNKNOWN


# ── Canonical CODES (not labels) ───────────────────────────────────────────
# The fistula charts are keyed on the raw form codes: PIE_COLORS maps
# 'obstetric' to a colour and GENITAL_TYPES lists 'vvf'/'rvf' to fix the bar
# order, and FistulaIndicators has its own label map on the same codes.
# Relabelling those to English server-side emptied both Fistula Corner charts,
# because every one of those lookups missed. So for fistula the merge has to
# land on a canonical CODE and leave presentation to the frontend.
_CANON = {
    'fistula_type': {
        'obstetric': 'obstetric', 'obstetric fistula': 'obstetric',
        'iatrogenic': 'iatrogenic', 'iterogenic': 'iatrogenic',
        'iatrogenic fistula': 'iatrogenic',
        'congenital': 'congenital',
        'traumatic': 'traumatic', 'tr': 'traumatic',
    },
    'genital_fistula_type': {
        'vvf': 'vvf', 'vesicovaginal': 'vvf', 'vesico vaginal': 'vvf',
        'rvf': 'rvf', 'rectovaginal': 'rvf', 'recto vaginal': 'rvf',
        'uvf': 'urethrovaginal', 'urethrovaginal': 'urethrovaginal',
        'urethro vaginal': 'urethrovaginal',
        'ureterovaginal': 'ureterovaginal', 'uretero vaginal': 'ureterovaginal',
        'vesicouterine': 'vesicouterine', 'vesico uterine': 'vesicouterine',
        'vesicocervical': 'vesicocervical', 'vesico cervical': 'vesicocervical',
        # Neither is an anatomical type. Both appear in this field in
        # production; keep them visible under one spelling instead of two.
        'tr': 'traumatic', 'traumatic': 'traumatic',
        'iatrogenic': 'iatrogenic', 'iterogenic': 'iatrogenic',
    },
}


def canonicalise(field, counts):
    """Merge spelling variants onto one canonical CODE, preserving codes.

    Same duplicate-killing job as relabel(), but the output stays machine
    readable so code-keyed charts keep working.
    """
    mapping = _CANON.get(field, {})
    out = {}
    for raw, n in (counts or {}).items():
        key = _norm(raw)
        code = mapping.get(key, key.replace(' ', '_')) if key else 'unknown'
        out[code] = out.get(code, 0) + n
    return out


# Fields the dashboard renders in a fixed sequence rather than by size. The
# aggregate must emit them in that sequence, because the chart preserves
# insertion order and a Counter's order is arbitrary.
_ORDER = {
    'anc_visits_count': ['None', '1 visit', '2 visits', '3 visits',
                         '4 or more', UNKNOWN],
}


def relabel(field, counts):
    """Decode and MERGE a {raw_value: n} breakdown into {label: n}.

    Merging is the point: 'normal' and 'vaginal_spontaneous' are one clinical
    fact and must add up, not sit as two slices.
    """
    out = {}
    for raw, n in (counts or {}).items():
        label = decode(field, raw)
        out[label] = out.get(label, 0) + n
    order = _ORDER.get(field)
    if order:
        ranked = {k: out[k] for k in order if k in out}
        # Anything outside the canonical sequence still gets shown, after it.
        ranked.update({k: v for k, v in out.items() if k not in ranked})
        return ranked
    return out


# ── Time of death ──────────────────────────────────────────────────────────
# The model comment says this field holds antepartum/intrapartum/postpartum,
# but the verbatim forms ask for the CLOCK TIME of death, so that is what is
# stored. Rendering it raw produced 46 individual timestamps at 2% each, which
# is not an indicator. Bin into six four-hour periods.
_TOD_BANDS = [
    (0, 4, '00:00-03:59'), (4, 8, '04:00-07:59'), (8, 12, '08:00-11:59'),
    (12, 16, '12:00-15:59'), (16, 20, '16:00-19:59'), (20, 24, '20:00-23:59'),
]


def band_time_of_death(counts):
    """{'11:30:00.000+06:00': 1, ...} -> {'08:00-11:59': 1, ...}."""
    out = {lbl: 0 for _, _, lbl in _TOD_BANDS}
    out[UNKNOWN] = 0
    for raw, n in (counts or {}).items():
        m = re.match(r'\s*(\d{1,2})\s*:', str(raw or ''))
        if not m:
            out[UNKNOWN] += n
            continue
        hour = int(m.group(1))
        if not 0 <= hour <= 23:
            out[UNKNOWN] += n
            continue
        for lo, hi, lbl in _TOD_BANDS:
            if lo <= hour < hi:
                out[lbl] += n
                break
    return out


# ── Postnatal care ─────────────────────────────────────────────────────────
# pnc_received holds a VISIT COUNT, not a yes/no. It was being rendered by a
# yes/no stat tile, which is why the headline read "Received: 0 of 22" while
# the breakdown underneath showed 19 women with at least one visit. 99 is the
# forms' not-known sentinel. Anything above _PNC_MAX is a data-entry error
# (production holds a 24); it is folded into Unknown so it is never charted
# as real visits, without printing "Invalid entry" on a public panel
# (Rafi, 3 Aug 2026).
_PNC_MAX = 10


def band_pnc(counts):
    """{'0': 3, '1': 10, '99': 1, '24': 1} -> banded, with errors called out."""
    out = {'None': 0, '1 visit': 0, '2 visits': 0, '3 visits': 0,
           '4 or more': 0, UNKNOWN: 0}
    for raw, n in (counts or {}).items():
        key = _norm(raw)
        if key in _NULLISH:
            out[UNKNOWN] += n
            continue
        try:
            v = int(float(key))
        except (TypeError, ValueError):
            out[UNKNOWN] += n
            continue
        if v < 0 or v > _PNC_MAX:
            out[UNKNOWN] += n
        elif v == 0:
            out['None'] += n
        elif v == 1:
            out['1 visit'] += n
        elif v == 2:
            out['2 visits'] += n
        elif v == 3:
            out['3 visits'] += n
        else:
            out['4 or more'] += n
    return out
