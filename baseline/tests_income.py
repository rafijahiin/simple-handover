"""Hijra income is measured on two mutually exclusive branches.

B101 (who do you live with) splits the instrument:
  dera (B101='2')  -> B106 = B104 - (B105 / B103)  PERSONAL income
  otherwise        -> B107 total                    HOUSEHOLD earnings

The published chart and SRHR tile read B104 — the gross share handed over BEFORE
the dera's shared expenses are deducted, which the questionnaire itself does not
call income, and which only the dera branch is ever asked. 42 of 370 Hijra
answered it; the other 328 dropped out of a figure titled "Monthly income"
without the chart saying so.
"""
from django.test import TestCase

from .income import resolve_income
from .insights import compute_insights
from .srhr import compute_srhr

HIJRA_UID = 'aBT7aCL9p4FGcW4WwXZcr6'


class _Resp:
    survey_round = 'baseline'
    district = 'Dhaka'
    age = 30
    population = 'hijra'

    def __init__(self, raw):
        self.raw_data = raw


def _dera(**over):
    """Lives in a dera: answers B103/B104/B105, and B106 is calculated."""
    base = {'_xform_id_string': HIJRA_UID, 'grp_a2/a205_age': 30,
            'grp_b1/b101_live_with': '2', 'grp_b1/b103_dera_members': 10,
            'grp_b1/b104_share': 15000, 'grp_b1/b105_shared_exp': 45000,
            'grp_b1/b106_personal_income': 10500}
    base.update(over)
    return base


def _non_dera(**over):
    """Does not live in a dera: answers the itemised B107 block instead."""
    base = {'_xform_id_string': HIJRA_UID, 'grp_a2/a205_age': 30,
            'grp_b1/b101_live_with': '1', 'grp_b1/b107_sexwork': 20000,
            'grp_b1/b107_total': 20000}
    base.update(over)
    return base


def _bands(rows, key='income_band'):
    return {b['name']: b['value'] for b in compute_insights(rows)[key]['hijra']}


class HijraIncomeBranchTest(TestCase):
    def test_personal_income_uses_b106_not_the_gross_share(self):
        # B104 = 15,000 would band 15k-20k. B106 = 10,500 is the actual income.
        by = _bands([_Resp(_dera())])
        self.assertEqual(by.get('10k–15k', 0), 1, 'income must come from B106')
        self.assertEqual(by.get('15k–20k', 0), 0, 'B104 gross share was banded as income')

    def test_household_income_is_a_separate_series_never_pooled(self):
        rows = [_Resp(_dera()), _Resp(_non_dera())]
        personal = _bands(rows)
        household = _bands(rows, 'hh_income_band')
        self.assertEqual(sum(personal.values()), 1, 'only the dera record has personal income')
        self.assertEqual(sum(household.values()), 1, 'only the non-dera record has household income')
        self.assertEqual(household.get('20k–30k', 0), 1)

    def test_coverage_is_published_so_a_gate_cannot_hide_a_denominator(self):
        rows = [_Resp(_dera())] + [_Resp(_non_dera()) for _ in range(3)]
        cov = compute_insights(rows)['income_covered']['hijra']
        self.assertEqual(cov['total'], 4)
        self.assertEqual(cov['n'], 1, 'personal income covers only the dera branch')
        self.assertEqual(cov['hh_n'], 3)

    def test_srhr_reports_the_two_branches_as_two_tiles(self):
        out = compute_srhr([_Resp(_dera()), _Resp(_non_dera())])['hijra']
        tiles = [t for mod in out['modules'] for t in mod['indicators']]
        refs = {t.get('ref'): t for t in tiles}
        self.assertNotIn('B104', refs, 'B104 gross share is still published as income')
        self.assertEqual(refs['B106']['value'], 10500)
        self.assertEqual(refs['B106']['n'], 1)
        self.assertEqual(refs['B107']['value'], 20000)
        self.assertEqual(refs['B107']['n'], 1)


class PhantomZeroTest(TestCase):
    """B107_total is a `calculate` with NO relevance gate, and its expression wraps
    every source in if(x!='', x, 0). Kobo therefore submits b107_total = 0 for a
    dera resident who is never shown the B107 block. Banding on "a value is
    present" reported 49 of them as households earning under 5,000 taka."""

    def test_dera_resident_is_not_a_zero_income_household(self):
        raw = {'b101_live_with': '2', 'b106_personal_income': 10500, 'b107_total': 0}
        personal, household = resolve_income('hijra', raw)
        self.assertEqual(personal, 10500)
        self.assertIsNone(household, 'the dera branch never answers B107')

    def test_dera_zero_is_kept_out_of_the_published_band(self):
        rows = [_Resp(_dera(**{'grp_b1/b107_total': 0}))]
        self.assertEqual(_bands(rows, 'hh_income_band').get('<5k', 0), 0,
                         'a dera resident was banded as a household under 5k')
        self.assertEqual(compute_insights(rows)['income_covered']['hijra']['hh_n'], 0)

    def test_a_genuine_zero_household_is_kept(self):
        # The B107 sources are required on this branch, so all-zeros is an answer.
        raw = {'b101_live_with': '1', 'b107_total': 0}
        personal, household = resolve_income('hijra', raw)
        self.assertIsNone(personal)
        self.assertEqual(household, 0)

    def test_unanswered_branch_yields_nothing(self):
        self.assertEqual(resolve_income('hijra', {'b107_total': 0}), (None, None))

    def test_fsw_is_unbranched(self):
        self.assertEqual(resolve_income('fsw', {'b108': 25000}), (25000, None))


class UnmetLegalNeedTest(TestCase):
    """Q2.21 '00' ("No such need arose") is exclusive: it cannot be true alongside
    a reason for not seeking help. The indicator used to test "'00' not in the
    answer", which silently sided with the 00 — 29 of 319 FSW named a barrier AND
    ticked 00 and were all published as having no unmet need (40 vs 69)."""

    def test_contradiction_leaves_the_denominator_rather_than_being_guessed(self):
        from .srhr import _unmet_legal
        # named a barrier AND said no need arose -> ambiguous, not a value to guess
        self.assertEqual(_unmet_legal({'q2_21': '00 02'}), (True, False))

    def test_clean_answers_score_normally(self):
        from .srhr import _unmet_legal
        self.assertEqual(_unmet_legal({'q2_21': '00'}), (False, True))      # no need
        self.assertEqual(_unmet_legal({'q2_21': '02 05'}), (True, True))    # unmet
        self.assertEqual(_unmet_legal({'q2_21': ''}), (False, False))       # unanswered

    def test_fsw_q2_21_is_now_guarded_like_hijra_always_was(self):
        from .anomaly import EXCLUSIVE_CHOICE_CODES
        self.assertEqual(EXCLUSIVE_CHOICE_CODES['fsw'].get('q2_21'), ['00'],
                         'the same question is enforced to different standards per form')
