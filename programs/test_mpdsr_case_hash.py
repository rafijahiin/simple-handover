"""A case serial is unique per form and district — the case_hash must be too.

MPDSRCase.case_hash carries a UNIQUE constraint across the whole table, but
`case_serial` is a per-form, per-district counter: F-01/Gaibandha and
F-02/Sunamganj both have a case "21". The upsert looked the row up scoped to
(partner, sub_form_type, district, case_hash) and then stored the BARE serial,
so a serial already used by another form or district matched nothing, tried to
INSERT, and hit the global constraint:

    IntegrityError: duplicate key value violates unique constraint
    "mpdsr_mpdsrcase_case_hash_key"  DETAIL: Key (case_hash)=(21) already exists.

programs/webhook.py turns any handler exception into a 500, so Kobo could not
deliver and the submission stayed in Kobo. 90 of 152 MPDSR death records never
reached the approval queue or the dashboard.

These tests run the real handlers, so they fail on the bare-serial version.
"""
from django.test import TestCase

from mpdsr.models import MPDSRCase
from programs.ciprb_handlers import (
    handle_ciprb_mpdsr_community_maternal,
    handle_ciprb_mpdsr_community_neonatal,
    handle_ciprb_mpdsr_facility_neonatal,
)


def _payload(**over):
    base = {
        '_id': '900001',
        'case_serial': '21',
        'district': 'gaibandha',
        'death_date': '2026-07-01',
        'consent_given': '1',
    }
    base.update(over)
    return base


class CaseSerialCollisionTest(TestCase):
    def test_same_serial_across_two_forms_does_not_collide(self):
        r1 = handle_ciprb_mpdsr_community_maternal(_payload(_id='900001'), None, None)
        r2 = handle_ciprb_mpdsr_community_neonatal(_payload(_id='900002'), None, None)
        self.assertEqual((r1.status_code, r2.status_code), (200, 200))
        self.assertEqual(MPDSRCase.objects.count(), 2,
                         'the two forms must produce two separate cases')
        hashes = set(MPDSRCase.objects.values_list('case_hash', flat=True))
        self.assertEqual(len(hashes), 2, 'case_hash must be unique per form')

    def test_same_serial_across_two_districts_does_not_collide(self):
        r1 = handle_ciprb_mpdsr_community_maternal(
            _payload(_id='900003', district='gaibandha'), None, None)
        r2 = handle_ciprb_mpdsr_community_maternal(
            _payload(_id='900004', district='sunamganj'), None, None)
        self.assertEqual((r1.status_code, r2.status_code), (200, 200))
        self.assertEqual(MPDSRCase.objects.count(), 2)

    def test_three_forms_one_serial(self):
        for i, fn in enumerate((handle_ciprb_mpdsr_community_maternal,
                                handle_ciprb_mpdsr_community_neonatal,
                                handle_ciprb_mpdsr_facility_neonatal)):
            r = fn(_payload(_id='9100%02d' % i), None, None)
            self.assertEqual(r.status_code, 200)
        self.assertEqual(MPDSRCase.objects.count(), 3)

    def test_resubmitting_the_same_case_updates_not_duplicates(self):
        handle_ciprb_mpdsr_community_maternal(_payload(_id='900005'), None, None)
        handle_ciprb_mpdsr_community_maternal(
            _payload(_id='900005', upazila='Sadar'), None, None)
        self.assertEqual(MPDSRCase.objects.count(), 1, 'a retry must upsert')
        self.assertEqual(MPDSRCase.objects.first().upazila, 'Sadar')

    def test_legacy_bare_serial_row_still_upserts(self):
        """Rows written before the fix hold a bare serial. A new submission for
        that same case must update it, not spawn a duplicate — and should
        migrate the key on the way through."""
        handle_ciprb_mpdsr_community_maternal(_payload(_id='900006'), None, None)
        case = MPDSRCase.objects.get()
        case.case_hash = '21'          # simulate a pre-fix row
        case.save()

        handle_ciprb_mpdsr_community_maternal(
            _payload(_id='900006', upazila='Palashbari'), None, None)
        self.assertEqual(MPDSRCase.objects.count(), 1, 'legacy row was duplicated')
        case.refresh_from_db()
        self.assertEqual(case.upazila, 'Palashbari')
        self.assertNotEqual(case.case_hash, '21',
                            'the key should migrate to the namespaced form')
