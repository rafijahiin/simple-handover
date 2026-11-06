"""Every form goes through the approval queue — no auto-approve bypasses.

Closes the auto-approve paths (Rafi: everything in the site must be approved):
  - Bandhu Mother List registration (was auto-approved like PHD used to be)
  - PHD monthly counselling summary (was auto-approved as an aggregate)
and proves field logging is NOT blocked while a registration is PENDING (the
just-registered mother stays in the pulldata lookup CSV until she is REJECTED)."""
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from programs.bandhu_handlers import handle_bandhu_mother_list
from programs.phd_handlers import _phd_counselling
from programs.management.commands.export_bandhu_clients import build_csv
from programs.models import ServiceCenter, Client, PHDCounsellingReport
from accounts.models import User


def _center(org, code):
    return ServiceCenter.objects.create(
        organisation=org, name=f'{org} centre', code=code,
        center_type=ServiceCenter.DIC, district='Dhaka', is_active=True,
    )


class BandhuRegistrationAutoApproveTest(TestCase):
    """Bandhu Mother List registration is AUTO-APPROVED (Rafi 2026-06-30): the
    field manages its own registry and the service forms' pulldata must find a
    client the instant she registers. (PHD FSW registration is manager-approved
    — partner-specific.)"""
    def setUp(self):
        cache.clear()
        self.center = _center('Bandhu', 'BAN-001')

    def _register(self, kobo_id='5001', mlid='01-0001', name='Asha'):
        payload = {
            'center_code': 'BAN-001',
            'ml_id_no': mlid, 'ml_name': name, 'ml_gender': '05',
            '_id': kobo_id, '_submitted_by': 'bandhu_worker',
        }
        return handle_bandhu_mother_list(payload, lat=23.7, lng=90.4)

    def test_registration_auto_approved(self):
        resp = self._register()
        self.assertEqual(resp.status_code, 201)
        c = Client.objects.get(client_id='01-0001')
        self.assertEqual(c.approval_status, Client.APPROVED)

    def test_registered_client_is_in_lookup_csv(self):
        self._register(name='Asha')
        csv_bytes, n = build_csv()
        self.assertEqual(n, 1)
        self.assertIn(b'Asha', csv_bytes)


