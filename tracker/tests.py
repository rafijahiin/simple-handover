import datetime

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import Organisation, Role, User
from submissions.models import FormType, KoboSubmission, SubmissionStatus
from .forecasting import attainment_percent, linear_forecast
from .models import Alert, AlertSeverity, AlertType, MonthlyTarget

TARGETS_URL = '/api/tracker/targets/'
ALERTS_URL = '/api/tracker/alerts/'
FORECAST_URL = '/api/tracker/forecast/'


def make_user(email, org, role):
    return User.objects.create_user(
        email=email, password='pass', full_name='Test', organisation=org, role=role,
    )


def make_submission(partner, form_type, year, month, status=SubmissionStatus.APPROVED):
    dt = datetime.datetime(year, month, 15, tzinfo=datetime.timezone.utc)
    return KoboSubmission.objects.create(
        kobo_id=f'k-{KoboSubmission.objects.count()}',
        form_type=form_type,
        partner=partner,
        worker_name='Rina',
        district='Dhaka',
        region='Dhaka',
        submitted_at=dt,
        raw_data={},
        status=status,
    )


# ---------------------------------------------------------------------------
# Forecasting unit tests
# ---------------------------------------------------------------------------

class ForecastingTest(TestCase):

    def test_linear_forecast_returns_correct_count(self):
        result = linear_forecast([10, 12, 14, 16, 18, 20], periods_ahead=3)
        self.assertEqual(len(result), 3)

    def test_linear_forecast_projects_trend(self):
        # Perfect linear trend: should forecast ~22, 24, 26
        result = linear_forecast([10, 12, 14, 16, 18, 20], periods_ahead=3)
        self.assertAlmostEqual(result[0], 22.0, delta=1.0)

    def test_linear_forecast_no_negative(self):
        # Declining trend that would go negative
        result = linear_forecast([20, 15, 10, 5, 2, 0], periods_ahead=3)
        for val in result:
            self.assertGreaterEqual(val, 0)

    def test_forecast_insufficient_data(self):
        result = linear_forecast([5], periods_ahead=3)
        self.assertEqual(result, [0.0, 0.0, 0.0])

    def test_attainment_percent_basic(self):
        self.assertEqual(attainment_percent(80, 100), 80.0)

    def test_attainment_percent_zero_target(self):
        self.assertIsNone(attainment_percent(10, 0))


# ---------------------------------------------------------------------------
# MonthlyTarget CRUD
# ---------------------------------------------------------------------------

