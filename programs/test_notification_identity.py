"""A mother and her baby are two deaths, not one.

The notification upsert keyed on (slip_variant, district, date_of_death,
deceased_name) and left case_serial in `defaults`, where it was overwritten. Any
two deaths sharing a district, a date and a mother's name therefore collapsed
into a single row. Both real collisions in the live data are exactly the pairing
MPDSR exists to count:

    Bhola 2026-05-15 'Sadia'    serial 1  = maternal death, serial 3  = stillbirth
    Bhola 2026-06-01 'Suntana'  serial 34 = stillbirth,     serial 41 = neonatal

One death vanished from surveillance in each pair, and the survivor's
death_kind was decided by whichever slip arrived last.
"""
from django.test import TestCase

from mpdsr.ciprb_models import MPDSRDeathNotification
from programs.ciprb_handlers import (
    handle_ciprb_notification_slip_01,
    handle_ciprb_notification_slip_02,
)


def _slip(**over):
    base = {
        '_id': '800001',
        'district': 'bhola',
        'death_date': '2026-05-15',
        'mother_name': 'Sadia',
        'mother_age': '18',
        'upazila': 'Monpura',
        'case_serial': '1',
        'death_kind': 'maternal',
    }
    base.update(over)
    return base


class NotificationIdentityTest(TestCase):
    def test_maternal_death_and_stillbirth_same_mother_are_two_records(self):
        handle_ciprb_notification_slip_01(
            _slip(_id='800001', case_serial='1', death_kind='maternal'), None, None)
        handle_ciprb_notification_slip_01(
            _slip(_id='800002', case_serial='3', death_kind='stillbirth'), None, None)

        self.assertEqual(MPDSRDeathNotification.objects.count(), 2,
                         'the stillbirth overwrote the maternal death')
        kinds = set(MPDSRDeathNotification.objects.values_list('death_kind', flat=True))
        self.assertEqual(kinds, {'maternal', 'stillbirth'})

    def test_stillbirth_and_neonatal_same_mother_are_two_records(self):
        base = dict(district='bhola', death_date='2026-06-01',
                    mother_name='Suntana', mother_age='30', upazila='Sodor')
        handle_ciprb_notification_slip_02(
            dict(base, _id='807058755', case_serial='34', death_kind='stillbirth'), None, None)
        handle_ciprb_notification_slip_02(
            dict(base, _id='807113268', case_serial='41', death_kind='neonatal'), None, None)

        self.assertEqual(MPDSRDeathNotification.objects.count(), 2)
        serials = set(MPDSRDeathNotification.objects.values_list('case_serial', flat=True))
        self.assertEqual(serials, {'34', '41'})

    def test_a_genuine_resubmission_still_updates_one_row(self):
        handle_ciprb_notification_slip_01(_slip(_id='800003'), None, None)
        handle_ciprb_notification_slip_01(
            _slip(_id='800003', upazila='Corrected'), None, None)
        self.assertEqual(MPDSRDeathNotification.objects.count(), 1,
                         'a retry must upsert, not duplicate')
        self.assertEqual(MPDSRDeathNotification.objects.get().upazila, 'Corrected')

    def test_blank_serial_falls_back_to_the_submission_id(self):
        """Without a serial, two different deaths must still not merge — and a
        retry of the same submission must still update its own row."""
        handle_ciprb_notification_slip_01(_slip(_id='800004', case_serial=''), None, None)
        handle_ciprb_notification_slip_01(_slip(_id='800005', case_serial=''), None, None)
        self.assertEqual(MPDSRDeathNotification.objects.count(), 2)

        handle_ciprb_notification_slip_01(
            _slip(_id='800004', case_serial='', village='Retried'), None, None)
        self.assertEqual(MPDSRDeathNotification.objects.count(), 2, 'retry duplicated')

    def test_a_legacy_blank_serial_row_is_updated_not_duplicated(self):
        """Rows written before case_serial joined the identity still hold ''.
        Re-delivering that slip must UPDATE the existing row — matching only the
        new 'kobo:<id>' key created a second row for the same death, which is
        exactly what happened to the Ayrin and Moriom Begum notifications."""
        handle_ciprb_notification_slip_01(_slip(_id='800007', case_serial=''), None, None)
        legacy = MPDSRDeathNotification.objects.get()
        legacy.case_serial = ''            # simulate the pre-fix row
        legacy.approval_status = 'APPROVED'
        legacy.save()

        handle_ciprb_notification_slip_01(_slip(_id='800007', case_serial=''), None, None)
        self.assertEqual(MPDSRDeathNotification.objects.count(), 1,
                         'the legacy row was duplicated instead of updated')
        legacy.refresh_from_db()
        self.assertEqual(legacy.approval_status, 'APPROVED',
                         'an update must not reset an approved record to pending')

    def test_new_notifications_are_held_for_approval(self):
        handle_ciprb_notification_slip_01(_slip(_id='800006'), None, None)
        self.assertEqual(MPDSRDeathNotification.objects.get().approval_status, 'PENDING')
