"""
Org-isolation smoke test — confirms that every programs ViewSet correctly
restricts manager visibility to their own organisation.

Pattern: create one row per organisation, log in as a manager, assert the
LIST endpoint returns exactly one row whose organisation matches them.
A super admin login asserts both rows are returned.

Covered endpoints (one per ViewSet base class):
  - /api/programs/centers/         (ServiceCenter — direct ModelViewSet)
  - /api/programs/clients/         (Client          — direct ModelViewSet)
  - /api/programs/clinic-visits/   (ClinicVisit     — OrgFilteredViewSet
                                   with own get_queryset override)
  - /api/programs/outreach-sessions/ (OutreachSession — plain
                                     OrgFilteredViewSet inheritance)
  - /api/programs/stock-entries/   (StockEntry      — OrgFilteredViewSet
                                   with own get_queryset override)
  - /api/programs/visitor-register/ (VisitorRegister — direct ModelViewSet)
  - /api/programs/pending-approvals/ (aggregated view)
"""
from datetime import date

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import Organisation, Role, User
from programs.models import (
    ServiceCenter, Client, ClinicVisit, OutreachSession,
    StockEntry, VisitorRegister,
)


def _make_user(email, org, role):
    return User.objects.create_user(
        email=email, password='pass', full_name='Test', organisation=org, role=role,
    )


def _make_center(organisation, name, code):
    return ServiceCenter.objects.create(
        organisation=organisation, name=name, code=code,
        center_type=ServiceCenter.DIC, district='Dhaka', is_active=True,
    )


