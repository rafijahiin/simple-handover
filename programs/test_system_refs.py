"""
System reference numbers (<FORM>-<DIST>-<NNNN>) on MPDSR cases, death
notifications and near-miss records — CIPRB's "automatic ID on every form"
(2026-08-11).
"""
from unittest import mock

from django.test import TestCase

from mpdsr.ciprb_models import MPDSRDeathNotification, MaternalNearMissCase
from mpdsr.models import MPDSRCase
from programs.ciprb_handlers import (handle_ciprb_mpdsr_community_maternal,
                                     handle_ciprb_near_miss,
                                     handle_ciprb_notification_slip_01)
from programs.refs import allocate_system_ref


def _slip(name='Amena', kobo_id='910001', serial='7', **extra):
    p = {'_id': kobo_id, 'district': 'bhola', 'death_date': '2026-08-01',
         'mother_name': name, 'case_serial': serial, 'death_kind': 'maternal',
         'slip_date': '2026-08-02', '_submitted_by': 'ciprb_field'}
    p.update(extra)
    return p


@mock.patch('programs.refs._writeback_kobo_id')
class SystemRefTest(TestCase):

    def test_notification_gets_sequential_district_ref(self, wb):
        handle_ciprb_notification_slip_01(_slip(), lat=None, lng=None)
        handle_ciprb_notification_slip_01(
            _slip(name='Rahima', kobo_id='910002', serial='8'),
            lat=None, lng=None)
        refs = sorted(MPDSRDeathNotification.objects
                      .values_list('system_ref', flat=True))
        self.assertEqual(refs, ['NS1-BH-0001', 'NS1-BH-0002'])
        wb.assert_called()  # ref goes back onto the Kobo record

    def test_redelivery_keeps_the_same_ref(self, wb):
        p = _slip()
        handle_ciprb_notification_slip_01(p, lat=None, lng=None)
        handle_ciprb_notification_slip_01(p, lat=None, lng=None)
        self.assertEqual(MPDSRDeathNotification.objects.count(), 1)
        self.assertEqual(MPDSRDeathNotification.objects.get().system_ref,
                         'NS1-BH-0001')

    def test_districts_number_independently(self, wb):
        handle_ciprb_notification_slip_01(_slip(), lat=None, lng=None)
        handle_ciprb_notification_slip_01(
            _slip(name='Salma', kobo_id='910003', district='sherpur'),
            lat=None, lng=None)
        refs = set(MPDSRDeathNotification.objects
                   .values_list('system_ref', flat=True))
        self.assertEqual(refs, {'NS1-BH-0001', 'NS1-SH-0001'})

    def test_mpdsr_f1_ref(self, wb):
        payload = {'_id': '910010', 'district': 'bhola',
                   'death_date': '2026-07-20', 'mother_name': 'Karima',
                   'case_serial': '3', '_submitted_by': 'ciprb_field'}
        resp = handle_ciprb_mpdsr_community_maternal(payload, lat=None, lng=None)
        self.assertLess(resp.status_code, 300, resp.content)
        case = MPDSRCase.objects.get()
        self.assertEqual(case.system_ref, 'F1-BH-0001')

    def test_near_miss_ref(self, wb):
        payload = {'_id': '910020', 'district': 'sunamganj',
                   'event_date': '2026-07-25', 'woman_name': 'Nasima',
                   'case_serial': '5', '_submitted_by': 'ciprb_field'}
        resp = handle_ciprb_near_miss(payload, lat=None, lng=None)
        self.assertLess(resp.status_code, 300, resp.content)
        self.assertEqual(MaternalNearMissCase.objects.get().system_ref,
                         'NM-SU-0001')

    def test_allocate_is_idempotent(self, wb):
        handle_ciprb_notification_slip_01(_slip(), lat=None, lng=None)
        obj = MPDSRDeathNotification.objects.get()
        self.assertEqual(allocate_system_ref(obj, 'NS1'), 'NS1-BH-0001')

    def test_unknown_district_uses_xx_not_crash(self, wb):
        obj = MPDSRDeathNotification.objects.create(
            slip_variant='01', district='Atlantis',
            date_of_death='2026-08-01', deceased_name='X', case_serial='1')
        self.assertEqual(allocate_system_ref(obj, 'NS1', writeback=False),
                         'NS1-XX-0001')
