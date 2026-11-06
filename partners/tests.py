"""Sanity tests for the Partner registry."""
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import Organisation, Role, User
from partners.models import Partner


class PartnerSeedTest(TestCase):
    """Migration 0001 seeds CIPRB, Bandhu, PHD with the spec'd colors."""

    def test_three_partners_exist(self):
        codes = set(Partner.objects.values_list('code', flat=True))
        self.assertEqual(codes, {'CIPRB', 'Bandhu', 'PHD'})

    def test_colors_match_spec(self):
        ciprb = Partner.objects.get(code='CIPRB')
        bandhu = Partner.objects.get(code='Bandhu')
        phd = Partner.objects.get(code='PHD')
        # Per IDMS handoff: CIPRB=Blue, Bandhu=Green, PHD=Orange.
        self.assertEqual(ciprb.color_hex.upper(), '#0072BC')
        self.assertEqual(bandhu.color_hex.upper(), '#00B050')
        self.assertEqual(phd.color_hex.upper(), '#ED7D31')

    def test_str(self):
        self.assertEqual(str(Partner.objects.get(code='PHD')), 'PHD')


class PartnerAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='u@unfpa.org', password='x', full_name='U',
            organisation=Organisation.UNFPA, role=Role.SUPERVISOR,
        )

    def test_unauthenticated_blocked(self):
        resp = self.client.get('/api/partners/')
        self.assertEqual(resp.status_code, 403)

    def test_lists_three_partners(self):
        self.client.force_authenticate(user=self.user)
        resp = self.client.get('/api/partners/')
        self.assertEqual(resp.status_code, 200)
        codes = {row['code'] for row in resp.data}
        self.assertEqual(codes, {'CIPRB', 'Bandhu', 'PHD'})

    def test_retrieve_by_code(self):
        self.client.force_authenticate(user=self.user)
        resp = self.client.get('/api/partners/Bandhu/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['code'], 'Bandhu')
