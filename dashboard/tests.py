import datetime

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Organisation, Role, User
from submissions.models import FormType, KoboSubmission, SubmissionStatus

BASE_URL = '/api/dashboard/'


def make_user(email, org, role):
    return User.objects.create_user(
        email=email, password='pass', full_name='Test', organisation=org, role=role,
    )


def make_submission(partner, form_type, district='Dhaka', status=SubmissionStatus.APPROVED,
                    worker_name='Rina', submitted_at=None, lat=None, lng=None, kobo_id=None):
    if submitted_at is None:
        submitted_at = timezone.now()
    return KoboSubmission.objects.create(
        kobo_id=kobo_id or f'k-{KoboSubmission.objects.count()}',
        form_type=form_type,
        partner=partner,
        worker_name=worker_name,
        district=district,
        region='Dhaka',
        submitted_at=submitted_at,
        latitude=lat,
        longitude=lng,
        raw_data={},
        status=status,
    )


# ---------------------------------------------------------------------------
# KPI view
# ---------------------------------------------------------------------------

class KPIViewTest(TestCase):
    def setUp(self):
        # KPIView caches its payload for 60s keyed by org scope. The LocMemCache
        # persists across tests in one process, so without this clear a test
        # reads a PRIOR test's cached counts (e.g. mom_change=100 in a test that
        # created no data). Clear it so each test computes fresh.
        from django.core.cache import cache
        cache.clear()
        self.client = APIClient()
        self.phd = make_user('pm@phd.org', Organisation.PHD, Role.MANAGER)
        self.bondhu = make_user('bm@bandhu.org', Organisation.BANDHU, Role.MANAGER)

    def test_unauthenticated_returns_403(self):
        resp = self.client.get(f'{BASE_URL}kpis/')
        self.assertEqual(resp.status_code, 403)

    def test_returns_expected_keys(self):
        self.client.force_authenticate(user=self.phd)
        resp = self.client.get(f'{BASE_URL}kpis/')
        self.assertEqual(resp.status_code, 200)
        for key in ('submissions_this_month', 'submissions_pending', 'active_workers',
                    'fistula_cases_this_month', 'mpdsr_cases_this_month',
                    'previous_month_submissions', 'mom_change_percent'):
            self.assertIn(key, resp.data)

    def test_counts_this_month_only(self):
        now = timezone.now()
        last_month = now.replace(day=1) - datetime.timedelta(days=1)
        make_submission('PHD', FormType.MPDSR, submitted_at=now)
        make_submission('PHD', FormType.MPDSR, submitted_at=last_month)  # last month — excluded
        self.client.force_authenticate(user=self.phd)
        resp = self.client.get(f'{BASE_URL}kpis/')
        self.assertEqual(resp.data['submissions_this_month'], 1)

    def test_org_isolation_phd_does_not_count_bondhu(self):
        make_submission('PHD', FormType.MPDSR)
        make_submission('Bandhu', FormType.MPDSR)
        self.client.force_authenticate(user=self.phd)
        resp = self.client.get(f'{BASE_URL}kpis/')
        self.assertEqual(resp.data['submissions_this_month'], 1)

    def test_pending_counted_separately(self):
        # Per the current KPI contract (_base_qs in dashboard/views.py),
        # `submissions_this_month` counts every received submission
        # — both PENDING and APPROVED — because submissions become
        # visible on dashboards the moment they arrive via webhook.
        # `submissions_pending` is the *additional* counter that only
        # counts unreviewed items.
        make_submission('PHD', FormType.MPDSR, status=SubmissionStatus.PENDING)
        make_submission('PHD', FormType.MPDSR, status=SubmissionStatus.APPROVED)
        self.client.force_authenticate(user=self.phd)
        resp = self.client.get(f'{BASE_URL}kpis/')
        self.assertEqual(resp.data['submissions_this_month'], 2)
        self.assertEqual(resp.data['submissions_pending'], 1)

    def test_fistula_count(self):
        make_submission('PHD', FormType.FISTULA)
        make_submission('PHD', FormType.MPDSR)
        self.client.force_authenticate(user=self.phd)
        resp = self.client.get(f'{BASE_URL}kpis/')
        self.assertEqual(resp.data['fistula_cases_this_month'], 1)
        self.assertEqual(resp.data['mpdsr_cases_this_month'], 1)

    def test_mom_change_positive(self):
        now = timezone.now()
        last_month = (now.replace(day=1) - datetime.timedelta(days=1)).replace(day=15)
        make_submission('PHD', FormType.MPDSR, submitted_at=last_month)
        make_submission('PHD', FormType.MPDSR, submitted_at=now)
        make_submission('PHD', FormType.MPDSR, submitted_at=now)
        self.client.force_authenticate(user=self.phd)
        resp = self.client.get(f'{BASE_URL}kpis/')
        # 2 this month vs 1 last month = +100%
        self.assertEqual(resp.data['mom_change_percent'], 100.0)

    def test_mom_change_zero_when_no_history(self):
        self.client.force_authenticate(user=self.phd)
        resp = self.client.get(f'{BASE_URL}kpis/')
        self.assertEqual(resp.data['mom_change_percent'], 0.0)

    def test_active_workers_distinct(self):
        now = timezone.now()
        make_submission('PHD', FormType.MPDSR, worker_name='Rina', submitted_at=now)
        make_submission('PHD', FormType.MPDSR, worker_name='Rina', submitted_at=now, kobo_id='k2')
        make_submission('PHD', FormType.MPDSR, worker_name='Mita', submitted_at=now, kobo_id='k3')
        self.client.force_authenticate(user=self.phd)
        resp = self.client.get(f'{BASE_URL}kpis/')
        self.assertEqual(resp.data['active_workers'], 2)


