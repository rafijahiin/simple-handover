"""Which form version is "current" decides who gets flagged as out of date.

It was a majority vote of the submissions, which inverts the rule the moment a
new form is deployed: the new version starts with the FEWEST submissions, so the
version everyone should be leaving wins the vote, and the enumerators who already
re-downloaded are the ones flagged. Live on 2026-07-17: two Hijra records were
already on the deployed form and both were flagged, while 283 on an older form
were treated as current.
"""
from django.test import TestCase

from .anomaly import _current_version


def _r(version, t, **extra):
    d = {'__version__': version, '_submission_time': t}
    d.update(extra)
    return d


class CurrentVersionTest(TestCase):
    def test_newly_deployed_form_wins_against_the_majority(self):
        # 283 on the old form, 2 who already updated. The 2 are not the anomaly.
        records = ([_r('vOLD', f'2026-07-11T05:{i:02d}:00') for i in range(59)]
                   + [_r('vNEW', '2026-07-17T03:44:52'), _r('vNEW', '2026-07-17T04:00:00')])
        self.assertEqual(_current_version(records), 'vNEW')

    def test_a_straggler_on_an_old_form_cannot_reclaim_current(self):
        # Someone submits on the old form AFTER the new one is live. First-seen is
        # unmoved, so the old version stays old.
        records = [_r('vOLD', '2026-07-11T05:00:00'),
                   _r('vNEW', '2026-07-16T05:00:00'),
                   _r('vOLD', '2026-07-17T09:00:00')]
        self.assertEqual(_current_version(records), 'vNEW')

    def test_deploy_with_no_submissions_yet_flags_nobody(self):
        # Conservative: until one updated device submits, the previous version is
        # current and no one is called out. It self-corrects on that first record.
        records = [_r('vPREV', '2026-07-11T05:00:00'), _r('vPREV', '2026-07-12T05:00:00')]
        self.assertEqual(_current_version(records), 'vPREV')

    def test_end_stamp_is_not_required_to_identify_the_current_form(self):
        # The old rule only counted records carrying interview_end_actual — a proxy
        # that breaks once several versions all have the field.
        records = [_r('vOLD', '2026-07-11T05:00:00', interview_end_actual='2026-07-11T06:00:00'),
                   _r('vNEW', '2026-07-17T05:00:00')]
        self.assertEqual(_current_version(records), 'vNEW')

    def test_no_timestamps_falls_back_to_the_majority_not_none(self):
        records = [_r('vA', ''), _r('vA', ''), _r('vB', '')]
        self.assertEqual(_current_version(records), 'vA')

    def test_empty_and_versionless(self):
        self.assertIsNone(_current_version([]))
        self.assertIsNone(_current_version([{'_submission_time': '2026-07-17T05:00:00'}]))

    def test_ties_break_on_volume(self):
        records = [_r('vA', '2026-07-17T05:00:00'), _r('vB', '2026-07-17T05:00:00'),
                   _r('vB', '2026-07-17T06:00:00')]
        self.assertEqual(_current_version(records), 'vB')