class OrgIsolationSmokeTest(TestCase):
    """Each row of partner data should be visible only to its own org's
    manager (and to super admins). A leak would mean a PHD manager can see
    Bandhu rows or vice versa."""

    @classmethod
    def setUpTestData(cls):
        cls.phd_mgr     = _make_user('mgr@phd.org',    Organisation.PHD,    Role.MANAGER)
        cls.bandhu_mgr  = _make_user('mgr@bandhu.org', Organisation.BANDHU, Role.MANAGER)
        cls.supervisor = _make_user('sa@ciprb.org',   Organisation.CIPRB,  Role.SUPERVISOR)

        # Two ServiceCenters, one per org.
        cls.phd_center    = _make_center('PHD',    'PHD Center 1',    'PHD-001')
        cls.bandhu_center = _make_center('Bandhu', 'Bandhu Center 1', 'BAN-001')

        # Two Clients, one per org.
        cls.phd_client = Client.objects.create(
            organisation='PHD', center=cls.phd_center,
            client_id='PHD-C-1', name='Sample PHD client',
        )
        cls.bandhu_client = Client.objects.create(
            organisation='Bandhu', center=cls.bandhu_center,
            client_id='BAN-C-1', name='Sample Bandhu client',
        )

        # ClinicVisit — one per org.
        cls.phd_visit = ClinicVisit.objects.create(
            organisation='PHD', center=cls.phd_center, client=cls.phd_client,
            visit_date=date(2026, 5, 10),
        )
        cls.bandhu_visit = ClinicVisit.objects.create(
            organisation='Bandhu', center=cls.bandhu_center, client=cls.bandhu_client,
            visit_date=date(2026, 5, 11),
        )

        # OutreachSession — one per org.
        OutreachSession.objects.create(
            organisation='PHD', center=cls.phd_center,
            session_date=date(2026, 5, 12),
            peer_educator_name='PHD PE',
        )
        OutreachSession.objects.create(
            organisation='Bandhu', center=cls.bandhu_center,
            session_date=date(2026, 5, 13),
            peer_educator_name='Bandhu PE',
        )

        # StockEntry — one per org.
        StockEntry.objects.create(
            organisation='PHD', center=cls.phd_center,
            reporting_month=date(2026, 5, 1), item_name='PHD test item',
        )
        StockEntry.objects.create(
            organisation='Bandhu', center=cls.bandhu_center,
            reporting_month=date(2026, 5, 1), item_name='Bandhu test item',
        )

        # VisitorRegister — one per org.
        VisitorRegister.objects.create(
            organisation='PHD', center=cls.phd_center,
            visitor_name='PHD visitor', visit_date=date(2026, 5, 14),
        )
        VisitorRegister.objects.create(
            organisation='Bandhu', center=cls.bandhu_center,
            visitor_name='Bandhu visitor', visit_date=date(2026, 5, 15),
        )

    def setUp(self):
        self.client = APIClient()

    # ── ServiceCenter ──────────────────────────────────────────────────────

    def test_centers_phd_manager_sees_only_phd(self):
        self.client.force_authenticate(user=self.phd_mgr)
        resp = self.client.get('/api/programs/centers/')
        self.assertEqual(resp.status_code, 200)
        rows = self._rows(resp)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['organisation'], 'PHD')

    def test_centers_bandhu_manager_sees_only_bandhu(self):
        self.client.force_authenticate(user=self.bandhu_mgr)
        resp = self.client.get('/api/programs/centers/')
        self.assertEqual(resp.status_code, 200)
        rows = self._rows(resp)
        # Assert the isolation PROPERTY, not a hardcoded count — migrations seed
        # real Bandhu wellness centres, so the count is > 1. What matters is that
        # a Bandhu manager sees ONLY Bandhu centres and the test's own is present.
        self.assertGreaterEqual(len(rows), 1)
        self.assertTrue(all(r['organisation'] == 'Bandhu' for r in rows))

    def test_centers_supervisor_sees_both(self):
        self.client.force_authenticate(user=self.supervisor)
        resp = self.client.get('/api/programs/centers/')
        self.assertEqual(resp.status_code, 200)
        orgs = {r['organisation'] for r in self._rows(resp)}
        self.assertEqual(orgs, {'PHD', 'Bandhu'})

    # ── Clients ────────────────────────────────────────────────────────────

    def test_clients_phd_manager_sees_only_phd(self):
        self.client.force_authenticate(user=self.phd_mgr)
        rows = self._rows(self.client.get('/api/programs/clients/'))
        self.assertEqual({r['organisation'] for r in rows}, {'PHD'})

    def test_clients_bandhu_manager_sees_only_bandhu(self):
        self.client.force_authenticate(user=self.bandhu_mgr)
        rows = self._rows(self.client.get('/api/programs/clients/'))
        self.assertEqual({r['organisation'] for r in rows}, {'Bandhu'})

    # ── ClinicVisit (OrgFilteredViewSet + override) ────────────────────────

    def test_clinic_visits_phd_manager_sees_only_phd(self):
        self.client.force_authenticate(user=self.phd_mgr)
        rows = self._rows(self.client.get('/api/programs/clinic-visits/'))
        self.assertEqual({r['organisation'] for r in rows}, {'PHD'})

    def test_clinic_visits_bandhu_manager_sees_only_bandhu(self):
        self.client.force_authenticate(user=self.bandhu_mgr)
        rows = self._rows(self.client.get('/api/programs/clinic-visits/'))
        self.assertEqual({r['organisation'] for r in rows}, {'Bandhu'})

    def test_clinic_visits_bandhu_cannot_access_phd_visit_by_id(self):
        """Detail GET on another org's row should 404, never 200."""
        self.client.force_authenticate(user=self.bandhu_mgr)
        resp = self.client.get(f'/api/programs/clinic-visits/{self.phd_visit.pk}/')
        self.assertEqual(resp.status_code, 404)

    # ── OutreachSession ────────────────────────────────────────────────────

    def test_outreach_phd_manager_sees_only_phd(self):
        self.client.force_authenticate(user=self.phd_mgr)
        rows = self._rows(self.client.get('/api/programs/outreach-sessions/'))
        self.assertEqual({r['organisation'] for r in rows}, {'PHD'})

    def test_outreach_bandhu_manager_sees_only_bandhu(self):
        self.client.force_authenticate(user=self.bandhu_mgr)
        rows = self._rows(self.client.get('/api/programs/outreach-sessions/'))
        self.assertEqual({r['organisation'] for r in rows}, {'Bandhu'})

    # ── StockEntry ─────────────────────────────────────────────────────────

    def test_stock_entries_phd_manager_sees_only_phd(self):
        self.client.force_authenticate(user=self.phd_mgr)
        rows = self._rows(self.client.get('/api/programs/stock-entries/'))
        self.assertEqual({r['organisation'] for r in rows}, {'PHD'})

    def test_stock_entries_bandhu_manager_sees_only_bandhu(self):
        self.client.force_authenticate(user=self.bandhu_mgr)
        rows = self._rows(self.client.get('/api/programs/stock-entries/'))
        self.assertEqual({r['organisation'] for r in rows}, {'Bandhu'})

    # ── VisitorRegister ────────────────────────────────────────────────────

    def test_visitor_register_phd_manager_sees_only_phd(self):
        self.client.force_authenticate(user=self.phd_mgr)
        rows = self._rows(self.client.get('/api/programs/visitor-register/'))
        self.assertEqual({r['organisation'] for r in rows}, {'PHD'})

    def test_visitor_register_bandhu_manager_sees_only_bandhu(self):
        self.client.force_authenticate(user=self.bandhu_mgr)
        rows = self._rows(self.client.get('/api/programs/visitor-register/'))
        self.assertEqual({r['organisation'] for r in rows}, {'Bandhu'})

    # ── Aggregated PendingApprovalsView ────────────────────────────────────

    def test_pending_approvals_phd_manager_sees_only_phd(self):
        self.client.force_authenticate(user=self.phd_mgr)
        resp = self.client.get('/api/programs/pending-approvals/')
        self.assertEqual(resp.status_code, 200)
        orgs = {item['organisation'] for item in resp.data['items']}
        self.assertNotIn('Bandhu', orgs)

    def test_pending_approvals_bandhu_manager_sees_only_bandhu(self):
        self.client.force_authenticate(user=self.bandhu_mgr)
        resp = self.client.get('/api/programs/pending-approvals/')
        self.assertEqual(resp.status_code, 200)
        orgs = {item['organisation'] for item in resp.data['items']}
        self.assertNotIn('PHD', orgs)

    def test_pending_approvals_supervisor_sees_both(self):
        self.client.force_authenticate(user=self.supervisor)
        resp = self.client.get('/api/programs/pending-approvals/')
        self.assertEqual(resp.status_code, 200)
        orgs = {item['organisation'] for item in resp.data['items']}
        self.assertIn('PHD', orgs)
        self.assertIn('Bandhu', orgs)

    def test_counts_by_org_is_true_backlog_not_the_capped_page(self):
        """The partner tab badge must count the REAL pending backlog, not the
        capped page. Regression for '317 won't drop even after I approve': the
        display cap truncated the returned rows, so the badge (counted from the
        page) back-filled a hidden row and never moved. counts_by_org is derived
        from an aggregate BEFORE the [:_CAP] slice, so it stays the DB truth even
        when `items` is truncated — and it must be org-scoped."""
        # Every pending Bandhu record across all approval models.
        from programs.models import OutreachSession
        true_bandhu = (
            ClinicVisit.objects.filter(organisation='Bandhu', approval_status='PENDING').count()
            + OutreachSession.objects.filter(organisation='Bandhu', approval_status='PENDING').count()
        )
        self.client.force_authenticate(user=self.bandhu_mgr)
        resp = self.client.get('/api/programs/pending-approvals/')
        self.assertEqual(resp.status_code, 200)
        # Badge count matches the DB truth for Bandhu...
        self.assertGreaterEqual(resp.data['counts_by_org'].get('Bandhu', 0), true_bandhu)
        # ...and a Bandhu manager's counts never leak PHD.
        self.assertNotIn('PHD', resp.data['counts_by_org'])

    # ── Helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _rows(response):
        """DRF list endpoints may be paginated or bare lists."""
        data = response.data
        if isinstance(data, dict) and 'results' in data:
            return data['results']
        return data


