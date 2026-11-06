"""Regression tests for the 2026-06-28 data-flow wiring fixes.

Each test pins one defect from the simpledashboard.pro audit: visuals that read
the wrong model/table so live CIPRB / programs submissions never reached them.
These prove the fixed chain actually populates from live data.
"""
import datetime

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Organisation, Role, User

from dashboard.views import (
    _partner_programs_counts, _district_activity_programs,
)
from tracker.programs_query import daily_reporting_activity, programs_last_by_centre

from fistula.ciprb_models import CIPRBFistulaCase
from mpdsr.models import MPDSRCase, DeathType, ReviewStatus
from mpdsr.ciprb_models import MPDSRDeathNotification, MaternalNearMissCase

BASE_URL = '/api/dashboard/'


def make_fistula(stage, approval='APPROVED', district='Dhaka'):
    return CIPRBFistulaCase.objects.create(
        organisation='CIPRB', district=district, name='Test Patient',
        current_stage=stage, approval_status=approval,
    )


def make_mpdsr_case(death_type=DeathType.MATERNAL, approval='APPROVED',
                    sub_form_type='', district='Dhaka'):
    return MPDSRCase.objects.create(
        organisation='CIPRB', partner='CIPRB', district=district, region='Dhaka',
        date_of_death=datetime.date.today(), death_type=death_type,
        cause_of_death='Hemorrhage', status=ReviewStatus.REPORTED,
        sub_form_type=sub_form_type, approval_status=approval,
    )


def make_notification(kind, approval='APPROVED', district='Dhaka'):
    return MPDSRDeathNotification.objects.create(
        organisation='CIPRB', district=district, death_kind=kind,
        deceased_name='Deceased', date_of_death=datetime.date.today(),
        reporter_name='Reporter', approval_status=approval,
    )


class DailyReportingCiprbTest(TestCase):
    """Defect #4 — daily_reporting_activity must scan the CIPRB models
    (mpdsr/fistula apps), not only the programs app, or the CIPRB daily-
    reporting tile is permanently silent."""

    def test_ciprb_submission_is_counted(self):
        make_fistula(CIPRBFistulaCase.STAGE_SUSPECTED)
        make_mpdsr_case()
        now = timezone.now()
        threshold = now - datetime.timedelta(hours=24)
        today_start = timezone.localtime(now).replace(
            hour=0, minute=0, second=0, microsecond=0)
        recent, today, codes, last = daily_reporting_activity(
            'CIPRB', threshold, today_start)
        self.assertGreaterEqual(recent, 2)   # fistula + mpdsr case
        self.assertIsNotNone(last)

    def test_other_partner_unaffected(self):
        make_fistula(CIPRBFistulaCase.STAGE_SUSPECTED)  # CIPRB only
        now = timezone.now()
        threshold = now - datetime.timedelta(hours=24)
        today_start = timezone.localtime(now).replace(
            hour=0, minute=0, second=0, microsecond=0)
        recent, *_ = daily_reporting_activity('PHD', threshold, today_start)
        self.assertEqual(recent, 0)   # CIPRB rows must not leak into PHD

    def test_pending_submission_counts_as_reported(self):
        # Daily reporting is submission-based: a submitted-but-unapproved record
        # IS a report (the field did its job; approval is the manager's separate
        # step). Only REJECTED records are excluded. Previously this counted
        # APPROVED-only, so a pending backlog made partners read as falsely silent.
        make_mpdsr_case(approval='PENDING')
        make_fistula(CIPRBFistulaCase.STAGE_SUSPECTED, approval='PENDING')
        make_mpdsr_case(approval='REJECTED')   # rejected must NOT count
        now = timezone.now()
        threshold = now - datetime.timedelta(hours=24)
        today_start = timezone.localtime(now).replace(
            hour=0, minute=0, second=0, microsecond=0)
        recent, today, codes, last = daily_reporting_activity(
            'CIPRB', threshold, today_start)
        self.assertEqual(recent, 2)   # the two PENDING reports, not the rejected
        self.assertEqual(today, 2)
        self.assertIsNotNone(last)

    def test_registration_counts_for_both_orgs(self):
        # A client registration IS field-reporting work and counts for BOTH orgs
        # under the SAME rule. PHD's daily activity is FSW registration (pending),
        # so excluding Client made PHD read 0 while Bandhu (registrations
        # auto-approved, service records elsewhere) showed a number. Whether the
        # registration is PENDING (PHD) or APPROVED (Bandhu) is irrelevant.
        from programs.models import ServiceCenter, Client
        now = timezone.now()
        threshold = now - datetime.timedelta(hours=24)
        today_start = timezone.localtime(now).replace(
            hour=0, minute=0, second=0, microsecond=0)
        for org, code, status in (
            ('PHD', 'PHD-RT', 'PENDING'),      # FSW registration is manager-approved
            ('Bandhu', 'BND-RT', 'APPROVED'),  # Mother List is auto-approved
        ):
            centre = ServiceCenter.objects.create(
                organisation=org, name='C', code=code,
                center_type='DIC', district='Dhaka')
            Client.objects.create(
                organisation=org, center=centre, client_id=f'{code}-1',
                name='X', approval_status=status)
            recent, *_ = daily_reporting_activity(org, threshold, today_start)
            self.assertEqual(recent, 1, f'{org} registration must count as a report')

    def test_per_centre_last_uses_programs_models(self):
        # The per-centre 'hours silent' drill-down must see programs-model
        # submissions (PHD/Bandhu have no KoboSubmission rows). A pending clinic
        # visit at a centre gives that centre a last-report time; a rejected one
        # does not, and auto-approved registrations (Client) are excluded.
        from programs.models import ServiceCenter, Client, ClinicVisit
        centre = ServiceCenter.objects.create(
            organisation='Bandhu', name='DIC', code='BND-PC-1',
            center_type='DIC', district='Dhaka')
        cl = Client.objects.create(
            organisation='Bandhu', center=centre, client_id='PC-1', name='A')
        ClinicVisit.objects.create(
            organisation='Bandhu', center=centre, client=cl,
            visit_date=datetime.date.today(), approval_status='PENDING')
        by_centre = programs_last_by_centre('Bandhu')
        self.assertIn('BND-PC-1', by_centre)          # pending visit is a report
        self.assertIsNotNone(by_centre['BND-PC-1'])

        # A different centre with ONLY a rejected visit must not appear.
        centre2 = ServiceCenter.objects.create(
            organisation='Bandhu', name='DIC2', code='BND-PC-2',
            center_type='DIC', district='Dhaka')
        ClinicVisit.objects.create(
            organisation='Bandhu', center=centre2, client=cl,
            visit_date=datetime.date.today(), approval_status='REJECTED')
        self.assertNotIn('BND-PC-2', programs_last_by_centre('Bandhu'))


