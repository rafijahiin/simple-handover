"""
Server-side fistula patient-ID issuance (mirrors the Bandhu Mother List tests).

Since 2026-08-10 the Suspected-stage form sends patient_code_final EMPTY and
the webhook allocates <district-code>-NNNN itself — the client-side pulldata
duplicate check had a CSV-staleness window that let 2-0028 be registered twice
on 2026-08-08.
"""
from unittest import mock

from django.test import TestCase

from fistula.ciprb_models import CIPRBFistulaCase
from programs.ciprb_handlers import handle_ciprb_fistula


def _suspected(name='Amena Begum', district='bhola', kobo_id='900001', **extra):
    p = {
        '_id': kobo_id,
        'stage': 'suspected',
        'district': district,
        'name': name,
        'case_serial': '61',
        'age': '35',
        'suspected_date': '2026-08-10',
        '_submitted_by': 'ciprb_field',
        'patient_code_final': '',
    }
    p.update(extra)
    return p


@mock.patch('programs.ciprb_handlers._writeback_kobo_id')
class FistulaIdAllocationTest(TestCase):

    def test_blank_code_gets_next_district_serial(self, wb):
        CIPRBFistulaCase.objects.create(
            patient_code='2-0028', organisation='CIPRB',
            district='Bhola', name='Shahida Akhtar')
        resp = handle_ciprb_fistula(_suspected(), lat=None, lng=None)
        self.assertLess(resp.status_code, 300, resp.content)
        case = CIPRBFistulaCase.objects.get(name='Amena Begum')
        self.assertEqual(case.patient_code, '2-0029')
        wb.assert_called_once_with(
            mock.ANY, '900001', '2-0029', field_path='patient_code_final')

    def test_districts_number_independently(self, wb):
        handle_ciprb_fistula(_suspected(kobo_id='900001'), lat=None, lng=None)
        handle_ciprb_fistula(
            _suspected(name='Rahima', district='sunamganj', kobo_id='900002'),
            lat=None, lng=None)
        codes = set(CIPRBFistulaCase.objects.values_list(
            'patient_code', flat=True))
        self.assertEqual(codes, {'2-0001', '1-0001'})

    def test_two_registrations_never_share_an_id(self, wb):
        handle_ciprb_fistula(_suspected(kobo_id='900001'), lat=None, lng=None)
        handle_ciprb_fistula(
            _suspected(name='Shahida Akhtar', kobo_id='900002'),
            lat=None, lng=None)
        codes = list(CIPRBFistulaCase.objects.values_list(
            'patient_code', flat=True))
        self.assertEqual(len(codes), len(set(codes)))
        self.assertEqual(sorted(codes), ['2-0001', '2-0002'])

    def test_webhook_redelivery_does_not_burn_a_second_id(self, wb):
        p = _suspected()
        handle_ciprb_fistula(p, lat=None, lng=None)
        handle_ciprb_fistula(p, lat=None, lng=None)   # Kobo retry, same _id
        self.assertEqual(CIPRBFistulaCase.objects.count(), 1)
        self.assertEqual(
            CIPRBFistulaCase.objects.get().patient_code, '2-0001')

    def test_typed_code_from_old_form_version_still_honoured(self, wb):
        resp = handle_ciprb_fistula(
            _suspected(patient_code_final='2-0044'), lat=None, lng=None)
        self.assertLess(resp.status_code, 300, resp.content)
        self.assertEqual(
            CIPRBFistulaCase.objects.get().patient_code, '2-0044')
        wb.assert_not_called()

    def test_ten_prefix_does_not_collide_with_one(self, wb):
        # Dhaka is 10-; a Sunamganj (1-) allocation must not read 10- serials.
        CIPRBFistulaCase.objects.create(
            patient_code='10-0500', organisation='CIPRB',
            district='Dhaka', name='X')
        handle_ciprb_fistula(
            _suspected(name='Rahima', district='sunamganj'),
            lat=None, lng=None)
        self.assertEqual(
            CIPRBFistulaCase.objects.get(name='Rahima').patient_code,
            '1-0001')

    def test_unknown_district_is_400_not_500(self, wb):
        resp = handle_ciprb_fistula(
            _suspected(district='narnia'), lat=None, lng=None)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(CIPRBFistulaCase.objects.count(), 0)
