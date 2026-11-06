"""Major SRHR indicators — the module-based analytical summary of the baseline.

Computes the indicator list CIPRB specified (Dashbroad.docx) over VERIFIED
responses, per key population, grouped by questionnaire module. Every indicator
is mapped to the REAL digitised field(s) by content (the paper numbering drifted
in places — e.g. the FSW instrument has no dedicated HIV-testing/counselling
item, so the nearest true measures are reported and labelled honestly).

Conventions
- pct indicators: numerator/denominator over answered rows only; N/A, don't-know
  and refusal codes are excluded from the denominator.
- PHQ-9: sum of q8_3_1..q8_3_9 (0–3 each). Prevalence = score >= 10;
  moderate/severe = >= 15; suicidal ideation = item 9 > 0.
- FIES: count of affirmed items (Hijra c101–c109; FSW b301_a..i occurrence).
  Severe food insecurity = 7+ of 9 affirmed (FIES-standard cutoff).
- Knowledge scores: mean % of items answered correctly ('1' = Yes/correct).
"""
from submissions.flatten import flatten_group_keys

from .income import resolve_income
from .codes import is_non_answer
from .populations import resolve_population

from statistics import median

_SKIP = {'', None, '8', '98', '99', '00'}   # non-substantive codes (per-list overrides below)


def _s(raw, f):
    v = raw.get(f)
    return None if v is None else str(v).strip()


def _int(raw, f):
    try:
        return int(float(raw.get(f)))
    except (TypeError, ValueError):
        return None


class Agg:
    """num/den accumulator -> pct."""
    def __init__(self):
        self.n = 0
        self.d = 0

    def add(self, hit, ok=True):
        if ok:
            self.d += 1
            if hit:
                self.n += 1

    def pct(self):
        return round(100 * self.n / self.d) if self.d else None


# Non-substantive answer codes on the Yes/No grids: 8 = Not applicable,
# 97 = Other (specify), 98 = Don't know, 99 = Decline/Prefer not to say. These are
# EXCLUDED from the denominator — counting them as an implicit "No" would invent a
# negative the respondent never gave (the Hijra Q7.1/Q7.2 batteries gained codes 8
# and 97 on 2026-07-10, which silently deflated GBV prevalence until this).
_GRID_SKIP = ('', None, '8', '97', '98', '99')


def _unmet_legal(raw):
    """(unmet, usable) for Q2.21 "needed legal help but did not seek it — why?".

    '00' ("No such need arose" / "Did not need such assistance") is exclusive: it
    cannot be true alongside a reason for not seeking help. The rule used to be
    "'00' not in the answer", which silently sided with the 00 whenever both were
    ticked — 29 of 319 FSW named a barrier AND ticked 00, and every one of them was
    published as having no unmet need, holding the FSW indicator at 40 where the
    barriers say 69.

    A contradiction is not a value to guess: those records leave the DENOMINATOR
    and are flagged for review instead (MUTUALLY_EXCLUSIVE_MULTISELECT). The FSW
    form now carries the same exclusive constraint Hijra always had, so new
    submissions cannot contain one.
    """
    v = _s(raw, 'q2_21')
    if not v:
        return False, False
    parts = v.split()
    named_barrier = any(p != '00' for p in parts)
    contradictory = '00' in parts and named_barrier
    return named_barrier, not contradictory


def _grid_any(raw, fields, yes='1', skip=_GRID_SKIP):
    """(any_yes, answered_any) over a Yes/No grid."""
    hit = seen = False
    for f in fields:
        v = _s(raw, f)
        if v in skip:
            continue
        seen = True
        if v == yes:
            hit = True
    return hit, seen


def _phq(raw):
    items = [_int(raw, f'q8_3_{i}') for i in range(1, 10)]
    if any(v is None for v in items):
        return None, None
    return sum(items), items[8]


