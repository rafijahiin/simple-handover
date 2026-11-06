"""The home page's baseline indicator must count real verified interviews.

compute_Baseline imported `BaselineSurvey` — a model deleted when the baseline
app was rebuilt around BaselineResponse — and its `except ImportError: return 0`
silently reported zero. 'Baseline assessment records entered: 0' sat on the
UNFPA-facing home page against 684 verified interviews.
"""
import datetime

from django.test import TestCase

from baseline.models import BaselineResponse
from indicators.ciprb import compute_Baseline


class BaselineIndicatorTest(TestCase):
    def _resp(self, **over):
        kw = dict(population='fsw', survey_round='baseline', partner='CIPRB',
                  district='Jashore', raw_data={})
        kw.update(over)
        return BaselineResponse.objects.create(**kw)

    def test_counts_verified_responses_in_period(self):
        self._resp()
        self._resp()
        today = datetime.date.today()
        n = compute_Baseline('CIPRB', today - datetime.timedelta(days=7),
                             today + datetime.timedelta(days=1))
        self.assertEqual(n, 2)

    def test_duplicates_are_excluded(self):
        keep = self._resp()
        self._resp(is_duplicate=True, duplicate_of=keep)
        today = datetime.date.today()
        n = compute_Baseline('CIPRB', today - datetime.timedelta(days=7),
                             today + datetime.timedelta(days=1))
        self.assertEqual(n, 1)

    def test_outside_period_not_counted(self):
        self._resp()
        n = compute_Baseline('CIPRB', datetime.date(2020, 1, 1),
                             datetime.date(2020, 12, 31))
        self.assertEqual(n, 0)