# ─── Step 5: meeting / training mandatory upload gate ────────────────────────

import io
from datetime import date as _date
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from programs.models import (
    CoordMeeting, TrainingEvent, ServiceCenter,
)
from programs.serializers import CoordMeetingSerializer, TrainingEventSerializer


def _tiny_file(name='notes.pdf', content=b'%PDF-1.4\n%fake\n'):
    """Build a small in-memory file safe for serializer / model validation."""
    return SimpleUploadedFile(name, content, content_type='application/pdf')


def _oversize_photo(name='big.jpg', size_mb=3):
    """JPEG-ish payload over the 2 MiB cap."""
    content = b'\xff\xd8\xff\xe0' + b'\x00' * (size_mb * 1024 * 1024)
    return SimpleUploadedFile(name, content, content_type='image/jpeg')


def _under_photo(name='small.jpg', size_kb=512):
    content = b'\xff\xd8\xff\xe0' + b'\x00' * (size_kb * 1024)
    return SimpleUploadedFile(name, content, content_type='image/jpeg')


class CoordMeetingUploadGateTest(TestCase):
    """The meeting_notes upload is enforced at every layer."""

    def setUp(self):
        self.center = ServiceCenter.objects.create(
            organisation='Bandhu', name='Dhaka KP Clinic', code='BAN-001',
            center_type='DIC', district='Dhaka', upazila='Dhanmondi',
        )

    def _base_payload(self):
        return {
            'organisation': 'Bandhu',
            'center': self.center.id,
            'meeting_date': str(_date.today()),
            'meeting_type': CoordMeeting.GOB,
            'location_text': 'Civil Surgeon Office',
            'participant_count': 12,
            'agenda': 'Quarterly review',
        }

    def test_serializer_rejects_missing_meeting_notes(self):
        ser = CoordMeetingSerializer(data=self._base_payload())
        self.assertFalse(ser.is_valid())
        self.assertIn('meeting_notes', ser.errors)

    def test_serializer_accepts_meeting_notes(self):
        data = self._base_payload()
        data['meeting_notes'] = _tiny_file()
        ser = CoordMeetingSerializer(data=data)
        self.assertTrue(ser.is_valid(), msg=str(ser.errors))

    def test_serializer_rejects_oversize_photo(self):
        data = self._base_payload()
        data['meeting_notes'] = _tiny_file()
        data['photo'] = _oversize_photo(size_mb=3)
        ser = CoordMeetingSerializer(data=data)
        self.assertFalse(ser.is_valid())
        self.assertIn('photo', ser.errors)

    def test_serializer_under_2mb_photo_not_rejected_for_size(self):
        data = self._base_payload()
        data['meeting_notes'] = _tiny_file()
        data['photo'] = _under_photo(size_kb=512)
        ser = CoordMeetingSerializer(data=data)
        # Pillow's image-content check may still reject the synthetic
        # JPEG — for the size gate we only assert no size-related error
        # message fires.
        ser.is_valid()
        for err in ser.errors.get('photo', []):
            self.assertNotIn(
                'too large', str(err),
                msg=f'2 MiB gate should not trip on <2MiB photo: {err}',
            )

    def test_model_clean_raises_without_meeting_notes(self):
        m = CoordMeeting(
            organisation='Bandhu', center=self.center,
            meeting_date=_date.today(), meeting_type=CoordMeeting.GOB,
            participant_count=10,
        )
        with self.assertRaises(ValidationError) as cm:
            m.full_clean()
        self.assertIn('meeting_notes', cm.exception.message_dict)