def _fies_count(raw, pop):
    fields = ([f'c10{i}' for i in range(1, 10)] if pop == 'hijra'
              else [f'b301_{c}_occ' for c in 'abcdefghi'])
    vals = [_s(raw, f) for f in fields]
    if all(v in ('', None) for v in vals):
        return None
    return sum(1 for v in vals if v == '1')


HIJRA_GBV = [f'q7_1_{c}' for c in 'abcdefghijk']
FSW_GBV = [f'q7_1_{c}' for c in ('i', 'ii', 'iii', 'iv', 'v', 'vi', 'vii',
                                 'viii', 'ix', 'x', 'xi', 'xii')]
# FSW Q7.1 row groups by violence type — verified against each row's actual
# text, NOT a positional guess: i/ii/iii = physical (slapped/beaten, hit with
# object/burned, weapon threat); iv/v = psychological (humiliated, threatened
# with outing); vi/vii/ix = sexual (forced sex, coerced/non-consensual condom
# removal, coerced via threats/blackmail/debt). viii/x/xi are economic
# (payment withheld, money/property taken, eviction) — deliberately excluded
# from the physical/sexual/psychological split; xii (movement restricted) is
# a distinct confinement item, also excluded from the 3-way split.
FSW_PHYS = [f'q7_1_{c}' for c in ('i', 'ii', 'iii')]
FSW_PSY = [f'q7_1_{c}' for c in ('iv', 'v')]
FSW_SEX = [f'q7_1_{c}' for c in ('vi', 'vii', 'ix')]
# Q7.2 = technology-facilitated violence. Q7.18 ("did you seek help") is asked
# about Q7.1 OR Q7.2, so the help-seeking denominator spans both batteries.
FSW_TFV = [f'q7_2_{c}' for c in ('a', 'b', 'c', 'd', 'e')]

# Direction of each indicator: 'bad' = higher is a worse outcome (coloured as a
# concern), 'neutral' = descriptive (no value judgement), else 'good'.
_BAD = {
    'discr_any', 'discr_police', 'discr_work', 'discr_housing', 'discr_evict',
    'discr_denial', 'legal_unmet', 'health_poor', 'sti_sympt', 'sti_told_12m',
    'gbv_any', 'gbv_phys', 'gbv_sex', 'gbv_emot',
}
_NEUTRAL = {'sex_active', 'brothel_based'}


