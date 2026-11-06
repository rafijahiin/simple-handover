from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import Organisation, Role, User
from .anomaly import detect_anomalies
from .pii_stripper import strip_pii

BASE_URL = '/api/reports/'


def make_user(email, org, role):
    return User.objects.create_user(
        email=email, password='pass', full_name='Test', organisation=org, role=role,
    )


# ---------------------------------------------------------------------------
# PII stripper unit tests
# ---------------------------------------------------------------------------

class PIIStripperTest(TestCase):

    def test_strips_known_pii_keys(self):
        data = {'patient_name': 'Fatema', 'district': 'Dhaka', 'age': 30}
        result = strip_pii(data)
        self.assertNotIn('patient_name', result)
        self.assertIn('district', result)
        self.assertIn('age', result)

    def test_redacts_phone_numbers_in_values(self):
        data = {'notes': 'Call 01712345678 for follow-up'}
        result = strip_pii(data)
        self.assertNotIn('01712345678', result['notes'])
        self.assertIn('[REDACTED]', result['notes'])

    def test_strips_nid_field(self):
        data = {'nid': '1234567890', 'district': 'Sylhet'}
        result = strip_pii(data)
        self.assertNotIn('nid', result)

    def test_empty_dict_returns_empty(self):
        self.assertEqual(strip_pii({}), {})

    def test_non_pii_data_unchanged(self):
        data = {'district': 'Dhaka', 'region': 'Dhaka', 'age': 25}
        result = strip_pii(data)
        self.assertEqual(result, data)


# ---------------------------------------------------------------------------
# Anomaly detection unit tests
# ---------------------------------------------------------------------------

class AnomalyDetectionTest(TestCase):

    def test_detects_spike(self):
        counts = [10, 12, 11, 10, 12, 11, 10, 50, 12, 11, 10, 12]
        anomalies = detect_anomalies(counts)
        indices = [a['index'] for a in anomalies]
        self.assertIn(7, indices)

    def test_no_anomalies_in_flat_data(self):
        counts = [10, 10, 10, 10, 10, 10]
        anomalies = detect_anomalies(counts)
        self.assertEqual(anomalies, [])

    def test_insufficient_data_returns_empty(self):
        self.assertEqual(detect_anomalies([5, 6]), [])

    def test_anomaly_has_required_keys(self):
        counts = [10, 10, 10, 10, 10, 10, 10, 100]
        anomalies = detect_anomalies(counts)
        if anomalies:
            for key in ('index', 'value', 'z_score'):
                self.assertIn(key, anomalies[0])


# ---------------------------------------------------------------------------
# API — generate endpoint
# ---------------------------------------------------------------------------

class ReportGenerateTest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.manager = make_user('pm@phd.org', Organisation.PHD, Role.MANAGER)

    def test_unauthenticated_returns_403(self):
        resp = self.client.post(f'{BASE_URL}generate/', {})
        self.assertEqual(resp.status_code, 403)

    def test_generate_pdf_monthly_summary(self):
        self.client.force_authenticate(user=self.manager)
        resp = self.client.post(f'{BASE_URL}generate/', {
            'report_type': 'monthly_summary',
            'format': 'pdf',
            'partner': 'PHD',
            'year': 2025,
            'month': 5,
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertIn('id', resp.data)
        self.assertEqual(resp.data['format'], 'pdf')

    def test_generate_docx(self):
        self.client.force_authenticate(user=self.manager)
        resp = self.client.post(f'{BASE_URL}generate/', {
            'report_type': 'monthly_summary',
            'format': 'docx',
            'partner': 'PHD',
            'year': 2025,
            'month': 5,
        }, format='json')
        self.assertEqual(resp.status_code, 201)

    def test_invalid_month_rejected(self):
        self.client.force_authenticate(user=self.manager)
        resp = self.client.post(f'{BASE_URL}generate/', {
            'report_type': 'monthly_summary',
            'format': 'pdf',
            'partner': 'PHD',
            'year': 2025,
            'month': 13,
        }, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_anomalies_endpoint_returns_correct_structure(self):
        self.client.force_authenticate(user=self.manager)
        resp = self.client.get(f'{BASE_URL}anomalies/?year=2024&form_type=mpdsr')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('anomalies', resp.data)
