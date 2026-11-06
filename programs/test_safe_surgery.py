"""
Safe Surgery Checklist (CIPRB-11) webhook handler + phase scoring.

Covers the behaviour Tanjina asked for: an automatic operation ID, and the
three WHO phases (Sign In / Time Out / Sign Out) scored to a per-phase
completion state so compliance is trackable at a glance.
"""
from unittest import mock

from django.test import TestCase

from mpdsr.ciprb_models import SurgeryChecklist, SURGERY_PHASE_ITEMS
from programs.ciprb_handlers import handle_ciprb_safe_surgery


def _full_payload(kobo_id='700001', district='dhaka', **overrides):
    """A complete, fully-compliant checklist: every phase item answered with a
    non-'not_done' value."""
    p = {
        '_id': kobo_id,
        '_submitted_by': 'ciprb_ot',
        'district': district,
        'collection_date': '2026-10-19',
        'facility_name': 'Dhaka Medical College Hospital',
        'ward_unit': 'OT-2',
        'operation_name': 'Caesarean section',
        'op_datetime': '2026-10-19T14:30:00.000+06:00',
        'surgeon': 'Dr. Rahman',
        'anesthesiologist': 'Dr. Akter',
        'patient_name': 'Jane Patient',
        'enumerator_name': 'OT Nurse',
    }
    for name in SURGERY_PHASE_ITEMS['signin']:
        p[name] = 'yes'
    for name in SURGERY_PHASE_ITEMS['timeout']:
        p[name] = 'done'
    for name in SURGERY_PHASE_ITEMS['signout']:
        p[name] = 'done'
    p.update(overrides)
    return p


@mock.patch('programs.refs._writeback_kobo_id')
class SafeSurgeryHandlerTest(TestCase):

    def test_full_checklist_is_compliant_and_pending(self, wb):
        resp = handle_ciprb_safe_surgery(_full_payload(), lat=23.7, lng=90.4)
        self.assertEqual(resp.status_code, 200, resp.content)
        row = SurgeryChecklist.objects.get()
        self.assertTrue(row.signin_complete)
        self.assertTrue(row.timeout_complete)
        self.assertTrue(row.signout_complete)
        self.assertTrue(row.fully_compliant)
        self.assertEqual(row.phases_complete_count, 3)
        # Counts reflect the fixed phase sizes (maternal WHO checklist).
        self.assertEqual((row.signin_total, row.signin_done), (19, 19))
        self.assertEqual((row.timeout_total, row.timeout_done), (11, 11))
        self.assertEqual((row.signout_total, row.signout_done), (7, 7))
        # New record is held for CIPRB approval, and carries the auto operation ID.
        self.assertEqual(row.approval_status, 'PENDING')
        self.assertEqual(row.system_ref, 'SS-DH-0001')

    def test_not_done_item_breaks_only_that_phase(self, wb):
        # One Time Out step not carried out — Time Out is incomplete, the other
        # two phases still complete, so the operation is not fully compliant.
        p = _full_payload()
        p['to_skin_prep'] = 'not_done'
        handle_ciprb_safe_surgery(p, lat=None, lng=None)
        row = SurgeryChecklist.objects.get()
        self.assertTrue(row.signin_complete)
        self.assertFalse(row.timeout_complete)
        self.assertEqual((row.timeout_done, row.timeout_total), (10, 11))
        self.assertTrue(row.signout_complete)
        self.assertFalse(row.fully_compliant)
        self.assertEqual(row.phases_complete_count, 2)

    def test_blank_item_counts_as_not_done(self, wb):
        # A skipped (blank) answer must not read as a completed step.
        p = _full_payload()
        p['si_airway'] = ''
        handle_ciprb_safe_surgery(p, lat=None, lng=None)
        row = SurgeryChecklist.objects.get()
        self.assertFalse(row.signin_complete)
        self.assertEqual((row.signin_done, row.signin_total), (18, 19))

    def test_no_item_variant_still_counts_as_addressed(self, wb):
        # 'no' / 'na' answers mean the check happened (WHO compliance = the
        # check was done, not that the answer was yes) — phase stays complete.
        p = _full_payload()
        p['si_allergy'] = 'no'
        p['si_airway'] = 'no'
        p['si_antacid'] = 'na'
        p['si_blood_available'] = 'na'
        handle_ciprb_safe_surgery(p, lat=None, lng=None)
        row = SurgeryChecklist.objects.get()
        self.assertTrue(row.fully_compliant)

    def test_redelivery_is_idempotent(self, wb):
        p = _full_payload()
        handle_ciprb_safe_surgery(p, lat=None, lng=None)
        handle_ciprb_safe_surgery(p, lat=None, lng=None)
        self.assertEqual(SurgeryChecklist.objects.count(), 1)
        self.assertEqual(SurgeryChecklist.objects.get().system_ref, 'SS-DH-0001')

    def test_sequential_ids_per_district(self, wb):
        handle_ciprb_safe_surgery(_full_payload(kobo_id='700001'), None, None)
        handle_ciprb_safe_surgery(_full_payload(kobo_id='700002'), None, None)
        handle_ciprb_safe_surgery(
            _full_payload(kobo_id='700003', district='bhola'), None, None)
        refs = set(SurgeryChecklist.objects.values_list('system_ref', flat=True))
        self.assertEqual(refs, {'SS-DH-0001', 'SS-DH-0002', 'SS-BH-0001'})

    def test_operation_name_required(self, wb):
        p = _full_payload()
        p['operation_name'] = ''
        resp = handle_ciprb_safe_surgery(p, None, None)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(SurgeryChecklist.objects.count(), 0)

    def test_patient_name_stored_but_absent_from_dashboard(self, wb):
        # patient_name is persisted (encrypted) for the approval drawer, but the
        # dashboard aggregate must never expose it.
        handle_ciprb_safe_surgery(_full_payload(), None, None)
        row = SurgeryChecklist.objects.get()
        self.assertEqual(row.patient_name, 'Jane Patient')
        # Only APPROVED operations reach the at-a-glance dashboard.
        row.approval_status = 'APPROVED'
        row.save(update_fields=['approval_status'])

        from accounts.models import User
        from mpdsr.views import safe_surgery
        from rest_framework.test import APIRequestFactory, force_authenticate
        u = User.objects.create_user(
            email='dev@x.test', password='pass', full_name='Dev',
            organisation='UNFPA', role='developer')
        req = APIRequestFactory().get('/api/mpdsr/safe-surgery/')
        force_authenticate(req, user=u)
        resp = safe_surgery(req)
        self.assertEqual(resp.status_code, 200, resp.data)
        body = resp.data
        self.assertEqual(body['total'], 1)
        self.assertEqual(body['compliant'], 1)
        self.assertEqual(body['compliance_pct'], 100.0)
        self.assertEqual(body['phase_complete'],
                         {'signin': 1, 'timeout': 1, 'signout': 1})
        self.assertEqual(body['by_district'], {'Dhaka': 1})
        op = body['operations'][0]
        self.assertEqual(op['system_ref'], 'SS-DH-0001')
        self.assertTrue(op['fully_compliant'])
        self.assertNotIn('patient_name', op)