class PartnerProgramsCountsTest(TestCase):
    """Defect #6 — PartnerKPIsView counts must include the programs/CIPRB
    submission models, not only the legacy KoboSubmission table."""

    def test_ciprb_counts(self):
        m0, m1 = timezone.now().replace(day=1, hour=0), timezone.now() + datetime.timedelta(days=1)
        make_mpdsr_case(approval='APPROVED')
        make_notification('maternal', approval='PENDING')
        this_month, pending = _partner_programs_counts('CIPRB', m0, m1)
        self.assertGreaterEqual(this_month, 1)   # approved case this month
        self.assertGreaterEqual(pending, 1)      # pending notification

    def test_phd_excludes_ciprb(self):
        make_mpdsr_case()   # CIPRB
        m0, m1 = timezone.now().replace(day=1, hour=0), timezone.now() + datetime.timedelta(days=1)
        this_month, pending = _partner_programs_counts('PHD', m0, m1)
        self.assertEqual(this_month, 0)
        self.assertEqual(pending, 0)


class BandhuTwoStageBucketTest(TestCase):
    """A Bandhu manager approval must MOVE a record from the manager bucket to
    the UNFPA bucket — not silently clear it. The org banner reads pending
    (manager stage) + pending_unfpa (MANAGER_APPROVED, awaiting UNFPA); both are
    still uncounted by the indicators until UNFPA finalises. Regression for the
    'I approve but the number just vanishes and nothing counts' report."""

    def setUp(self):
        cache.clear()
        from programs.models import ServiceCenter, Client, ClinicVisit
        self.centre = ServiceCenter.objects.create(
            organisation='Bandhu', name='DIC', code='BND-2S',
            center_type='DIC', district='Dhaka', is_active=True)
        self.client_obj = Client.objects.create(
            organisation='Bandhu', center=self.centre, client_id='2S-1',
            name='Asha', approval_status='APPROVED')
        self.cv = ClinicVisit.objects.create(
            organisation='Bandhu', center=self.centre, client=self.client_obj,
            visit_date=timezone.now().date(), approval_status='PENDING')
        self.mgr = User.objects.create_user(
            email='b2s@x.org', password='Str0ng-Passw0rd-2026', full_name='Mgr',
            organisation=Organisation.BANDHU, role=Role.MANAGER)

    def _kpis(self):
        c = APIClient()
        c.force_authenticate(self.mgr)
        r = c.get(f'{BASE_URL}partner-kpis/?partner=Bandhu')
        self.assertEqual(r.status_code, 200, r.content)
        return r.data

    def test_manager_approval_moves_bucket_not_clears(self):
        d = self._kpis()
        self.assertEqual(d['pending'], 1)          # awaiting manager
        self.assertEqual(d['pending_unfpa'], 0)    # nothing at UNFPA yet

        # Stage 1: Bandhu manager approves → MANAGER_APPROVED.
        self.cv.approval_status = 'MANAGER_APPROVED'
        self.cv.save()
        cache.clear()
        d = self._kpis()
        self.assertEqual(d['pending'], 0)          # left the manager bucket
        self.assertEqual(d['pending_unfpa'], 1)    # now awaiting UNFPA — NOT gone

        # Stage 2: UNFPA finalises → APPROVED, clears both buckets.
        self.cv.approval_status = 'APPROVED'
        self.cv.save()
        cache.clear()
        d = self._kpis()
        self.assertEqual(d['pending'], 0)
        self.assertEqual(d['pending_unfpa'], 0)


