"""The approval card must never be empty for an MPDSR review.

A reviewer approving a death review they cannot read is a blind signature.
Two things made that happen for every verbatim review since 23 June: the
handler never stored the Kobo answers on the case, and the serializer only
looked at the legacy linked submission. These tests pin all three layers of
the fix: the handler stores, the serializer prefers the stored answers, and
when neither source exists it synthesises a readable summary from the model.
"""

from django.test import TestCase

from mpdsr.models import MPDSRCase, DeathType, SUB_FORM_LABELS
from programs.serializers import MPDSRCaseApprovalSerializer
from programs.webhook import FORM_HANDLERS, _flatten_group_keys


class HandlerStoresTheAnswers(TestCase):
    def test_a_community_maternal_review_keeps_its_kobo_payload(self):
        payload = _flatten_group_keys({
            '_id': 910001,
            'district': 'sirajganj',
            'case_serial': '77',
            'death_date': '2026-07-10',
            'deceased_name': 'Payload Fixture',
            'cause_of_death': 'pph',
        })
        resp = FORM_HANDLERS['ciprb_mpdsr_community_maternal_v1'](payload, None, None)
        self.assertEqual(resp.status_code, 200)
        case = MPDSRCase.objects.get(sub_form_type='f1')
        self.assertTrue(case.raw_payload, 'the Kobo answers must be stored')
        self.assertEqual(case.raw_payload.get('cause_of_death'), 'pph')


class SerializerNeverReturnsEmpty(TestCase):
    def _case(self, **extra):
        base = dict(partner='CIPRB', organisation='CIPRB', sub_form_type='f2',
                    district='Sirajganj', date_of_death='2026-01-03',
                    death_type=DeathType.PERINATAL, cause_of_death='asphyxia',
                    approval_status='PENDING', case_hash='pl-1')
        base.update(extra)
        return MPDSRCase.objects.create(**base)

    def test_stored_payload_wins(self):
        case = self._case(raw_payload={'q1': 'answer'})
        self.assertEqual(
            MPDSRCaseApprovalSerializer(case).data['raw_payload'],
            {'q1': 'answer'})

    def test_without_any_payload_a_model_summary_is_synthesised(self):
        case = self._case(raw_payload={})
        data = MPDSRCaseApprovalSerializer(case).data['raw_payload']
        self.assertTrue(data, 'must never be empty')
        self.assertEqual(data['cause_of_death'], 'asphyxia')
        self.assertEqual(data['district'], 'Sirajganj')
        self.assertIn('Neonatal', data['form'])


class LabelsMatchTheVerbatimSuite(TestCase):
    def test_f1_f2_are_reviews_not_notifications(self):
        # The pre-verbatim map called these notifications; the queue then
        # captioned every community review wrongly.
        self.assertIn('Review', SUB_FORM_LABELS['f1'])
        self.assertIn('Maternal', SUB_FORM_LABELS['f1'])
        self.assertIn('Review', SUB_FORM_LABELS['f2'])
        self.assertIn('Neonatal', SUB_FORM_LABELS['f2'])
        self.assertNotIn('Notification', SUB_FORM_LABELS['f1'])
        self.assertNotIn('Notification', SUB_FORM_LABELS['f2'])