def compute_srhr(responses):
    """responses: iterable of verified BaselineResponse. -> module-grouped
    indicator values per population."""
    rows = {'hijra': [], 'fsw': []}
    for r in responses:
        # Kobo stores grouped answers as 'group/field'; flatten so the indicator
        # field names below actually match. Population is resolved from the FORM,
        # not the stored column (which older rows may have misfiled).
        raw = flatten_group_keys(r.raw_data or {})
        pop = resolve_population(raw, default=(r.population or '').lower())
        if pop in rows:
            rows[pop].append(raw)

    out = {}
    for pop, data in rows.items():
        n = len(data)
        aggs = {}

        def P(key):
            return aggs.setdefault(key, Agg())

        incomes, phq_scores, phq_sui, fies_sev, know_hiv, know_sti = [], [], Agg(), Agg(), [], []
        hh_incomes = []

        for raw in data:
            if pop == 'hijra':
                P('employed').add(_s(raw, 'b108_worked') == '1', _s(raw, 'b108_worked') in ('1', '2'))
                # The Hijra instrument measures income on TWO mutually exclusive
                # branches (B101 = who you live with), and they are different
                # quantities that must never be pooled:
                #   dera (B101='2')  -> B106 = B104 - (B105 / B103), PERSONAL income
                #   otherwise        -> B107 total, the HOUSEHOLD's earnings
                # This published tile used B104 — the gross share handed over before
                # the dera's shared expenses are deducted, which the form itself does
                # not call income — and B104 is gated to the dera branch, so a figure
                # labelled "monthly income" for Hijra was 42 of 370 respondents.
                # Resolved from the B101 branch, not from "which field has a value":
                # B107's calculate runs for everyone and sums blanks to 0, so a dera
                # resident who is never shown the B107 block still submits 0 — that
                # is "not asked", not "earned nothing". See baseline/income.py.
                personal, household = resolve_income('hijra', raw)
                if personal is not None:
                    incomes.append(personal)
                if household is not None:
                    hh_incomes.append(household)
                hit, seen = _grid_any(raw, [f'q2_1_{c}' for c in 'abcdefghijklmno'])
                P('discr_any').add(hit, seen)
                P('discr_police').add(_s(raw, 'q2_1_k') == '1', _s(raw, 'q2_1_k') in ('1', '2'))
                P('discr_work').add(_s(raw, 'q2_1_g') == '1', _s(raw, 'q2_1_g') in ('1', '2'))
                v = _s(raw, 'q2_5')
                P('community').add(v in ('3', '4'), v in ('1', '2', '3', '4'))
                v = _s(raw, 'q2_12')
                P('rights_aware').add(bool(v) and '98' not in (v or ''), bool(v))
                P('legal_got').add(_s(raw, 'q2_19') == '1', _s(raw, 'q2_19') in ('1', '2'))
                P('legal_unmet').add(*_unmet_legal(raw))
                # HIV-knowledge items differ by form: the Hijra Q3.1–3.7 block is
                # all HIV, but the FSW form shifts — its Q3.1–3.3 are contraception
                # / condom-access, and only Q3.4–3.7 are HIV. Score the real HIV
                # yes/no items per form so the FSW score isn't diluted.
                hiv_ks = (['q3_1', 'q3_5', 'q3_6', 'q3_7'] if pop == 'hijra'
                          else ['q3_4', 'q3_6', 'q3_7'])
                hiv_items = [1 if _s(raw, f) == '1' else 0 for f in hiv_ks
                             if _s(raw, f) in ('1', '2')]
                if hiv_items:
                    know_hiv.append(100 * sum(hiv_items) / len(hiv_items))
                sti_items = [1 if _s(raw, f'q3_{i}') == '1' else 0 for i in (8, 9, 10)
                             if _s(raw, f'q3_{i}') in ('1', '2')]
                if sti_items:
                    know_sti.append(100 * sum(sti_items) / len(sti_items))
                P('sex_active').add(_s(raw, 'q4_3') == '1', _s(raw, 'q4_3') in ('1', '2'))
                # consistent condom = Always with every applicable partner type
                cvals = [_s(raw, f'q4_7_{c}') for c in 'abcd']
                appl = [v for v in cvals if v in ('1', '2', '3')]
                if appl:
                    P('condom_consistent').add(all(v == '1' for v in appl))
                v = _s(raw, 'q4_8')
                P('lube_water').add(v == '1', v in ('1', '2', '3', '4'))
                v = _s(raw, 'q5_1')
                P('health_poor').add(v in ('4', '5'), v in ('1', '2', '3', '4', '5'))
                hit, seen = _grid_any(raw, [f'q5_4_{c}' for c in 'abcd'])
                P('sti_sympt').add(hit, seen)
                ever = _s(raw, 'q5_8')
                if ever == '2':
                    P('hiv_test_12m').add(False)
                elif ever == '1':
                    v = _s(raw, 'q5_9')
                    if v in ('1', '2', '3'):
                        P('hiv_test_12m').add(v == '1')
                v = _s(raw, 'q5_11')
                P('hiv_counsel').add(v in ('1', '2', '3'), v in ('1', '2', '3', '4'))
                v = _s(raw, 'q5_15')
                P('sti_treat_done').add(v == '1', v in ('1', '2', '3'))
                P('svc_used').add(_s(raw, 'q6_1') == '1', _s(raw, 'q6_1') in ('1', '2'))
                v = _s(raw, 'q6_5')
                P('svc_satisfied').add(v in ('3', '4'), v in ('1', '2', '3', '4'))
                gbv_hit, gbv_seen = _grid_any(raw, [f + '_ever' for f in HIJRA_GBV])
                P('gbv_any').add(gbv_hit, gbv_seen)
            else:
                v = _s(raw, 'b101')
                P('brothel_based').add(v in ('1', '2'), bool(v))
                # 99 = "Prefer not to say" is a refusal code, not taka — it must
                # never enter the published median. See baseline/codes.py.
                inc = _int(raw, 'b108')
                if inc and not is_non_answer('fsw', 'b108', raw.get('b108')):
                    incomes.append(inc)
                v = _s(raw, 'b112')
                P('income_autonomy').add(v == '1', v in ('1', '2', '3'))
                P('savings').add(_s(raw, 'b114') == '1', _s(raw, 'b114') in ('1', '2'))
                hit, seen = _grid_any(raw, [f'q2_1_{c}' for c in 'abcdefghijklmn'])
                P('discr_any').add(hit, seen)
                P('discr_housing').add(_s(raw, 'q2_1_a') == '1', _s(raw, 'q2_1_a') in ('1', '2'))
                P('discr_evict').add(_s(raw, 'q2_1_b') == '1', _s(raw, 'q2_1_b') in ('1', '2'))
                P('discr_denial').add(_s(raw, 'q2_1_c') == '1', _s(raw, 'q2_1_c') in ('1', '2'))
                P('discr_police').add(_s(raw, 'q2_1_j') == '1', _s(raw, 'q2_1_j') in ('1', '2'))
                # Rights-awareness composite (doc cites "Q2.12-Q2.19" as a range):
                # q2_12_a-e = training received on rights/justice/services/advocacy;
                # q2_13 = aware of laws/legal protections; q2_14 = aware of social
                # safety net programmes; q2_17 = aware of skills programmes. q2_15/
                # 16/18 are outcome/detail items (not awareness) and q2_19 is the
                # separate "received legal services" indicator — excluded here.
                aw_fields = [f'q2_12_{c}' for c in 'abcde'] + ['q2_13', 'q2_14', 'q2_17']
                aware_vals = [_s(raw, f) for f in aw_fields]
                seen_aw = any(v in ('1', '2') for v in aware_vals)
                any_aware = any(v == '1' for v in aware_vals)
                P('rights_aware').add(any_aware, seen_aw)
                P('legal_got').add(_s(raw, 'q2_19') == '1', _s(raw, 'q2_19') in ('1', '2'))
                P('legal_unmet').add(*_unmet_legal(raw))
                # HIV-knowledge items differ by form: the Hijra Q3.1–3.7 block is
                # all HIV, but the FSW form shifts — its Q3.1–3.3 are contraception
                # / condom-access, and only Q3.4–3.7 are HIV. Score the real HIV
                # yes/no items per form so the FSW score isn't diluted.
                hiv_ks = (['q3_1', 'q3_5', 'q3_6', 'q3_7'] if pop == 'hijra'
                          else ['q3_4', 'q3_6', 'q3_7'])
                hiv_items = [1 if _s(raw, f) == '1' else 0 for f in hiv_ks
                             if _s(raw, f) in ('1', '2')]
                if hiv_items:
                    know_hiv.append(100 * sum(hiv_items) / len(hiv_items))
                sti_items = [1 if _s(raw, f'q3_{i}') == '1' else 0 for i in (8, 9, 10)
                             if _s(raw, f'q3_{i}') in ('1', '2')]
                if sti_items:
                    know_sti.append(100 * sum(sti_items) / len(sti_items))
                cvals = [_s(raw, f'q4_7_{c}') for c in 'abc']
                appl = [v for v in cvals if v in ('1', '2', '3')]
                if appl:
                    P('condom_consistent').add(all(v == '1' for v in appl))
                v = _s(raw, 'q4_5')
                P('condom_last_client').add(v == '1', v in ('1', '2'))
                v = _s(raw, 'q4_9')
                P('refuse_client').add(v == '1', v in ('1', '2', '3'))
                v = _s(raw, 'q5_1')
                P('health_poor').add(v in ('4', '5'), v in ('1', '2', '3', '4', '5'))
                hit, seen = _grid_any(raw, [f'q5_4_{c}' for c in 'abcde'])
                P('sti_sympt').add(hit, seen)
                P('sti_tested').add(_s(raw, 'q5_8') == '1', _s(raw, 'q5_8') in ('1', '2'))
                P('sti_told_12m').add(_s(raw, 'q5_9') == '1', _s(raw, 'q5_9') in ('1', '2'))
                v = _s(raw, 'q5_11')
                P('syph_test_12m').add(v == '1', v in ('1', '2', '3'))
                v = _s(raw, 'q5_10')
                P('sti_treat_done').add(v == '1', v in ('1', '2', '3'))
                P('svc_used').add(_s(raw, 'q6_1') == '1', _s(raw, 'q6_1') in ('1', '2'))
                v = _s(raw, 'q6_4')
                P('svc_satisfied').add(v in ('3', '4'), v in ('1', '2', '3', '4'))
                gbv_hit, gbv_seen = _grid_any(raw, [f + '_ever' for f in FSW_GBV])
                P('gbv_any').add(gbv_hit, gbv_seen)
                h, s2 = _grid_any(raw, [f + '_ever' for f in FSW_PHYS])
                P('gbv_phys').add(h, s2)
                h, s2 = _grid_any(raw, [f + '_ever' for f in FSW_SEX])
                P('gbv_sex').add(h, s2)
                h, s2 = _grid_any(raw, [f + '_ever' for f in FSW_PSY])
                P('gbv_emot').add(h, s2)
                # Q7.18 asks "did you seek help" about the most serious incident IN
                # THE PAST 12 MONTHS. Its condition lived only in the label text —
                # the deployed form carried relevant=None (now gated), so all 303
                # FSW were asked it, including women reporting no incident at all.
                # Counting every answer put non-victims in the denominator of
                # "Sought help after GBV", deflating it. The denominator is the
                # 12-month incident subset, not everyone who happened to answer.
                inc_12mo, _ = _grid_any(
                    raw, [f + '_12mo' for f in FSW_GBV + FSW_TFV])
                v = _s(raw, 'q7_18')
                P('gbv_help').add(inc_12mo and v == '1', inc_12mo and v in ('1', '2'))

            score, item9 = _phq(raw)
            if score is not None:
                phq_scores.append(score)
                phq_sui.add(item9 > 0)
            fc = _fies_count(raw, pop)
            if fc is not None:
                fies_sev.add(fc >= 7)
            # PrEP / PEP awareness — both forms ask these as yes/no at Q3.6 / Q3.7.
            P('prep_aware').add(_s(raw, 'q3_6') == '1', _s(raw, 'q3_6') in ('1', '2'))
            P('pep_aware').add(_s(raw, 'q3_7') == '1', _s(raw, 'q3_7') in ('1', '2'))

        def pct(key):
            a = aggs.get(key)
            return {'value': a.pct() if a else None, 'n': a.d if a else 0}

        def tile(key, label, ref):
            d = 'bad' if key in _BAD else ('neutral' if key in _NEUTRAL else 'good')
            return {'label': label, 'ref': ref, 'dir': d, **pct(key)}

        phq_prev = round(100 * sum(1 for s2 in phq_scores if s2 >= 10) / len(phq_scores)) if phq_scores else None
        phq_modsev = round(100 * sum(1 for s2 in phq_scores if s2 >= 15) / len(phq_scores)) if phq_scores else None
        med_inc = int(median(incomes)) if incomes else None
        med_hh_inc = int(median(hh_incomes)) if hh_incomes else None
        k_hiv = round(sum(know_hiv) / len(know_hiv)) if know_hiv else None
        k_sti = round(sum(know_sti) / len(know_sti)) if know_sti else None

        common_mh = [
            {'label': 'Depression prevalence (PHQ-9 ≥ 10)', 'ref': 'PHQ-9', 'dir': 'bad', 'value': phq_prev, 'n': len(phq_scores)},
            {'label': 'Moderate/severe depression (PHQ-9 ≥ 15)', 'ref': 'PHQ-9', 'dir': 'bad', 'value': phq_modsev, 'n': len(phq_scores)},
            {'label': 'Suicidal ideation (item 9 > 0)', 'ref': 'PHQ-9 · 9', 'dir': 'bad', 'value': phq_sui.pct(), 'n': phq_sui.d},
        ]

        if pop == 'hijra':
            modules = [
                ('Livelihood & economic security', [
                    tile('employed', 'Worked in the past 7 days', 'B108'),
                    # Two tiles, not one average: the instrument asks a different
                    # question of each branch, so pooling them would report a
                    # personal figure and a household figure as one number.
                    {'label': 'Median personal income — lives in a dera', 'ref': 'B106',
                     'dir': 'neutral', 'value': med_inc, 'n': len(incomes), 'unit': '৳'},
                    {'label': 'Median household income — does not live in a dera', 'ref': 'B107',
                     'dir': 'neutral', 'value': med_hh_inc, 'n': len(hh_incomes), 'unit': '৳'},
                    {'label': 'Severe food insecurity (FIES 7+/9)', 'ref': 'C101–C109', 'dir': 'bad', 'value': fies_sev.pct(), 'n': fies_sev.d},
                ]),
                ('Discrimination, rights & legal access', [
                    tile('discr_any', 'Experienced any discrimination', 'Q2.1'),
                    tile('discr_police', 'Police harassment', 'Q2.1k'),
                    tile('discr_work', 'Workplace discrimination', 'Q2.1g'),
                    tile('community', 'Participates in community events', 'Q2.5'),
                    tile('rights_aware', 'Aware of any legal right/policy', 'Q2.12'),
                    tile('legal_got', 'Received legal services', 'Q2.19'),
                    tile('legal_unmet', 'Needed but did not seek legal support', 'Q2.21'),
                ]),
                ('HIV & STI knowledge', [
                    {'label': 'HIV knowledge score', 'ref': 'Q3.1–3.7', 'dir': 'good', 'value': k_hiv, 'n': len(know_hiv), 'unit': 'score'},
                    tile('prep_aware', 'Aware of PrEP', 'Q3.6'),
                    tile('pep_aware', 'Aware of PEP', 'Q3.7'),
                    {'label': 'STI knowledge score', 'ref': 'Q3.8–3.10', 'dir': 'good', 'value': k_sti, 'n': len(know_sti), 'unit': 'score'},
                ]),
                ('Sexual behaviour & prevention', [
                    tile('sex_active', 'Sexually active in last 12 months', 'Q4.3'),
                    tile('condom_consistent', 'Consistent condom use (all partners)', 'Q4.7'),
                    tile('lube_water', 'Water-based lubricant with condoms', 'Q4.8'),
                ]),
                ('Health status, testing & services', [
                    tile('health_poor', 'Self-rated poor/very poor health', 'Q5.1'),
                    tile('sti_sympt', 'STI symptoms in last 12 months', 'Q5.4'),
                    tile('hiv_test_12m', 'HIV test within last 12 months', 'Q5.8–5.9'),
                    tile('hiv_counsel', 'Counselling at last HIV test', 'Q5.11'),
                    tile('sti_treat_done', 'Completed STI treatment', 'Q5.15'),
                    tile('svc_used', 'Used a health facility (12 m)', 'Q6.1'),
                    tile('svc_satisfied', 'Most/all needs met by services', 'Q6.5'),
                ]),
                ('Mental health (PHQ-9)', common_mh),
                ('Gender-based violence', [
                    tile('gbv_any', 'Any GBV experience (lifetime)', 'Q7.1'),
                ]),
            ]
        else:
            modules = [
                ('Livelihood & economic security', [
                    tile('brothel_based', 'Brothel-based (vs street-based)', 'B101'),
                    {'label': 'Median monthly income from sex work', 'ref': 'B108', 'dir': 'neutral', 'value': med_inc, 'n': len(incomes), 'unit': '৳'},
                    tile('income_autonomy', 'Full control over own income', 'B112'),
                    tile('savings', 'Has savings', 'B114'),
                    {'label': 'Severe food insecurity (FIES 7+/9)', 'ref': 'B301', 'dir': 'bad', 'value': fies_sev.pct(), 'n': fies_sev.d},
                ]),
                ('Discrimination, rights & legal access', [
                    tile('discr_any', 'Experienced any discrimination', 'Q2.1'),
                    tile('discr_housing', 'Housing discrimination', 'Q2.1a'),
                    tile('discr_evict', 'Brothel eviction threat', 'Q2.1b'),
                    tile('discr_denial', 'Service denial in public places', 'Q2.1c'),
                    tile('discr_police', 'Police harassment', 'Q2.1j'),
                    tile('rights_aware', 'Aware of any legal protection', 'Q2.12'),
                    tile('legal_got', 'Received legal support', 'Q2.19'),
                    tile('legal_unmet', 'Unmet need for legal support', 'Q2.21'),
                ]),
                ('HIV & STI knowledge', [
                    {'label': 'HIV knowledge score', 'ref': 'Q3.4–3.7', 'dir': 'good', 'value': k_hiv, 'n': len(know_hiv), 'unit': 'score'},
                    tile('prep_aware', 'Aware of PrEP', 'Q3.6'),
                    tile('pep_aware', 'Aware of PEP', 'Q3.7'),
                    {'label': 'STI knowledge score', 'ref': 'Q3.8–3.10', 'dir': 'good', 'value': k_sti, 'n': len(know_sti), 'unit': 'score'},
                ]),
                ('Sexual behaviour & prevention', [
                    tile('condom_consistent', 'Consistent condom use (all partners)', 'Q4.7'),
                    tile('condom_last_client', 'Condom at last sex with client', 'Q4.5'),
                    tile('refuse_client', 'Can refuse a client who rejects condoms', 'Q4.9'),
                ]),
                ('Health status, testing & services', [
                    tile('health_poor', 'Self-rated poor/very poor health', 'Q5.1'),
                    tile('sti_sympt', 'STI symptoms in last 12 months', 'Q5.4'),
                    tile('sti_tested', 'Ever tested for an STI (non-HIV)', 'Q5.8'),
                    tile('sti_told_12m', 'Diagnosed with an STI (12 m)', 'Q5.9'),
                    tile('syph_test_12m', 'Syphilis test within 12 months', 'Q5.11'),
                    tile('sti_treat_done', 'Completed STI treatment', 'Q5.10'),
                    tile('svc_used', 'Used a health facility (12 m)', 'Q6.1'),
                    tile('svc_satisfied', 'Most/all needs met by services', 'Q6.4'),
                ]),
                ('Mental health (PHQ-9)', common_mh),
                ('Gender-based violence', [
                    tile('gbv_any', 'Any GBV experience (lifetime)', 'Q7.1'),
                    tile('gbv_phys', 'Physical violence', 'Q7.1 i–iii'),
                    tile('gbv_sex', 'Sexual violence', 'Q7.1 vi–viii'),
                    tile('gbv_emot', 'Psychological violence', 'Q7.1 iv–v'),
                    tile('gbv_help', 'Sought help after GBV (12 m)', 'Q7.18'),
                ]),
            ]

        out[pop] = {'n': n, 'modules': [
            {'module': name, 'indicators': inds} for name, inds in modules
        ]}
    return out