# ---------------------------------------------------------------------------
# Monthly breakdown
# ---------------------------------------------------------------------------

class MonthlyBreakdownTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.phd = make_user('pm@phd.org', Organisation.PHD, Role.MANAGER)

    def test_returns_12_months(self):
        self.client.force_authenticate(user=self.phd)
        resp = self.client.get(f'{BASE_URL}monthly/?year=2024')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['months']), 12)
        self.assertEqual(resp.data['year'], 2024)

    def test_counts_correct_month(self):
        dt = datetime.datetime(2024, 6, 15, tzinfo=datetime.timezone.utc)
        make_submission('PHD', FormType.MPDSR, submitted_at=dt)
        self.client.force_authenticate(user=self.phd)
        resp = self.client.get(f'{BASE_URL}monthly/?year=2024')
        june = resp.data['months'][5]  # index 5 = June
        self.assertEqual(june['month'], 6)
        self.assertEqual(june['mpdsr'], 1)

    def test_org_isolated_from_bondhu(self):
        dt = datetime.datetime(2024, 6, 15, tzinfo=datetime.timezone.utc)
        make_submission('Bandhu', FormType.MPDSR, submitted_at=dt)
        self.client.force_authenticate(user=self.phd)
        resp = self.client.get(f'{BASE_URL}monthly/?year=2024')
        june = resp.data['months'][5]
        self.assertEqual(june['mpdsr'], 0)

    def test_defaults_to_current_year(self):
        self.client.force_authenticate(user=self.phd)
        resp = self.client.get(f'{BASE_URL}monthly/')
        self.assertEqual(resp.data['year'], timezone.now().year)

    def test_invalid_year_defaults_gracefully(self):
        self.client.force_authenticate(user=self.phd)
        resp = self.client.get(f'{BASE_URL}monthly/?year=notanumber')
        self.assertEqual(resp.status_code, 200)


# ---------------------------------------------------------------------------
# Activity feed
# ---------------------------------------------------------------------------

class ActivityFeedTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.phd = make_user('pm@phd.org', Organisation.PHD, Role.MANAGER)

    def test_returns_results_key(self):
        self.client.force_authenticate(user=self.phd)
        resp = self.client.get(f'{BASE_URL}activity/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('results', resp.data)

    def test_org_isolation(self):
        make_submission('PHD', FormType.MPDSR, worker_name='Rina')
        make_submission('Bandhu', FormType.MPDSR, worker_name='Mita')
        self.client.force_authenticate(user=self.phd)
        resp = self.client.get(f'{BASE_URL}activity/')
        names = [r['worker_name'] for r in resp.data['results']]
        self.assertIn('Rina', names)
        self.assertNotIn('Mita', names)

    def test_only_approved_in_feed(self):
        make_submission('PHD', FormType.MPDSR, status=SubmissionStatus.PENDING)
        self.client.force_authenticate(user=self.phd)
        resp = self.client.get(f'{BASE_URL}activity/')
        self.assertEqual(len(resp.data['results']), 0)

    def test_time_ago_field_present(self):
        make_submission('PHD', FormType.MPDSR)
        self.client.force_authenticate(user=self.phd)
        resp = self.client.get(f'{BASE_URL}activity/')
        self.assertIn('time_ago', resp.data['results'][0])

    def test_limit_respected(self):
        for i in range(5):
            make_submission('PHD', FormType.MPDSR, kobo_id=f'lim-{i}')
        self.client.force_authenticate(user=self.phd)
        resp = self.client.get(f'{BASE_URL}activity/?limit=3')
        self.assertEqual(len(resp.data['results']), 3)


# ---------------------------------------------------------------------------
# District ranking
# ---------------------------------------------------------------------------

class CentresViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.phd = make_user('pm@phd.org', Organisation.PHD, Role.MANAGER)

    def test_returns_districts_ranked(self):
        make_submission('PHD', FormType.MPDSR, district='Dhaka', kobo_id='d1')
        make_submission('PHD', FormType.MPDSR, district='Dhaka', kobo_id='d2')
        make_submission('PHD', FormType.MPDSR, district='Sylhet', kobo_id='d3')
        self.client.force_authenticate(user=self.phd)
        resp = self.client.get(f'{BASE_URL}centres/')
        self.assertEqual(resp.status_code, 200)
        districts = resp.data['districts']
        self.assertEqual(districts[0]['district'], 'Dhaka')
        self.assertEqual(districts[0]['rank'], 1)
        self.assertEqual(districts[0]['count'], 2)

    def test_org_isolation_in_centres(self):
        make_submission('Bandhu', FormType.MPDSR, district='Dhaka')
        self.client.force_authenticate(user=self.phd)
        resp = self.client.get(f'{BASE_URL}centres/')
        self.assertEqual(len(resp.data['districts']), 0)

    def test_month_label_present(self):
        self.client.force_authenticate(user=self.phd)
        resp = self.client.get(f'{BASE_URL}centres/')
        self.assertIn('month', resp.data)


# ---------------------------------------------------------------------------
# Partner summary (super admin)
# ---------------------------------------------------------------------------

class PartnerSummaryTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.phd_mgr = make_user('pm@phd.org', Organisation.PHD, Role.MANAGER)
        self.supervisor = make_user('sa@ciprb.org', Organisation.CIPRB, Role.SUPERVISOR)

    def test_manager_cannot_access(self):
        self.client.force_authenticate(user=self.phd_mgr)
        resp = self.client.get(f'{BASE_URL}partner-summary/')
        self.assertEqual(resp.status_code, 403)

    def test_supervisor_sees_both_partners(self):
        make_submission('PHD', FormType.MPDSR, kobo_id='ps1')
        make_submission('Bandhu', FormType.MPDSR, kobo_id='ps2')
        self.client.force_authenticate(user=self.supervisor)
        resp = self.client.get(f'{BASE_URL}partner-summary/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('PHD', resp.data)
        self.assertIn('Bandhu', resp.data)
        self.assertEqual(resp.data['PHD']['submissions_this_month'], 1)
        self.assertEqual(resp.data['Bandhu']['submissions_this_month'], 1)


# ---------------------------------------------------------------------------
# Map data
# ---------------------------------------------------------------------------

class MapDataTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.phd = make_user('pm@phd.org', Organisation.PHD, Role.MANAGER)

    def test_returns_only_geolocated_submissions(self):
        make_submission('PHD', FormType.MPDSR, lat=23.71, lng=90.40, kobo_id='geo1')
        make_submission('PHD', FormType.MPDSR, kobo_id='nogeo')  # no lat/lng
        self.client.force_authenticate(user=self.phd)
        resp = self.client.get(f'{BASE_URL}map-data/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['results']), 1)
        self.assertAlmostEqual(resp.data['results'][0]['lat'], 23.71, places=2)

    def test_org_isolation_map(self):
        make_submission('Bandhu', FormType.MPDSR, lat=22.0, lng=89.0)
        self.client.force_authenticate(user=self.phd)
        resp = self.client.get(f'{BASE_URL}map-data/')
        self.assertEqual(len(resp.data['results']), 0)