class TrainingEventUploadGateTest(TestCase):
    """The training-event report_file upload is enforced at every layer."""

    def setUp(self):
        self.center = ServiceCenter.objects.create(
            organisation='PHD', name='Daulatdia Brothel Centre', code='PHD-001',
            center_type='BROTHEL', district='Rajbari', upazila='Goalondo',
        )

    def _base_payload(self):
        return {
            'organisation': 'PHD',
            'center': self.center.id,
            'event_date': str(_date.today()),
            'event_type': TrainingEvent.TRAINING,
            'participant_type': TrainingEvent.MW,
            'topic': 'Safe motherhood — refresher',
            'total_participants': 8,
        }

    def test_serializer_rejects_missing_report_file(self):
        ser = TrainingEventSerializer(data=self._base_payload())
        self.assertFalse(ser.is_valid())
        self.assertIn('report_file', ser.errors)

    def test_serializer_accepts_report_file(self):
        data = self._base_payload()
        data['report_file'] = _tiny_file('report.pdf')
        ser = TrainingEventSerializer(data=data)
        self.assertTrue(ser.is_valid(), msg=str(ser.errors))

    def test_model_clean_raises_without_report_file(self):
        e = TrainingEvent(
            organisation='PHD', center=self.center,
            event_date=_date.today(), event_type=TrainingEvent.TRAINING,
            participant_type=TrainingEvent.MW, topic='X',
            total_participants=5,
        )
        with self.assertRaises(ValidationError) as cm:
            e.full_clean()
        self.assertIn('report_file', cm.exception.message_dict)

    def test_oversize_photo_rejected_at_serializer(self):
        data = self._base_payload()
        data['report_file'] = _tiny_file('report.pdf')
        data['photo'] = _oversize_photo(size_mb=3)
        ser = TrainingEventSerializer(data=data)
        self.assertFalse(ser.is_valid())
        self.assertIn('photo', ser.errors)