class MonthlyTargetViewTest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.manager = make_user('pm@phd.org', Organisation.PHD, Role.MANAGER)
        self.supervisor = make_user('sa@ciprb.org', Organisation.CIPRB, Role.SUPERVISOR)

    def test_supervisor_can_create_target(self):
        self.client.force_authenticate(user=self.supervisor)
        resp = self.client.post(TARGETS_URL, {
            'partner': 'PHD',
            'form_type': FormType.MPDSR,
            'year': 2025,
            'month': 6,
            'target': 50,
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(MonthlyTarget.objects.count(), 1)

    def test_manager_cannot_create_target(self):
        self.client.force_authenticate(user=self.manager)
        resp = self.client.post(TARGETS_URL, {
            'partner': 'PHD', 'form_type': FormType.MPDSR,
            'year': 2025, 'month': 6, 'target': 50,
        }, format='json')
        self.assertEqual(resp.status_code, 403)

    def test_invalid_month_rejected(self):
        self.client.force_authenticate(user=self.supervisor)
        resp = self.client.post(TARGETS_URL, {
            'partner': 'PHD', 'form_type': FormType.MPDSR,
            'year': 2025, 'month': 13, 'target': 50,
        }, format='json')
        self.assertEqual(resp.status_code, 400)


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

class AlertViewTest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.phd = make_user('pm@phd.org', Organisation.PHD, Role.MANAGER)
        self.bondhu = make_user('bm@bandhu.org', Organisation.BANDHU, Role.MANAGER)

    def _make_alert(self, partner='PHD'):
        return Alert.objects.create(
            partner=partner,
            alert_type=AlertType.BELOW_TARGET,
            severity=AlertSeverity.WARNING,
            title='Test alert',
            message='Test message',
        )

    def test_phd_sees_only_phd_alerts(self):
        self._make_alert('PHD')
        self._make_alert('Bandhu')
        self.client.force_authenticate(user=self.phd)
        resp = self.client.get(ALERTS_URL)
        self.assertEqual(resp.status_code, 200)
        rows = resp.data if isinstance(resp.data, list) else resp.data['results']
        self.assertEqual(len(rows), 1)

    def test_acknowledge_alert(self):
        alert = self._make_alert('PHD')
        self.client.force_authenticate(user=self.phd)
        resp = self.client.post(f'{ALERTS_URL}{alert.id}/acknowledge/')
        self.assertEqual(resp.status_code, 200)
        alert.refresh_from_db()
        self.assertTrue(alert.acknowledged)
        self.assertEqual(alert.acknowledged_by, self.phd)

    def test_filter_unacknowledged(self):
        a1 = self._make_alert('PHD')
        self._make_alert('PHD')  # second alert stays unacknowledged
        a1.acknowledged = True
        a1.save()
        self.client.force_authenticate(user=self.phd)
        resp = self.client.get(f'{ALERTS_URL}?acknowledged=false')
        rows = resp.data if isinstance(resp.data, list) else resp.data['results']
        self.assertEqual(len(rows), 1)


# ---------------------------------------------------------------------------
# Forecast endpoint
# ---------------------------------------------------------------------------

class ForecastViewTest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.phd = make_user('pm@phd.org', Organisation.PHD, Role.MANAGER)

    def test_returns_history_and_forecast_keys(self):
        self.client.force_authenticate(user=self.phd)
        resp = self.client.get(f'{FORECAST_URL}?partner=PHD&form_type=mpdsr')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('history', resp.data)
        self.assertIn('attainment_percent', resp.data)

    def test_unauthenticated_returns_403(self):
        resp = self.client.get(FORECAST_URL)
        self.assertEqual(resp.status_code, 403)


# ---------------------------------------------------------------------------
# Progress endpoint — audit FIX 13.1 (CIPRB included) + 13.3 (exclusives)
# ---------------------------------------------------------------------------

PROGRESS_URL = '/api/tracker/progress/'


class ProgressViewExclusiveTest(TestCase):
    """Confirms the tracker default org list contains all three partners
    (FIX 13.1) and that partner-exclusive form types (Autoclave → PHD only,
    MPDSR/Fistula → CIPRB only) are filtered (FIX 13.3)."""

    def setUp(self):
        self.client = APIClient()
        self.supervisor = make_user('sup@unfpa.org', Organisation.UNFPA, Role.SUPERVISOR)

    def test_default_orgs_include_ciprb(self):
        """No ?partner query → response must include CIPRB rows."""
        self.client.force_authenticate(user=self.supervisor)
        resp = self.client.get(PROGRESS_URL)
        self.assertEqual(resp.status_code, 200)
        rows = resp.data['results']
        partners = {row['partner'] for row in rows}
        self.assertIn('CIPRB', partners)
        self.assertIn('PHD', partners)
        self.assertIn('Bandhu', partners)

    def test_autoclave_excluded_for_non_phd(self):
        """Autoclave rows must not appear for CIPRB or Bandhu (PHD-only form)."""
        self.client.force_authenticate(user=self.supervisor)
        resp = self.client.get(PROGRESS_URL)
        for row in resp.data['results']:
            if row.get('form_type') == 'autoclave_log':
                self.assertEqual(row['partner'], 'PHD')

    def test_mpdsr_excluded_for_phd_and_bandhu(self):
        """MPDSR rows must only appear for CIPRB."""
        self.client.force_authenticate(user=self.supervisor)
        resp = self.client.get(PROGRESS_URL)
        for row in resp.data['results']:
            if row.get('form_type') == 'mpdsr':
                self.assertEqual(row['partner'], 'CIPRB')
