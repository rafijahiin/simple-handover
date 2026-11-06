"""Intake panel (Option A): 'what's being submitted' counts ALL submissions
(pending + approved, minus rejected), opens on the latest month with data, and
lists the Bandhu F-01 Wellness Logbook."""
from datetime import date

from django.test import TestCase
from django.utils import timezone

from programs.models import ServiceCenter, OutreachSession, WellnessLogbookEntry
from tracker.programs_query import (
    count_programs, available_program_months, PROGRAMS_REGISTRY, ORG_FORM_TYPES,
)


def _center():
    return ServiceCenter.objects.create(
        organisation='Bandhu', name='X', code='BAN-001',
        center_type=ServiceCenter.DIC, district='Chittagong', is_active=True)


class IntakePanelTest(TestCase):
    def setUp(self):
        self.center = _center()
        # 3 outreach: 1 approved, 1 pending, 1 rejected — all this month.
        for st in (OutreachSession.APPROVED, OutreachSession.PENDING, 'REJECTED'):
            OutreachSession.objects.create(
                organisation='Bandhu', center=self.center,
                session_date=date(2026, 6, 30), peer_educator_name='p',
                approval_status=st)
        self.now = timezone.now()

    def _ym(self):
        # rows are stamped created_at=now() at creation, so query the real month
        return self.now.year, self.now.month

    def test_approved_only_counts_just_approved(self):
        y, m = self._ym()
        self.assertEqual(count_programs('outreach_session', 'Bandhu', y, m), 1)

    def test_intake_counts_pending_and_approved_but_not_rejected(self):
        y, m = self._ym()
        self.assertEqual(
            count_programs('outreach_session', 'Bandhu', y, m, approved_only=False), 2)

    def test_available_months_lists_the_month_with_data(self):
        months = available_program_months('Bandhu', ['outreach_session'])
        y, m = self._ym()
        self.assertIn({'year': y, 'month': m}, months)

    def test_wellness_logbook_is_registered_and_in_bandhu_list(self):
        self.assertIn('wellness_logbook', PROGRAMS_REGISTRY)
        self.assertEqual(PROGRAMS_REGISTRY['wellness_logbook'][0], 'WellnessLogbookEntry')
        self.assertIn('wellness_logbook', ORG_FORM_TYPES['Bandhu'])

    def test_logbook_counts_in_intake_view(self):
        WellnessLogbookEntry.objects.create(
            organisation='Bandhu', center=self.center,
            service_date=date(2026, 6, 30), client_id='02-0001',
            approval_status=WellnessLogbookEntry.PENDING)
        y, m = self._ym()
        # pending logbook is invisible to approved-only, visible to intake
        self.assertEqual(count_programs('wellness_logbook', 'Bandhu', y, m), 0)
        self.assertEqual(
            count_programs('wellness_logbook', 'Bandhu', y, m, approved_only=False), 1)