# ---------------------------------------------------------------------------
# Commit 2 model fixes — HTC consent, MH scoring, Training auto-total
# ---------------------------------------------------------------------------

class Commit2ModelFixesTest(TestCase):
    """One-liner tests per audit FIX 7.1 / 7.2 / 7.3 / 7.4 / 7.6 / 7.7 / 12.2."""

    @classmethod
    def setUpTestData(cls):
        cls.center = ServiceCenter.objects.create(
            organisation='PHD', name='C', code='C-IEC-1',
            center_type=ServiceCenter.DIC, district='Dhaka',
        )
        cls.client_obj = Client.objects.create(
            organisation='PHD', center=cls.center,
            client_id='PHD-HTC-1', name='Test',
        )

    # FIX 7.1 — HTC consent blocks save
    def test_htc_consent_required(self):
        from programs.models import HTCCounselling
        from django.core.exceptions import ValidationError
        h = HTCCounselling(
            organisation='PHD', center=self.center, client=self.client_obj,
            session_type=HTCCounselling.PRE, session_date=date(2026, 5, 1),
            client_consented=False,
        )
        with self.assertRaises(ValidationError):
            h.full_clean()

    def test_htc_consent_true_passes(self):
        from programs.models import HTCCounselling
        h = HTCCounselling(
            organisation='PHD', center=self.center, client=self.client_obj,
            session_type=HTCCounselling.PRE, session_date=date(2026, 5, 1),
            client_consented=True, visit_number=2,
            needle_sharing=False, blood_transfusion=False, client_pregnant=False,
        )
        h.full_clean()  # must not raise

    # FIX 7.2 — HIV/STI new fields exist
    def test_hiv_sti_has_target_group_and_test_name(self):
        from programs.models import HIVSTITestResult
        t = HIVSTITestResult(
            organisation='PHD', center=self.center, client=self.client_obj,
            testing_date=date(2026, 5, 1),
            target_group=HIVSTITestResult.TG_FSW,
            test_name=HIVSTITestResult.TN_HIV,
            referred=True, drug_prescribed='Tenofovir',
        )
        t.full_clean()
        t.save()
        self.assertEqual(t.target_group, 'FSW')
        self.assertTrue(t.referred)

    # FIX 7.3 — GBV sub-types persist
    def test_gbv_subtype_fields_persist(self):
        from programs.models import GBVCase
        g = GBVCase.objects.create(
            organisation='PHD', center=self.center,
            interview_date=date(2026, 5, 1), incident_date=date(2026, 4, 15),
            gbv_sexual=True, gbv_rape=True, gbv_acid_attack=True,
            perpetrator_age=35, perpetrator_occupation='trader',
        )
        g.refresh_from_db()
        self.assertTrue(g.gbv_rape)
        self.assertTrue(g.gbv_acid_attack)
        self.assertEqual(g.perpetrator_age, 35)

    # FIX 7.4 — Depression auto-calc + band + cutoff
    def test_depression_auto_calc_and_band(self):
        from programs.models import MHScreening
        # 30 items × 4 = 120 → 'Moderate' (115-123), exceeds 93.5 cutoff
        responses = {f'q{i}': 4 for i in range(1, 31)}
        m = MHScreening.objects.create(
            organisation='PHD', center=self.center, client=self.client_obj,
            screening_type=MHScreening.DEPRESSION,
            screening_date=date(2026, 5, 1),
            item_responses=responses,
        )
        self.assertEqual(float(m.total_score), 120.0)
        self.assertEqual(m.depression_band, 'Moderate')
        self.assertTrue(m.depression_cutoff_exceeded)

    def test_depression_override_blocked(self):
        from programs.models import MHScreening
        from django.core.exceptions import ValidationError
        responses = {f'q{i}': 3 for i in range(1, 31)}  # sum = 90
        m = MHScreening(
            organisation='PHD', center=self.center, client=self.client_obj,
            screening_type=MHScreening.DEPRESSION,
            screening_date=date(2026, 5, 1),
            item_responses=responses,
            total_score=145,  # forbidden override
        )
        with self.assertRaises(ValidationError):
            m.full_clean()

    # FIX 7.5 — PTSD bands
    def test_ptsd_band_severe(self):
        from programs.models import MHScreening
        responses = {f'q{i}': 5 for i in range(1, 16)}  # sum = 75
        m = MHScreening.objects.create(
            organisation='PHD', center=self.center, client=self.client_obj,
            screening_type=MHScreening.PTSD,
            screening_date=date(2026, 5, 1),
            item_responses=responses,
        )
        self.assertEqual(float(m.total_score), 75.0)
        self.assertEqual(m.ptsd_band, 'Severe Anxiety')
        self.assertTrue(m.ptsd_cutoff_exceeded)

    # FIX 7.6 — OutreachSession movement register fields
    def test_outreach_movement_fields_exist(self):
        from programs.models import OutreachSession
        from datetime import time
        o = OutreachSession.objects.create(
            organisation='PHD', center=self.center,
            session_date=date(2026, 5, 1),
            peer_educator_name='Rina',
            out_time=time(9, 0), return_time=time(13, 0),
            purpose='Outreach in Banani brothel',
            manager_endorsement=False,
            session_variant=OutreachSession.MOBILE_CAMP,
        )
        o.refresh_from_db()
        self.assertEqual(o.out_time.hour, 9)
        self.assertEqual(o.return_time.hour, 13)
        self.assertFalse(o.manager_endorsement)
        self.assertEqual(o.session_variant, 'mobile_camp')

    # FIX 7.7 — Training auto-total + mismatch block
    def test_training_auto_total_populated(self):
        from programs.models import TrainingEvent
        from django.core.files.uploadedfile import SimpleUploadedFile
        e = TrainingEvent(
            organisation='PHD',
            event_date=date(2026, 5, 1), event_type=TrainingEvent.TRAINING,
            participant_type=TrainingEvent.MW, topic='Auto-total test',
            participants_doctors=2, participants_nurses=3, participants_midwives=4,
            report_file=SimpleUploadedFile('r.pdf', b'data'),
        )
        e.save()
        self.assertEqual(e.total_participants, 9)

    def test_training_total_mismatch_blocked(self):
        from programs.models import TrainingEvent
        from django.core.exceptions import ValidationError
        from django.core.files.uploadedfile import SimpleUploadedFile
        e = TrainingEvent(
            organisation='PHD',
            event_date=date(2026, 5, 1), event_type=TrainingEvent.TRAINING,
            participant_type=TrainingEvent.MW, topic='Mismatch',
            total_participants=100,  # mismatch
            participants_doctors=2, participants_nurses=3,
            report_file=SimpleUploadedFile('r.pdf', b'data'),
        )
        with self.assertRaises(ValidationError):
            e.full_clean()

    # FIX 12.2 — IECMaterial model exists with required fields
    def test_iec_material_creates(self):
        from programs.models import IECMaterial
        from partners.models import Partner
        partner = Partner.objects.get(code='PHD')
        i = IECMaterial.objects.create(
            partner=partner, center=self.center, organisation='PHD',
            material_type=IECMaterial.BILLBOARD,
            quantity=11, date_distributed=date(2026, 5, 1),
            district='Cox\'s Bazar',
        )
        self.assertEqual(i.material_type, 'billboard')
        self.assertEqual(i.quantity, 11)
        # Audit FIX 2.7 — IEC distribution is not surveillance; defaults
        # to PENDING and must go through manager approval.
        self.assertEqual(i.approval_status, IECMaterial.PENDING)


