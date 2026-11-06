"""Baseline approval -> BaselineResponse materialisation (D5).

Pins the fix for "baseline approval does not take any data to the baseline tab":
approving a key-population baseline submission must create the verified
BaselineResponse that the tab's stats endpoint counts.
"""
from django.test import TestCase
from django.utils import timezone

from submissions.models import FormType, KoboSubmission, SubmissionStatus
from baseline.models import BaselineResponse, BaselineSurvey


def make_baseline_sub(raw, status=SubmissionStatus.PENDING):
    return KoboSubmission.objects.create(
        kobo_id=f'bk-{KoboSubmission.objects.count()}',
        form_type=FormType.BASELINE, partner='CIPRB',
        worker_name='Enum', district='Dhaka', region='Dhaka',
        submitted_at=timezone.now(), raw_data=raw, status=status,
    )


class BaselineApprovalTest(TestCase):
    def test_population_field_materialises_on_approval(self):
        sub = make_baseline_sub({'population': 'hijra', 'questionnaire_serial': 'H-001'})
        self.assertFalse(BaselineResponse.objects.filter(submission=sub).exists())
        sub.status = SubmissionStatus.APPROVED
        sub.save()  # fires the post_save signal
        resp = BaselineResponse.objects.filter(submission=sub).first()
        self.assertIsNotNone(resp)
        self.assertEqual(resp.population, 'hijra')
        self.assertEqual(resp.partner, 'CIPRB')

    def test_xform_id_fallback_materialises(self):
        # No 'population' field — only the form id. The hardened gate must still route it.
        sub = make_baseline_sub({'_xform_id_string': 'ciprb_baseline_fsw_v1',
                                 'questionnaire_serial': 'F-007'})
        sub.status = SubmissionStatus.APPROVED
        sub.save()
        resp = BaselineResponse.objects.filter(submission=sub).first()
        self.assertIsNotNone(resp)
        self.assertEqual(resp.population, 'fsw')

    def test_non_legacy_baseline_without_population_still_routes(self):
        # Neither population nor hijra/fsw in the id, but it is NOT the legacy
        # spondon_baseline_v1 — the fallback routes it to BaselineResponse.
        sub = make_baseline_sub({'_xform_id_string': 'ciprb_baseline_v2',
                                 'questionnaire_serial': 'X-1'})
        sub.status = SubmissionStatus.APPROVED
        sub.save()
        self.assertTrue(BaselineResponse.objects.filter(submission=sub).exists())

    def test_legacy_survey_does_not_create_baseline_response(self):
        sub = make_baseline_sub({'_xform_id_string': 'spondon_baseline_v1'})
        sub.status = SubmissionStatus.APPROVED
        sub.save()
        self.assertFalse(BaselineResponse.objects.filter(submission=sub).exists())
        # It should instead go to the legacy BaselineSurvey.
        self.assertTrue(BaselineSurvey.objects.filter(submission=sub).exists())

    def test_pending_does_not_materialise(self):
        make_baseline_sub({'population': 'fsw'}, status=SubmissionStatus.PENDING)
        self.assertEqual(BaselineResponse.objects.count(), 0)
