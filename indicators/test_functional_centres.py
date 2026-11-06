"""Functional-centre indicators (Bandhu 1.6/1.8, PHD SL8) are activity-gated.

A centre configured in the registry but with no approved service activity must
report 0 — a pre-launch / freshly-wiped system shows 0 functional centres, not
"all centres at 100%". Pins the fix for "no indicator is on track if no data is
there".
"""
import datetime

from django.core.cache import cache
from django.test import TestCase

from programs.models import ServiceCenter, OutreachSession, NilReport
from indicators import bandhu, phd


class FunctionalCentresTest(TestCase):
    def setUp(self):
        cache.clear()
        self.today = datetime.date.today()
        self.start = self.today - datetime.timedelta(days=30)
        self.end = self.today + datetime.timedelta(days=1)
        self.dic1 = ServiceCenter.objects.create(
            organisation='Bandhu', name='DIC 1', code='BND-DIC-T1',
            center_type='DIC', district='Sunamganj')
        self.dic2 = ServiceCenter.objects.create(
            organisation='Bandhu', name='DIC 2', code='BND-DIC-T2',
            center_type='DIC', district='Habiganj')
        self.brothel = ServiceCenter.objects.create(
            organisation='PHD', name='Brothel 1', code='PHD-BR-T1',
            center_type=ServiceCenter.BROTHEL, district='Rajbari')

    def _outreach(self, centre, status='APPROVED'):
        return OutreachSession.objects.create(
            organisation='Bandhu', center=centre, session_date=self.today,
            peer_educator_name='PE', approval_status=status)

    def test_idle_centres_count_zero(self):
        # Centres exist in config but have zero approved activity → 0.
        self.assertEqual(bandhu.compute_I_BND_1_8('Bandhu', self.start, self.end), 0)
        self.assertEqual(phd.compute_SL8('PHD', self.start, self.end), 0)

    def test_centre_with_activity_counts(self):
        self._outreach(self.dic1)
        self.assertEqual(bandhu.compute_I_BND_1_8('Bandhu', self.start, self.end), 1)
        # Second active DIC → climbs to 2; idle dic2 still excluded until used.
        self._outreach(self.dic2)
        self.assertEqual(bandhu.compute_I_BND_1_8('Bandhu', self.start, self.end), 2)

    def test_pending_activity_does_not_count(self):
        self._outreach(self.dic1, status='PENDING')
        self.assertEqual(bandhu.compute_I_BND_1_8('Bandhu', self.start, self.end), 0)

    def test_nil_report_does_not_make_centre_functional(self):
        NilReport.objects.create(
            organisation='Bandhu', center=self.dic1, report_date=self.today,
            reason='No clients today', approval_status='APPROVED')
        self.assertEqual(bandhu.compute_I_BND_1_8('Bandhu', self.start, self.end), 0)

    def test_activity_outside_period_excluded(self):
        self._outreach(self.dic1)  # created_at = today
        past_start = self.today - datetime.timedelta(days=60)
        past_end = self.today - datetime.timedelta(days=30)
        self.assertEqual(bandhu.compute_I_BND_1_8('Bandhu', past_start, past_end), 0)