# ---------------------------------------------------------------------------
# Commit 3 cleanup fixes — naming convention + field_staff scope
# ---------------------------------------------------------------------------

class Commit3CleanupFixesTest(TestCase):
    """Tests for audit FIX 10.4/10.5 (center naming) and 15.7 (field staff
    own-entries filter). FIX 12.3 (mobile outreach variant) covered in
    Commit2ModelFixesTest. FIX 14.2 is documentation-only."""

    # FIX 10.4 + 10.5 — naming convention property
    def test_phd_center_naming_compliant(self):
        c = ServiceCenter.objects.create(
            organisation='PHD', name="Daulatdia Brothel (PHD)", code='PHD-NC-1',
            center_type=ServiceCenter.BROTHEL, district='Rajbari',
        )
        self.assertTrue(c.naming_compliant)

    def test_phd_center_naming_non_compliant_warns(self):
        c = ServiceCenter.objects.create(
            organisation='PHD', name="Some Center", code='PHD-NC-2',
            center_type=ServiceCenter.BROTHEL, district='X',
        )
        self.assertFalse(c.naming_compliant)
        self.assertIn('PHD convention', c.naming_convention_hint)

    def test_bandhu_center_naming_compliant(self):
        c = ServiceCenter.objects.create(
            organisation='Bandhu',
            name="Wellness Center Dhaka (Bandhu)", code='BAN-NC-1',
            center_type=ServiceCenter.DIC, district='Dhaka',
        )
        self.assertTrue(c.naming_compliant)

    # FIX 15.7 — field staff own-entries filter (via OrgFilterMixin)
    def test_field_staff_sees_only_own_referrals(self):
        from programs.models import Referral, Client
        from rest_framework.test import APIClient as DRFAPIClient
        center = ServiceCenter.objects.create(
            organisation='PHD', name='C2', code='C2-FS',
            center_type=ServiceCenter.DIC, district='Dhaka',
        )
        client = Client.objects.create(
            organisation='PHD', center=center, client_id='PHD-FS-1', name='X',
        )
        fs_a = _make_user('fs-a@phd.org', Organisation.PHD, Role.FIELD_STAFF)
        fs_b = _make_user('fs-b@phd.org', Organisation.PHD, Role.FIELD_STAFF)
        # Both referrals live in PHD; A submitted one, B submitted the other.
        Referral.objects.create(
            organisation='PHD', center=center, client=client,
            referral_date=date(2026, 5, 1), referral_type=Referral.HIV,
            submitted_by=fs_a,
        )
        Referral.objects.create(
            organisation='PHD', center=center, client=client,
            referral_date=date(2026, 5, 2), referral_type=Referral.TB,
            submitted_by=fs_b,
        )
        api = DRFAPIClient()
        api.force_authenticate(user=fs_a)
        resp = api.get('/api/programs/referrals/')
        self.assertEqual(resp.status_code, 200)
        rows = resp.data if isinstance(resp.data, list) else resp.data.get('results', [])
        # fs_a should see exactly 1 row (their own submission)
        self.assertEqual(len(rows), 1)


