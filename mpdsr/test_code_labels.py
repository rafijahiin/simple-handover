"""Guard: the label mirror in code_labels.py must not drift from the forms.

code_labels.py hand-mirrors the choice lists in build_ciprb_forms.py because
that builder imports openpyxl, which production does not have. A mirror that
nobody checks rots, and a rotted mirror silently renders raw database codes to
CIPRB again. These tests fail the moment a form gains a choice the mirror does
not cover.
"""

import unittest

from django.test import SimpleTestCase

from mpdsr.code_labels import (
    _MAPS, _norm, UNKNOWN, band_pnc, band_time_of_death, canonicalise, decode,
    relabel,
)

try:
    from programs.management.commands.build_ciprb_forms import (
        _community_maternal_choices, _facility_maternal_choices,
    )
    HAVE_BUILDER = True
except Exception:                                    # openpyxl absent
    HAVE_BUILDER = False


# Choice list in the form  ->  indicator field in code_labels
LIST_TO_FIELD = {
    'death_place': 'place_of_death',
    'facility_place': 'place_of_delivery',
    'provider_cadre': 'person_assisted_delivery',
    'delivery_mode': 'mode_of_delivery',
    'delivery_outcome': 'delivery_outcome',
}


@unittest.skipUnless(HAVE_BUILDER, 'form builder needs openpyxl')
class MirrorCoversEveryFormChoice(SimpleTestCase):
    def test_every_choice_decodes_to_something_readable(self):
        rows = list(_community_maternal_choices()) + list(_facility_maternal_choices())
        missing = []
        for row in rows:
            list_name, code = str(row[0]), str(row[1])
            field = LIST_TO_FIELD.get(list_name)
            if not field:
                continue
            # Check membership directly. Inferring "unmapped" from the decoded
            # string does not work: a correct mapping may legitimately produce
            # the de-underscored code ('in_transit' -> 'In transit').
            if _norm(code) not in _MAPS.get(field, {}):
                missing.append('%s / %s' % (list_name, code))
        self.assertEqual(
            missing, [],
            'These form choices are not in code_labels._MAPS, so they would '
            'render as raw codes: %s' % missing)


class DuplicateVariantsMerge(SimpleTestCase):
    def test_legacy_labels_and_form_codes_land_on_one_bucket(self):
        # The exact split seen in production: 18 under the form code, 1 under
        # the legacy label, charted as two different modes of delivery.
        merged = relabel('mode_of_delivery',
                         {'vaginal_spontaneous': 18, 'normal': 1, 'C-section': 12})
        self.assertEqual(merged['Vaginal (spontaneous)'], 19)
        self.assertEqual(merged['Caesarean section'], 12)

    def test_misspelled_fistula_type_merges_onto_the_canonical_code(self):
        # Fistula must keep CODES: the Fistula Corner charts look up
        # PIE_COLORS['obstetric'] and GENITAL_TYPES 'vvf'/'rvf'. Returning
        # English labels here emptied both charts on the live dashboard.
        merged = canonicalise('genital_fistula_type',
                              {'iterogenic': 1, 'Iatrogenic': 1, 'VVF': 78,
                               'RVF': 10, 'TR': 4, 'UVF': 1})
        self.assertEqual(merged['iatrogenic'], 2, 'the misspelling must merge')
        self.assertEqual(merged['vvf'], 78)
        self.assertEqual(merged['rvf'], 10)
        self.assertEqual(merged['traumatic'], 4)
        self.assertEqual(merged['urethrovaginal'], 1)

    def test_fistula_cause_keeps_the_codes_the_pie_colours_need(self):
        merged = canonicalise('fistula_type', {'obstetric': 23, 'iterogenic': 4})
        self.assertEqual(sorted(merged), ['iatrogenic', 'obstetric'])

    def test_blank_and_sentinel_become_unknown(self):
        merged = relabel('place_of_death', {'': 2, '99': 1, 'home': 3})
        self.assertEqual(merged[UNKNOWN], 3)
        self.assertEqual(merged['Home'], 3)


class TimeOfDeathBands(SimpleTestCase):
    def test_clock_times_bin_into_four_hour_periods(self):
        out = band_time_of_death({
            '11:30:00.000+06:00': 1, '09:20:00.000+06:00': 1,
            '23:45:00.000+06:00': 1, '00:30:00.000+06:00': 2,
        })
        self.assertEqual(out['08:00-11:59'], 2)
        self.assertEqual(out['20:00-23:59'], 1)
        self.assertEqual(out['00:00-03:59'], 2)

    def test_unparseable_time_is_unknown_not_dropped(self):
        out = band_time_of_death({'antepartum': 3, '': 1})
        self.assertEqual(out[UNKNOWN], 4)
        self.assertEqual(sum(out.values()), 4)


class PostnatalCareBands(SimpleTestCase):
    def test_visit_counts_band_and_totals_are_preserved(self):
        # The live production distribution, including the impossible values.
        out = band_pnc({'0': 3, '1': 10, '2': 5, '3': 1, '4': 1, '24': 1, '99': 1})
        self.assertEqual(out['None'], 3)
        self.assertEqual(out['1 visit'], 10)
        self.assertEqual(out['4 or more'], 1)
        self.assertEqual(out[UNKNOWN], 2,
                         '99 (not-known sentinel) + 24 (impossible count) both land in Unknown')
        self.assertNotIn('Invalid entry', out,
                         'error bucket must not surface on the public panel')
        self.assertEqual(sum(out.values()), 22, 'no record may be dropped')


class CanonicalOrdering(SimpleTestCase):
    def test_anc_visits_come_back_in_clinical_order(self):
        # The chart preserves insertion order, and a Counter's order is
        # arbitrary, so the live dashboard showed 1, 3, 4+, None, 2.
        out = relabel('anc_visits_count',
                      {'3': 14, '1': 7, '4_plus': 14, 'none': 5, '2': 9})
        self.assertEqual(list(out.keys()),
                         ['None', '1 visit', '2 visits', '3 visits', '4 or more'])

    def test_unexpected_values_are_kept_after_the_canonical_run(self):
        out = relabel('anc_visits_count', {'2': 1, 'wat': 3})
        self.assertEqual(list(out.keys())[0], '2 visits')
        self.assertIn(3, out.values(), 'an unmapped value must not be dropped')
