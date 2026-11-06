"""Partner-KPI active_workers must count the programs models, not just legacy.

The main KPIView was fixed for this months ago (its comment says the legacy-only
count 'read 0 even while partners were actively submitting'); the per-partner
mirror kept the legacy-only query, so /phd and /bondhu showed '0 active workers'
against 3,456 and 1,406 submissions this month.
"""
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Organisation, Role, User
from programs.models import ServiceCenter, WellnessLogbookEntry


class PartnerActiveWorkersTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(User.objects.create_user(
            email='aw@x.org', password='p', full_name='AW',
            organisation=Organisation.CIPRB, role=Role.DEVELOPER))
        self.center = ServiceCenter.objects.create(
            name='DIC-1', organisation='Bandhu', district='Dhaka')

    def test_programs_model_submitters_are_counted(self):
        WellnessLogbookEntry.objects.create(
            organisation='Bandhu', center=self.center,
            service_date=timezone.now().date(),
            approval_status='APPROVED',
            submitted_by_kobo_user='bandhu_field_1')
        WellnessLogbookEntry.objects.create(
            organisation='Bandhu', center=self.center,
            service_date=timezone.now().date(),
            approval_status='APPROVED',
            submitted_by_kobo_user='bandhu_field_2')
        r = self.client.get('/api/dashboard/partner-kpis/?partner=Bandhu')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['active_workers'], 2)

    def test_pending_rows_do_not_count_as_active(self):
        WellnessLogbookEntry.objects.create(
            organisation='Bandhu', center=self.center,
            service_date=timezone.now().date(),
            approval_status='PENDING',
            submitted_by_kobo_user='bandhu_field_3')
        r = self.client.get('/api/dashboard/partner-kpis/?partner=Bandhu')
        self.assertEqual(r.json()['active_workers'], 0)