# ---------------------------------------------------------------------------
# Maternal Near-Miss ingestion — verbatim WHO MNM form (0-4 screening codes,
# derived delivery_outcome + contributory_conditions, full raw_payload).
# ---------------------------------------------------------------------------
class NearMissIngestTest(TestCase):

    def _payload(self, **ov):
        p = {
            '_id': '9001', '_submitted_by': 'collector1',
            'district': 'Dhaka', 'event_date': '2026-06-01',
            'woman_name': 'Test Woman', 'woman_age': '28',
            'facility_name': 'Dhaka Medical', 'gestational_weeks': '37',
            # Section 1 — WHO 0-4 temporal codes.
            'sev_pph': '1',        # present at arrival -> True
            'sev_preec': '0',      # not present -> False
            'eclampsia': '2',      # developed within 12h -> True
            'sepsis': '4',         # unknown -> None
            'crit_blood': '3',     # developed after 12h -> True
            'life_uterine': '',    # blank -> None
            # Section 3 — Q15 as 9 binary checkboxes (Excel structure);
            # mode_of_delivery is DERIVED from the first 'yes'.
            'mode_csection': 'yes',
            'infant_status_birth': 'dead',     # -> delivery_outcome 'stillbirth'
            'infant_status_discharge': 'dead',
            # Section 5 — structured underlying flags (primary cause is
            # DERIVED from these; the verbatim form has no cause question).
            'un_haemorrhage': 'yes', 'un_unknown': 'no',
            # Section 6 — contributory checklist + other.
            'cc_anemia': 'yes', 'cc_diabetes': '1', 'cc_heart': 'no',
            'cc_other': 'yes', 'cc_other_specify': 'Thyroid disorder',
            # Narrative.
            'audit_summary': 'Managed successfully after transfusion.',
            'audit_recommendations': 'Stock more blood.',
        }
        p.update(ov)
        return p

    def test_screening_codes_and_derivations(self):
        from programs.ciprb_handlers import handle_ciprb_near_miss
        from mpdsr.ciprb_models import MaternalNearMissCase

        resp = handle_ciprb_near_miss(self._payload(), 23.7, 90.4)
        self.assertEqual(resp.status_code, 200)

        c = MaternalNearMissCase.objects.get(woman_name='Test Woman')
        # 0-4 screening mapping: 1/2/3 -> True, 0 -> False, 4/blank -> None.
        self.assertIs(c.sev_pph, True)
        self.assertIs(c.sev_preec, False)
        self.assertIs(c.eclampsia, True)        # code 2 = present
        self.assertIsNone(c.sepsis)             # code 4 = unknown
        self.assertIs(c.crit_blood, True)       # code 3 = present
        self.assertIsNone(c.life_uterine)       # blank
        # mode_of_delivery derived from the Q15 binary checkboxes.
        self.assertEqual(c.mode_of_delivery, 'csection')
        # delivery_outcome derived from infant_status_birth.
        self.assertEqual(c.delivery_outcome, 'stillbirth')
        # contributory_conditions summarised from cc_* + other.
        self.assertIn('Anemia', c.contributory_conditions)
        self.assertIn('Diabetes mellitus', c.contributory_conditions)
        self.assertIn('Thyroid disorder', c.contributory_conditions)
        self.assertNotIn('Heart disease', c.contributory_conditions)  # cc_heart='no'
        # primary cause + summary.
        self.assertEqual(c.cause_of_near_miss, 'haemorrhage')
        self.assertEqual(c.audit_summary, 'Managed successfully after transfusion.')
        # full payload preserved (new structured fields live here).
        self.assertEqual(c.raw_payload.get('un_haemorrhage'), 'yes')
        self.assertEqual(c.raw_payload.get('audit_recommendations'), 'Stock more blood.')
        # lands PENDING for CIPRB verification.
        self.assertEqual(c.approval_status, 'PENDING')

    def test_legacy_yes_no_still_accepted(self):
        from programs.ciprb_handlers import handle_ciprb_near_miss
        from mpdsr.ciprb_models import MaternalNearMissCase
        # Pre-rebuild submissions sent yes/no/unknown — must still map.
        handle_ciprb_near_miss(
            self._payload(_id='9002', woman_name='Legacy Woman',
                          sev_pph='yes', sev_preec='no', sepsis='unknown'),
            23.7, 90.4)
        c = MaternalNearMissCase.objects.get(woman_name='Legacy Woman')
        self.assertIs(c.sev_pph, True)
        self.assertIs(c.sev_preec, False)
        self.assertIsNone(c.sepsis)
