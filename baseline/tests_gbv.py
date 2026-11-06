"""Q7.18 (help-seeking after GBV) is a conditional question.

Its label says "If Q7.1 or Q7.2 shows any incident in past 12 months", but the
deployed FSW form carried relevant=None — the condition existed only as text an
enumerator was expected to read and obey. So all 305 FSW were shown it, 122 of
them with no 12-month incident at all, and every one of those answers landed in
the denominator of the published "Sought help after GBV (12 m)" indicator:
24/305 = 8% instead of 17/183 = 9%.

Hijra's structurally identical q7_14 was always gated (16-term disjunction).
"""
from django.test import TestCase

from .srhr import FSW_GBV, FSW_TFV, compute_srhr

FSW_UID = 'aVsJ7VJ35k8GshpQpnXygC'


class _Resp:
    survey_round = 'baseline'
    district = 'Jashore'
    age = 30
    population = 'fsw'

    def __init__(self, raw):
        self.raw_data = raw


def _fsw(**over):
    base = {'_xform_id_string': FSW_UID, 'grp_scr/s1_age': 30}
    base.update(over)
    return base


def _tiles(rows):
    out = compute_srhr([_Resp(r) for r in rows])['fsw']
    return {t['ref']: t for mod in out['modules'] for t in mod['indicators']}


class GbvHelpDenominatorTest(TestCase):
    def test_respondent_with_no_incident_is_not_in_the_denominator(self):
        # Answered "No, did not seek help" but reported no 12-month incident:
        # the ungated form asked her anyway. She is not a GBV victim and must not
        # dilute the help-seeking rate.
        rows = [_fsw(**{'grp_module7/q7_1_i_12mo': '2', 'grp_module7/q7_18': '2'})]
        self.assertIsNone(_tiles(rows)['Q7.18']['value'])
        self.assertEqual(_tiles(rows)['Q7.18']['n'], 0)

    def test_victim_who_sought_help_counts(self):
        rows = [_fsw(**{'grp_module7/q7_1_i_12mo': '1', 'grp_module7/q7_18': '1'})]
        t = _tiles(rows)['Q7.18']
        self.assertEqual((t['value'], t['n']), (100, 1))

    def test_denominator_is_the_incident_subset(self):
        rows = [
            _fsw(**{'grp_module7/q7_1_i_12mo': '1', 'grp_module7/q7_18': '1'}),   # victim, sought
            _fsw(**{'grp_module7/q7_2_a_12mo': '1', 'grp_module7/q7_18': '2'}),   # TFV victim, did not
            _fsw(**{'grp_module7/q7_1_i_12mo': '2', 'grp_module7/q7_18': '2'}),   # no incident — excluded
            _fsw(**{'grp_module7/q7_1_i_12mo': '2', 'grp_module7/q7_18': '1'}),   # no incident — excluded
        ]
        t = _tiles(rows)['Q7.18']
        self.assertEqual(t['n'], 2, 'non-victims are still in the denominator')
        self.assertEqual(t['value'], 50)

    def test_q7_2_technology_violence_counts_as_an_incident(self):
        # Q7.18 asks about "Q7.1 OR Q7.2"; FSW_GBV alone covers only Q7.1.
        self.assertTrue(FSW_TFV, 'Q7.2 battery must be defined')
        rows = [_fsw(**{'grp_module7/q7_2_c_12mo': '1', 'grp_module7/q7_18': '1'})]
        self.assertEqual(_tiles(rows)['Q7.18']['n'], 1)

    def test_the_live_form_gates_q7_18(self):
        """The builder must emit the gate — the label text is not a skip rule."""
        from programs.management.commands._fsw_modules import fsw_module_survey
        row = next(r for r in fsw_module_survey() if r[1] == 'q7_18')
        rel = row[6] or ''
        self.assertIn('_12mo', rel, 'q7_18 has no relevance gate')
        for f in FSW_GBV + FSW_TFV:
            self.assertIn('${' + f + '_12mo}', rel, f'{f} missing from the q7_18 gate')
