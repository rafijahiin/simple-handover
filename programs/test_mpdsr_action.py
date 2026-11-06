"""
CIPRB-10 MPDSR Action-Plan handler — regression tests for the 2026-06 hardening:
idempotency, district-scoped upsert, collision reallocation, no-phantom-stub,
status/completion coupling, fail-closed default, and the PENDING-inclusive CSV.
Plus the dashboard action-aggregates endpoint contract.
"""
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import Organisation, Role, User
from mpdsr.models import (MPDSRAction, ActionStatus, STUB_ACTIVITY_SENTINEL,
                          DISTRICT_ACTION_CODE)
from unittest import mock

from programs.ciprb_handlers import handle_ciprb_mpdsr_action_plan
from programs.management.commands.export_mpdsr_actions import build_csv


def _new_plan(action_id, *, district='dhaka', activity='Train CHCPs',
              who='Alice', sub_id='S1', status=''):
    return handle_ciprb_mpdsr_action_plan({
        'ap_mode': 'new_plan',
        'district': district,
        'action_id': action_id,
        'act_activity': activity,
        'rp_section': 'system_strengthening',
        'act_status': status,
        'enumerator_name': who,
        '_id': sub_id,
        '_submitted_by': 'kobo',
    }, None, None)


def _update(action_id, *, district='dhaka', new_status='in_progress',
            completion='50', who='Bob', sub_id='U1'):
    return handle_ciprb_mpdsr_action_plan({
        'ap_mode': 'update_action',
        'district': district,
        'ap_action_sel': action_id,
        'ap_new_status': new_status,
        'ap_new_completion': completion,
        'enumerator_name': who,
        '_id': sub_id,
        '_submitted_by': 'kobo',
    }, None, None)


class NewPlanTest(TestCase):
    def test_new_plan_creates_pending_with_creator(self):
        r = _new_plan('DH-001')
        self.assertEqual(r.status_code, 200)
        act = MPDSRAction.objects.get(action_id='DH-001')
        self.assertEqual(act.district, 'Dhaka')
        self.assertEqual(act.approval_status, 'PENDING')
        self.assertEqual(act.creator_name, 'Alice')
        self.assertEqual(act.organisation, 'CIPRB')

    def test_default_approval_status_is_pending(self):
        # Fail-closed: any creation path that forgets to set it lands PENDING.
        act = MPDSRAction.objects.create(
            action_id='DH-009', district='Dhaka',
            section='system_strengthening', activity='x')
        self.assertEqual(act.approval_status, 'PENDING')


class IdempotencyTest(TestCase):
    def test_redelivery_does_not_revert_approval(self):
        _new_plan('DH-001', sub_id='X1')
        act = MPDSRAction.objects.get(action_id='DH-001')
        act.approval_status = 'APPROVED'
        act.save()
        audit_len = len(act.audit_trail)
        # Kobo re-delivers the SAME _id.
        r = _new_plan('DH-001', sub_id='X1', activity='changed')
        self.assertEqual(r.status_code, 200)
        act.refresh_from_db()
        self.assertEqual(act.approval_status, 'APPROVED')      # not reverted
        self.assertEqual(act.activity, 'Train CHCPs')          # not overwritten
        self.assertEqual(len(act.audit_trail), audit_len)      # not double-logged


class CollisionTest(TestCase):
    def test_different_creator_same_id_is_reallocated(self):
        _new_plan('DH-001', who='Alice', activity='Alice action', sub_id='A1')
        r = _new_plan('DH-001', who='Bob', activity='Bob action', sub_id='B1')
        self.assertEqual(r.status_code, 200)
        # Both actions survive; Bob's was reallocated to a fresh id.
        self.assertEqual(MPDSRAction.objects.count(), 2)
        ids = set(MPDSRAction.objects.values_list('action_id', flat=True))
        self.assertEqual(ids, {'DH-001', 'DH-002'})
        alice = MPDSRAction.objects.get(action_id='DH-001')
        bob = MPDSRAction.objects.get(action_id='DH-002')
        self.assertEqual(alice.activity, 'Alice action')
        self.assertEqual(bob.activity, 'Bob action')
        self.assertEqual(bob.creator_name, 'Bob')

    def test_same_creator_reregistration_updates_in_place(self):
        _new_plan('DH-001', who='Alice', activity='v1', sub_id='A1')
        _new_plan('DH-001', who='Alice', activity='v2', sub_id='A2')
        self.assertEqual(MPDSRAction.objects.count(), 1)
        act = MPDSRAction.objects.get(action_id='DH-001')
        self.assertEqual(act.activity, 'v2')
        self.assertEqual(act.creator_name, 'Alice')   # immutable