class PHDCounsellingApprovalTest(TestCase):
    def setUp(self):
        cache.clear()
        self.center = _center('PHD', 'PHD-001')

    def _report(self, kobo_id='6001'):
        payload = {
            'center_code': 'PHD-001',
            'counsel_date': '2026-06-01', 'counsel_prepared_by': 'Counsellor',
            'counsel_total': '12', 'counsel_hiv_test': '4',
            '_id': kobo_id, '_submitted_by': 'phd_counsellor',
        }
        return _phd_counselling(payload, lat=23.7, lng=90.4)

    def test_counselling_report_lands_pending(self):
        resp = self._report()
        self.assertEqual(resp.status_code, 201)
        r = PHDCounsellingReport.objects.get()
        self.assertEqual(r.approval_status, PHDCounsellingReport.PENDING)

    def test_counselling_report_surfaces_in_queue(self):
        self._report()
        dev = User.objects.create_user(
            email='dev@x.org', password='Str0ng-Passw0rd-2026', full_name='Dev',
            organisation='CIPRB', role='developer',
        )
        c = APIClient()
        c.force_authenticate(dev)
        r = c.get('/api/programs/pending-approvals/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('counselling_report', str(r.content))


class BandhuClientApproveButtonTest(TestCase):
    """Defensive regression for _apply_decision. Client is a plain
    TimestampedModel (not a SubmissionBase) with no manager-stage fields, so the
    Bandhu two-stage path used to run obj.manager_approved_by = user on it →
    AttributeError → 500. Bandhu registration now auto-approves so a Client is
    not normally queued, but the approval machinery must still never 500 on a
    non-SubmissionBase model — it must approve/reject single-stage."""
    def setUp(self):
        cache.clear()
        self.center = _center('Bandhu', 'BAN-001')
        self.mgr = User.objects.create_user(
            email='bmgr@x.org', password='Str0ng-Passw0rd-2026', full_name='B Mgr',
            organisation='Bandhu', role='manager',
        )
        self.reg = Client.objects.create(
            organisation='Bandhu', center=self.center, client_id='01-0009',
            name='Asha', approval_status=Client.PENDING,
        )

    def _post(self, action='approve'):
        c = APIClient()
        c.force_authenticate(self.mgr)
        return c.post('/api/programs/pending-approvals/', {
            'id': str(self.reg.id), 'model_type': 'client_reg', 'action': action,
            'reason': 'duplicate' if action == 'reject' else '',
        }, format='json')

    def test_manager_approve_finalises_registration(self):
        r = self._post('approve')
        self.assertEqual(r.status_code, 200, r.content)
        self.reg.refresh_from_db()
        self.assertEqual(self.reg.approval_status, Client.APPROVED)
        self.assertEqual(self.reg.approved_by, self.mgr)

    def test_manager_reject_works_too(self):
        r = self._post('reject')
        self.assertEqual(r.status_code, 200, r.content)
        self.reg.refresh_from_db()
        self.assertEqual(self.reg.approval_status, Client.REJECTED)


class StockEntryApprovalTest(TestCase):
    """StockEntry was counted by the dashboard's pending banner but missing
    from _APPROVAL_MODELS, so 51 PHD stock entries sat unapprovable and the
    SL5a-e commodity indicators (APPROVED-only) read zero while the data
    existed (found 2026-08-14). It must surface in the queue and approve."""
    def setUp(self):
        cache.clear()
        self.center = _center('PHD', 'PHD-001')
        self.mgr = User.objects.create_user(
            email='pmgr@x.org', password='Str0ng-Passw0rd-2026', full_name='P Mgr',
            organisation='PHD', role='manager',
        )
        from programs.models import StockEntry
        self.entry = StockEntry.objects.create(
            organisation='PHD', center=self.center,
            item_name='Condom (piece)', item_category=StockEntry.CONDOM,
            reporting_month='2026-07-01', quantity_issued=500,
            approval_status='PENDING',
        )

    def _client(self):
        c = APIClient()
        c.force_authenticate(self.mgr)
        return c

    def test_stock_entry_surfaces_in_queue(self):
        r = self._client().get('/api/programs/pending-approvals/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('stock_entry', str(r.content))

    def test_stock_entry_approves(self):
        r = self._client().post('/api/programs/pending-approvals/', {
            'id': str(self.entry.id), 'model_type': 'stock_entry',
            'action': 'approve', 'reason': '',
        }, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.approval_status, 'APPROVED')


class PreemptiveQueueCoverageTest(TestCase):
    """IECMaterial and GBVCornerRecord share StockEntry's failure shape
    (PENDING default + webhook-created + banner-counted): sealed before any
    field data could go invisible. Surfacing + approval must work for both."""
    def setUp(self):
        cache.clear()
        self.center = _center('PHD', 'PHD-001')
        self.mgr = User.objects.create_user(
            email='pmgr2@x.org', password='Str0ng-Passw0rd-2026', full_name='P Mgr',
            organisation='PHD', role='manager',
        )

    def _client(self):
        c = APIClient()
        c.force_authenticate(self.mgr)
        return c

    def test_iec_and_gbv_corner_surface_and_approve(self):
        from partners.models import Partner
        from programs.models import IECMaterial, GBVCornerRecord
        partner = Partner.objects.filter(code='PHD').first()
        iec = IECMaterial.objects.create(
            partner=partner, organisation='PHD', center=self.center,
            material_type=IECMaterial.DIGITAL, quantity=40,
            date_distributed='2026-08-01', district='Rajbari',
        )
        gbv = GBVCornerRecord.objects.create(
            organisation='PHD', center=self.center,
            date_of_establishment='2026-08-01',
        )
        body = str(self._client().get('/api/programs/pending-approvals/').content)
        self.assertIn('iec_material', body)
        self.assertIn('gbv_corner_record', body)
        for pk, mt, obj in ((iec.id, 'iec_material', iec),
                            (gbv.id, 'gbv_corner_record', gbv)):
            r = self._client().post('/api/programs/pending-approvals/', {
                'id': str(pk), 'model_type': mt, 'action': 'approve', 'reason': '',
            }, format='json')
            self.assertEqual(r.status_code, 200, r.content)
            obj.refresh_from_db()
            self.assertEqual(obj.approval_status, 'APPROVED')