class DistrictActivityTest(TestCase):
    """Defect #7 — CentresView district ranking must derive from the
    programs/CIPRB models, not only KoboSubmission."""

    def test_ciprb_district_appears(self):
        make_mpdsr_case(district='Sylhet')
        m0 = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        m1 = timezone.now() + datetime.timedelta(days=1)
        trend_start = timezone.now() - datetime.timedelta(days=14)
        counts, trend = _district_activity_programs(['CIPRB'], m0, m1, trend_start)
        self.assertIn('Sylhet', counts)
        self.assertGreaterEqual(counts['Sylhet'], 1)


class KpiCiprbPayloadTest(TestCase):
    """Defects #1/#2/#3/#5 — the homepage KPI payload must reflect live CIPRB
    fistula stages, live MPDSR review/notification counts, and count CIPRB
    submissions in the programme-wide this-month/pending totals."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.unfpa = User.objects.create_user(
            email='sup@unfpa.org', password='pass', full_name='Sup',
            organisation=Organisation.UNFPA, role=Role.SUPERVISOR,
        )
        self.client.force_authenticate(user=self.unfpa)

    def _kpis(self):
        cache.clear()
        resp = self.client.get(f'{BASE_URL}kpis/')
        self.assertEqual(resp.status_code, 200)
        return resp.data

    def test_fistula_repaired_from_ciprb_model(self):
        # Defect #1/#2 — repaired/rehabilitated read CIPRBFistulaCase (monotonic).
        make_fistula(CIPRBFistulaCase.STAGE_REPAIRED)
        make_fistula(CIPRBFistulaCase.STAGE_REHABILITATED)
        make_fistula(CIPRBFistulaCase.STAGE_SUSPECTED)
        data = self._kpis()
        self.assertEqual(data['fistula_repaired'], 2)        # repaired + rehab
        self.assertEqual(data['fistula_reintegrated'], 1)    # rehab only
        self.assertEqual(data['total_fistula_patients'], 3)  # all suspected+
        self.assertEqual(data['total_fistula_referred'], 2)  # referred+ (rep+rehab)

    def test_fistula_pending_not_counted_in_funnel(self):
        make_fistula(CIPRBFistulaCase.STAGE_REPAIRED, approval='PENDING')
        data = self._kpis()
        self.assertEqual(data['fistula_repaired'], 0)   # only APPROVED counts

    def test_mpdsr_review_and_notification_counts(self):
        # Defect #3 — live MPDSR review + notification rows feed the totals.
        make_mpdsr_case(death_type=DeathType.MATERNAL)
        make_mpdsr_case(death_type=DeathType.PERINATAL)
        make_notification('maternal')
        make_notification('neonatal')
        make_notification('stillbirth')
        data = self._kpis()
        self.assertGreaterEqual(data['total_md_reviewed'], 1)
        self.assertGreaterEqual(data['total_nd_reviewed'], 1)
        self.assertGreaterEqual(data['total_md_notified'], 1)
        self.assertGreaterEqual(data['total_nd_notified'], 1)
        self.assertGreaterEqual(data['total_stillbirths_notified'], 1)

    def test_ciprb_pending_counted_in_awaiting_review(self):
        # Defect #5 — a PENDING CIPRB submission increments the pending KPI.
        before = self._kpis()['submissions_pending']
        MaternalNearMissCase.objects.create(
            organisation='CIPRB', district='Dhaka',
            event_date=datetime.date.today(), approval_status='PENDING')
        after = self._kpis()['submissions_pending']
        self.assertEqual(after, before + 1)

    def test_ciprb_approved_counted_this_month(self):
        before = self._kpis()['submissions_this_month']
        make_mpdsr_case(approval='APPROVED')
        after = self._kpis()['submissions_this_month']
        self.assertEqual(after, before + 1)
