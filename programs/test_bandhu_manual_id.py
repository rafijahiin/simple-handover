"""Manual beneficiary IDs: the field types the number, nobody gets lost.

Bandhu asked for manual entry (2026-08-26). These cover the two ways manual
entry went wrong before: a number from the wrong centre, and two educators
choosing the same number for different women in one sitting.
"""
from django.test import TestCase

from programs.bandhu_handlers import handle_bandhu_mother_list
from programs.models import Client, ServiceCenter


def _centre(code='BND-DIC-08', district='Manikganj'):
    # The Bandhu centres are seeded, so take the existing row when it is there.
    centre, _ = ServiceCenter.objects.get_or_create(
        code=code,
        defaults={'name': 'WC ' + district, 'organisation': 'Bandhu',
                  'district': district})
    return centre


def _payload(kobo, name, typed='', dist='08', centre='BND-DIC-08'):
    return {
        '_id': kobo, 'centre_id': centre, 'centre_district_code': dist,
        'ml_existing_id': typed, 'ml_id_no': typed, 'ml_name': name,
        'ml_gender': '01',
    }


class ManualIdTests(TestCase):
    def setUp(self):
        self.centre = _centre()

    def test_typed_id_is_used_as_given(self):
        handle_bandhu_mother_list(_payload('1', 'Rina', '08-0042'), None, None)
        self.assertEqual(Client.objects.get().client_id, '08-0042')

    def test_blank_still_issues_one(self):
        handle_bandhu_mother_list(_payload('2', 'Shima'), None, None)
        c = Client.objects.get()
        self.assertTrue(c.client_id.startswith('08-'))

    def test_collision_registers_the_second_woman_instead_of_dropping_her(self):
        """The old behaviour kept the first record and returned 200, so the
        second woman was never registered and nothing said so."""
        handle_bandhu_mother_list(_payload('1', 'Rina', '08-0042'), None, None)
        r = handle_bandhu_mother_list(_payload('2', 'Shima', '08-0042'), None, None)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(Client.objects.count(), 2)
        names = dict(Client.objects.values_list('name', 'client_id'))
        self.assertEqual(names['Rina'], '08-0042')
        self.assertNotEqual(names['Shima'], '08-0042')
        self.assertTrue(names['Shima'].startswith('08-'))

    def test_the_same_woman_twice_is_still_one_record(self):
        handle_bandhu_mother_list(_payload('1', 'Rina', '08-0042'), None, None)
        handle_bandhu_mother_list(_payload('2', ' rina ', '08-0042'), None, None)
        self.assertEqual(Client.objects.count(), 1)

    def test_a_redelivered_submission_does_not_register_anyone_twice(self):
        handle_bandhu_mother_list(_payload('1', 'Rina', '08-0042'), None, None)
        handle_bandhu_mother_list(_payload('1', 'Rina', '08-0042'), None, None)
        self.assertEqual(Client.objects.count(), 1)


def _row(name):
    """A survey row by field name. _sr returns a list positioned to match
    SURVEY_HDR, so read a cell with _cell() rather than a literal index."""
    from programs.management.commands.build_bandhu_forms import (
        _mother_list_survey)
    return next(r for r in _mother_list_survey() if len(r) > 1 and r[1] == name)


def _cell(row, column):
    """One cell of a survey row, by XLSForm column name.

    Resolved through SURVEY_HDR instead of a hardcoded index: adding a column
    to the builder, as the Bangla hint did, shifts every position after it and
    silently turned this assertion into a read of the wrong cell."""
    from programs.management.commands.build_bandhu_forms import SURVEY_HDR
    return row[SURVEY_HDR.index(column)]


class PrefixConstraintTests(TestCase):
    """The wrong-centre prefix is blocked in the form, before it is sent."""

    def test_form_requires_the_centre_prefix(self):
        row = _row('ml_existing_id')
        constraint = _cell(row, 'constraint')
        self.assertIn('starts-with', constraint)
        self.assertIn('centre_district_code', constraint)
        self.assertIn('^[0-9]{2}-[0-9]{4}$', constraint)

    def test_the_field_is_labelled_for_everyday_use(self):
        row = _row('ml_existing_id')
        self.assertEqual(_cell(row, 'label::English'), 'Beneficiary ID')
        self.assertNotIn('only if she is', ' '.join(str(x) for x in row))