class UpdateActionTest(TestCase):
    def test_unknown_id_is_ignored_no_phantom(self):
        r = _update('DH-404')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(MPDSRAction.objects.count(), 0)        # no stub row

    def test_update_advances_and_repends(self):
        _new_plan('DH-001', sub_id='A1')
        act = MPDSRAction.objects.get(action_id='DH-001')
        act.approval_status = 'APPROVED'
        act.save()
        r = _update('DH-001', new_status='in_progress', completion='50',
                    who='Carol', sub_id='U1')
        self.assertEqual(r.status_code, 200)
        act.refresh_from_db()
        self.assertEqual(act.status, 'in_progress')
        self.assertEqual(act.completion_pct, 50)
        self.assertEqual(act.approval_status, 'PENDING')        # re-enters gate
        self.assertIsNone(act.approved_by)
        self.assertEqual(act.last_edited_by_name, 'Carol')

    def test_status_completion_coupling(self):
        _new_plan('DH-001', sub_id='A1')
        # Implemented forces 100%.
        _update('DH-001', new_status='implemented', completion='0', sub_id='U1')
        act = MPDSRAction.objects.get(action_id='DH-001')
        self.assertEqual(act.completion_pct, 100)
        self.assertEqual(act.status, 'implemented')
        # 100% forces Implemented.
        _update('DH-001', new_status='in_progress', completion='100', sub_id='U2')
        act.refresh_from_db()
        self.assertEqual(act.status, 'implemented')


class CsvTest(TestCase):
    def test_pending_action_is_in_lookup_csv(self):
        _new_plan('DH-001', sub_id='A1')                        # PENDING
        csv_bytes, n = build_csv()
        self.assertIn('DH-001', csv_bytes.decode('utf-8'))
        self.assertGreaterEqual(n, 1)
        self.assertIn('district_slug', csv_bytes.decode('utf-8').splitlines()[0])

    def test_stub_is_excluded_from_csv(self):
        MPDSRAction.objects.create(
            action_id='DH-777', district='Dhaka', section='system_strengthening',
            activity=STUB_ACTIVITY_SENTINEL, approval_status='PENDING')
        csv_bytes, n = build_csv()
        self.assertNotIn('DH-777', csv_bytes.decode('utf-8'))


class ActionAggregatesEndpointTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse('mpdsr-action-aggregates')
        self.ciprb = User.objects.create_user(
            email='lead@ciprb.org', password='p', full_name='Lead',
            organisation=Organisation.CIPRB, role=Role.ORG_LEAD)

    def _action(self, action_id, district, pct, status, approval='APPROVED',
                activity='Train CHCPs'):
        return MPDSRAction.objects.create(
            action_id=action_id, district=district, section='system_strengthening',
            activity=activity, completion_pct=pct, status=status,
            approval_status=approval)

    def test_requires_mpdsr_access(self):
        phd = User.objects.create_user(
            email='m@phd.org', password='p', full_name='M',
            organisation=Organisation.PHD, role=Role.MANAGER)
        self.client.force_authenticate(user=phd)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_aggregates_shape_and_rollups(self):
        self._action('DH-001', 'Dhaka', 100, 'implemented')
        self._action('DH-002', 'Dhaka', 0, 'pending')
        self._action('RA-001', 'Rangpur', 50, 'in_progress')
        self._action('RA-002', 'Rangpur', 0, 'pending', approval='PENDING')   # excluded
        self._action('RA-003', 'Rangpur', 0, 'pending', activity=STUB_ACTIVITY_SENTINEL)  # stub excluded
        self.client.force_authenticate(user=self.ciprb)
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        d = r.data
        self.assertEqual(d['total'], 3)                       # only APPROVED non-stub
        self.assertEqual(d['overall_pct'], 50)                # (100+0+50)/3
        self.assertEqual({a['action_id'] for a in d['actions']},
                         {'DH-001', 'DH-002', 'RA-001'})
        self.assertEqual(len(d['by_status']), len(ActionStatus.choices))
        dist = {row['key']: row for row in d['by_district']}
        self.assertEqual(dist['Dhaka']['n'], 2)
        self.assertEqual(dist['Dhaka']['pct'], 50)            # (100+0)/2

    def test_district_filter(self):
        self._action('DH-001', 'Dhaka', 100, 'implemented')
        self._action('RA-001', 'Rangpur', 50, 'in_progress')
        self.client.force_authenticate(user=self.ciprb)
        r = self.client.get(self.url, {'districts': 'Rangpur'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['total'], 1)
        self.assertEqual(r.data['actions'][0]['action_id'], 'RA-001')


class MapIntegrityTest(TestCase):
    def test_all_district_codes_unique(self):
        self.assertEqual(len(set(DISTRICT_ACTION_CODE.values())),
                         len(DISTRICT_ACTION_CODE))

    def test_next_action_id_is_three_digit_canonical(self):
        self.assertEqual(MPDSRAction.next_action_id('Rangpur'), 'RA-001')
        MPDSRAction.objects.create(action_id='RA-001', district='Rangpur',
                                   section='system_strengthening', activity='x')
        self.assertEqual(MPDSRAction.next_action_id('Rangpur'), 'RA-002')


class ModifiableFactorTest(TestCase):
    """Master Table 2's first column (common modifiable factor) must reach
    MPDSRAction.sub_category for BOTH factor sections, and must not leak into
    the System-Strengthening vocabulary."""

    @staticmethod
    def _plan(action_id, section, *, factor='', other='', subcat=''):
        return handle_ciprb_mpdsr_action_plan({
            'ap_mode': 'new_plan',
            'district': 'dhaka',
            'action_id': action_id,
            'act_activity': 'Strengthen referral network and transport support',
            'rp_section': section,
            'act_subcat': subcat,
            'act_factor': factor,
            'act_factor_other': other,
            'enumerator_name': 'Alice',
            '_id': 'F' + action_id,
            '_submitted_by': 'kobo',
        }, None, None)

    def test_community_va_factor_is_stored(self):
        self._plan('DH-101', 'community_va', factor='referral_linkages')
        act = MPDSRAction.objects.get(action_id='DH-101')
        self.assertEqual(act.section, 'community_va')
        self.assertEqual(act.sub_category, 'referral_linkages')
        self.assertEqual(act.sub_category_label, 'Inadequate referral linkages')

    def test_facility_dr_uses_the_same_factor_list(self):
        self._plan('DH-102', 'facility_dr', factor='pph_management')
        act = MPDSRAction.objects.get(action_id='DH-102')
        self.assertEqual(act.sub_category, 'pph_management')
        self.assertEqual(act.sub_category_label,
                         'Management of Postpartum Haemorrhage (PPH)')

    def test_other_stores_the_districts_own_wording(self):
        self._plan('DH-103', 'community_va', factor='other',
                   other='Delay in arranging transport at night')
        act = MPDSRAction.objects.get(action_id='DH-103')
        self.assertEqual(act.sub_category, 'Delay in arranging transport at night')
        # Unknown code -> shown as typed, never blank.
        self.assertEqual(act.sub_category_label,
                         'Delay in arranging transport at night')

    def test_other_wording_is_truncated_to_column_width(self):
        self._plan('DH-104', 'facility_dr', factor='other', other='x' * 300)
        act = MPDSRAction.objects.get(action_id='DH-104')
        self.assertEqual(len(act.sub_category), 120)

    def test_system_strengthening_still_uses_act_subcat(self):
        # A stray act_factor on an SS action must be ignored, not overwrite.
        self._plan('DH-105', 'system_strengthening',
                   subcat='community_death_review', factor='pph_management')
        act = MPDSRAction.objects.get(action_id='DH-105')
        self.assertEqual(act.sub_category, 'community_death_review')

    def test_factor_reaches_the_action_aggregates_api(self):
        self._plan('DH-106', 'community_va', factor='home_delivery_tba')
        MPDSRAction.objects.filter(action_id='DH-106').update(
            approval_status='APPROVED')
        user = User.objects.create_user(
            email='factor@ciprb.org', password='p', full_name='Lead',
            organisation=Organisation.CIPRB, role=Role.ORG_LEAD)
        c = APIClient()
        c.force_authenticate(user=user)
        res = c.get(reverse('mpdsr-action-aggregates'))
        self.assertEqual(res.status_code, 200)
        row = next(a for a in res.json()['actions'] if a['action_id'] == 'DH-106')
        self.assertEqual(row['sub_category'], 'home_delivery_tba')
        self.assertEqual(row['sub_category_label'], 'Home delivery by TBA')


class ServerIssuedActionIdTest(TestCase):
    """A blank action_id must be issued by the server, not rejected.

    Rina in Sunamganj could only guess a serial, typed SU-001, and the form's
    duplicate rule blocked her because SU-001 to SU-023 already existed
    (2026-08-20). No field worker can know which serials a district has used,
    so the server now allocates the next free one.
    """
    def _blank(self, district='sunamganj', who='Rina', sub_id='B1',
               activity='Notify maternal deaths within 24 hours'):
        return handle_ciprb_mpdsr_action_plan({
            'ap_mode': 'new_plan',
            'district': district,
            'action_id': '',
            'act_activity': activity,
            'rp_section': 'system_strengthening',
            'enumerator_name': who,
            '_id': sub_id,
            '_submitted_by': 'kobo',
        }, None, None)

    def test_blank_id_is_issued_not_rejected(self):
        resp = self._blank()
        self.assertEqual(resp.status_code, 200, resp.content)
        act = MPDSRAction.objects.get()
        self.assertEqual(act.action_id, 'SU-001')
        self.assertEqual(act.district, 'Sunamganj')
        self.assertEqual(act.creator_name, 'Rina')

    def test_issued_id_continues_after_existing_serials(self):
        for n in range(1, 24):
            MPDSRAction.objects.create(action_id='SU-%03d' % n,
                                       district='Sunamganj', organisation='CIPRB',
                                       activity='existing %d' % n)
        resp = self._blank()
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(
            MPDSRAction.objects.get(creator_name='Rina').action_id, 'SU-024')

    def test_two_blank_submissions_get_different_ids(self):
        self._blank(sub_id='B1', who='Rina')
        self._blank(sub_id='B2', who='Karim', activity='Second action')
        ids = sorted(MPDSRAction.objects.values_list('action_id', flat=True))
        self.assertEqual(ids, ['SU-001', 'SU-002'])

    def test_typed_id_from_an_older_phone_still_works(self):
        resp = _new_plan('SU-050', district='sunamganj', who='Rina', sub_id='T1')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(MPDSRAction.objects.get().action_id, 'SU-050')

    def test_districts_number_independently(self):
        self._blank(district='sunamganj', sub_id='B1')
        self._blank(district='kurigram', sub_id='B2', who='Karim')
        ids = set(MPDSRAction.objects.values_list('action_id', flat=True))
        self.assertEqual(ids, {'SU-001', 'KU-001'})


class IssuedActionIdWriteBackTest(TestCase):
    """The issued id must be written back onto the Kobo submission, or the
    district can never see its own Action ID without the dashboard."""

    def _blank(self, sub_id='W1'):
        return handle_ciprb_mpdsr_action_plan({
            'ap_mode': 'new_plan', 'district': 'sunamganj', 'action_id': '',
            'act_activity': 'Notify maternal deaths', 'rp_section': 'system_strengthening',
            'enumerator_name': 'Rina', '_id': sub_id, '_submitted_by': 'kobo',
        }, None, None)

    @mock.patch('programs.ciprb_handlers._writeback_kobo_id')
    def test_issued_id_is_written_back(self, wb):
        self._blank()
        wb.assert_called_once()
        args, kwargs = wb.call_args
        self.assertEqual(args[1], 'W1')          # the Kobo submission id
        self.assertEqual(args[2], 'SU-001')      # the issued action id
        self.assertEqual(kwargs['field_path'], 'action_id')

    @mock.patch('programs.ciprb_handlers._writeback_kobo_id')
    def test_typed_id_is_not_written_back(self, wb):
        _new_plan('SU-050', district='sunamganj', who='Rina', sub_id='T9')
        wb.assert_not_called()

    @mock.patch('programs.ciprb_handlers._writeback_kobo_id',
                side_effect=RuntimeError('kobo down'))
    def test_writeback_failure_does_not_lose_the_action(self, wb):
        with self.assertRaises(RuntimeError):
            self._blank()
        # The action itself was committed before the write-back was attempted.
        self.assertEqual(MPDSRAction.objects.count(), 1)
