"""Non-answer codes must never be reported as quantities.

B108 documents "(99 = Prefer not to say)" in the question text itself. Feeding
that to the published income band counted three FSW respondents who DECLINED as
earning under 5,000 taka.
"""
from django.test import TestCase

from .codes import NON_ANSWER_CODES, is_non_answer
from .insights import compute_insights
from .schema import load_schema

FSW_UID = 'aVsJ7VJ35k8GshpQpnXygC'


class _Resp:
    survey_round = 'baseline'
    district = 'Jashore'
    age = 30

    def __init__(self, raw, population='fsw'):
        self.raw_data = raw
        self.population = population


def _fsw(**over):
    base = {'_xform_id_string': FSW_UID, 'grp_admin/district': 'Jashore',
            'grp_scr/s1_age': 30}
    base.update(over)
    return base


class NonAnswerCodeTest(TestCase):
    def test_is_non_answer_only_for_documented_fields(self):
        self.assertTrue(is_non_answer('fsw', 'b108', 99))
        self.assertTrue(is_non_answer('fsw', 'b108', '99'))
        self.assertFalse(is_non_answer('fsw', 'b108', 25000))
        # 98 is NOT documented for b108 — do not invent codes.
        self.assertFalse(is_non_answer('fsw', 'b108', 98))
        # q4_1 documents both 98 and 99.
        self.assertTrue(is_non_answer('fsw', 'q4_1', 98))
        # a field with no documented code never suppresses a real answer.
        self.assertFalse(is_non_answer('fsw', 'a203', 99))
        self.assertFalse(is_non_answer('hijra', 'b104_share', 99))

    def test_refusal_is_excluded_from_the_published_income_band(self):
        rows = [_Resp(_fsw(**{'grp_b1/b108': 99})),        # declined
                _Resp(_fsw(**{'grp_b1/b108': 25000}))]     # real
        bands = compute_insights(rows)['income_band']['fsw']
        by = {b['name']: b['value'] for b in bands}
        self.assertEqual(by.get('<5k', 0), 0, 'a refusal was banded as income')
        self.assertEqual(by.get('20k–30k', 0), 1)

    def test_genuine_low_income_still_counted(self):
        rows = [_Resp(_fsw(**{'grp_b1/b108': 2000}))]
        by = {b['name']: b['value'] for b in compute_insights(rows)['income_band']['fsw']}
        self.assertEqual(by.get('<5k', 0), 1)

    def test_non_answer_codes_match_the_live_forms(self):
        """Every configured field must still exist in the deployed schema, and its
        label must still document the code — otherwise the mapping has rotted."""
        for pop, fields in NON_ANSWER_CODES.items():
            schema = load_schema()[pop]
            for field, codes in fields.items():
                self.assertIn(field, schema['labels'],
                              f'{pop}/{field} no longer exists in the form')
                label = str(schema['labels'][field])
                for code in codes:
                    self.assertIn(str(code), label,
                                  f'{pop}/{field} label no longer documents {code}: {label[:90]}')
