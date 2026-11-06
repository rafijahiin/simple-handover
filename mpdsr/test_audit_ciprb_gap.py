"""The gap audit must NAME the missing submissions and date them correctly.

This exists because "the difference is probably pilot data" is not an answer
anybody can check. CIPRB asks why Kobo shows 56 and the dashboard shows 49; the
audit has to produce the 7, each with a date and a side of the go-live line, and
it has to be read-only while doing it.
"""

from unittest import mock

from django.test import TestCase

from mpdsr.models import MPDSRCase
from mpdsr.reconcile import audit_ciprb_gap

SLUG = 'ciprb_social_autopsy_v1'


def _sub(sub_id, slip, when):
    return {
        '_id': sub_id,
        '_submission_time': when,
        'sa_death_type': '1',
        'meeting_date': '2026-07-20',
        'district': 'Bhola',
        'slip_number': slip,
        'deceased_name': 'Audit fixture %s' % sub_id,
        'collector_name': 'Field Officer',
    }


class GapAuditNamesWhatIsMissing(TestCase):
    def setUp(self):
        # One submission is ALREADY in the app, so the audit must not list it.
        self.present = MPDSRCase.objects.create(
            partner='CIPRB', organisation='CIPRB', sub_form_type='sa_md',
            district='Bhola', date_of_death='2026-07-20',
            approval_status='APPROVED', case_hash='sa:SB-PRESENT')
        self.subs = [
            _sub('1', 'SB-PRESENT', '2026-07-01T10:00:00Z'),   # already held
            _sub('2', 'SB-PILOT', '2026-06-01T10:00:00Z'),     # before go-live
            _sub('3', 'SB-LIVE', '2026-07-15T10:00:00Z'),      # after go-live
        ]

    def _run(self):
        with mock.patch('mpdsr.reconcile._fetch', return_value=self.subs):
            return audit_ciprb_gap('token', slugs=[SLUG])[0]

    def test_a_submission_already_in_the_app_is_not_reported_missing(self):
        ids = [m['id'] for m in self._run()['missing']]
        self.assertNotIn('1', ids)

    def test_pilot_and_live_gaps_are_named_and_separated(self):
        r = self._run()
        self.assertEqual(r['missing_total'], 2)
        self.assertEqual(r['missing_pre_go_live'], 1)
        self.assertEqual(r['missing_live'], 1)
        by_id = {m['id']: m for m in r['missing']}
        self.assertTrue(by_id['2']['pre_go_live'], 'June submission is pilot data')
        self.assertFalse(by_id['3']['pre_go_live'], 'July submission is live data')

    def test_every_missing_row_carries_a_date_to_check(self):
        # A list without dates cannot settle an argument with CIPRB.
        for m in self._run()['missing']:
            self.assertRegex(m['date'], r'^\d{4}-\d{2}-\d{2}$')

    def test_the_audit_writes_nothing(self):
        before = MPDSRCase.objects.count()
        self._run()
        self.assertEqual(MPDSRCase.objects.count(), before,
                         'the audit replays inside savepoints and must roll back')
        self.assertTrue(MPDSRCase.objects.filter(pk=self.present.pk).exists())

    def test_counts_reported_match_kobo_and_the_app(self):
        r = self._run()
        self.assertEqual(r['kobo_count'], 3)
        self.assertEqual(r['app_rows'], MPDSRCase.objects.filter(
            sub_form_type='sa_md').count())

    def test_the_cutoff_is_not_applied_to_the_fetch(self):
        # reconcile_ciprb filters pilot submissions out before replaying. The
        # audit must NOT, or it can never explain the pilot half of the gap.
        self.assertEqual(self._run()['kobo_count'], len(self.subs))
