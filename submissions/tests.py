import hashlib
import hmac
import json
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import Organisation, Role, User
from .models import FormType, KoboSubmission, SubmissionStatus

WEBHOOK_URL = '/webhook/kobo/'

TEST_UIDS = {
    'KOBO_ASSET_UID_MPDSR': 'uid_mpdsr',
    'KOBO_ASSET_UID_FISTULA': 'uid_fistula',
    'KOBO_ASSET_UID_ACTIVITY': 'uid_activity',
    'KOBO_ASSET_UID_BASELINE': 'uid_baseline',
    # Webhook validator is fail-closed — every test that hits the webhook
    # must authenticate. Tests that exercise the ingestion path pass this
    # plain token in the Authorization header (see TEST_AUTH).
    'KOBO_WEBHOOK_SECRET': 'testsecret',
}

# Every WebhookIngestTest POST needs this header. WebhookSignatureTest
# uses a different secret per its own override_settings.
TEST_AUTH = {'HTTP_AUTHORIZATION': 'Token testsecret'}


def make_user(email, org, role):
    return User.objects.create_user(
        email=email, password='pass123',
        full_name='Test', organisation=org, role=role,
    )


def mpdsr_payload(**overrides):
    base = {
        '_id': '1001',
        '_xform_id_string': 'uid_mpdsr',
        '_submission_time': '2024-06-01T08:00:00',
        '_geolocation': [23.7104, 90.4074],
        'partner': 'PHD',
        'worker_name': 'Rina Akter',
        'district': 'Dhaka',
        'division': 'Dhaka',
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Webhook — ingestion
# ---------------------------------------------------------------------------

@override_settings(**TEST_UIDS)
class WebhookIngestTest(TestCase):

    @patch('submissions.views.send_submission_alert')
    def test_valid_payload_creates_submission(self, mock_tg):
        # MPDSR is CIPRB-owned surveillance: the record is always attributed to
        # CIPRB regardless of the collector org named in the payload, and lands
        # PENDING for the manager-approval path. Nothing auto-approves at ingest
        # any more — every form goes through the approval queue.
        payload = mpdsr_payload()
        resp = self.client.post(
            WEBHOOK_URL, data=json.dumps(payload), content_type='application/json', **TEST_AUTH
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(KoboSubmission.objects.count(), 1)
        sub = KoboSubmission.objects.first()
        self.assertEqual(sub.form_type, FormType.MPDSR)
        self.assertEqual(sub.partner, 'CIPRB')
        self.assertEqual(sub.worker_name, 'Rina Akter')
        self.assertEqual(sub.district, 'Dhaka')
        self.assertEqual(sub.status, SubmissionStatus.PENDING)
        mock_tg.assert_called_once()

    @patch('submissions.views.send_submission_alert')
    def test_duplicate_kobo_id_is_idempotent(self, _):
        payload = mpdsr_payload()
        self.client.post(WEBHOOK_URL, data=json.dumps(payload), content_type='application/json', **TEST_AUTH)
        resp = self.client.post(WEBHOOK_URL, data=json.dumps(payload), content_type='application/json', **TEST_AUTH)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(KoboSubmission.objects.count(), 1)

    def test_unknown_form_uid_returns_400(self):
        payload = mpdsr_payload(_xform_id_string='uid_unknown')
        resp = self.client.post(WEBHOOK_URL, data=json.dumps(payload), content_type='application/json', **TEST_AUTH)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(KoboSubmission.objects.count(), 0)

    def test_missing_kobo_id_returns_400(self):
        payload = mpdsr_payload()
        del payload['_id']
        resp = self.client.post(WEBHOOK_URL, data=json.dumps(payload), content_type='application/json', **TEST_AUTH)
        self.assertEqual(resp.status_code, 400)

    def test_invalid_json_returns_400(self):
        resp = self.client.post(WEBHOOK_URL, data='not-json', content_type='application/json', **TEST_AUTH)
        self.assertEqual(resp.status_code, 400)

    def test_get_method_not_allowed(self):
        resp = self.client.get(WEBHOOK_URL)
        self.assertEqual(resp.status_code, 405)

    @patch('submissions.views.send_submission_alert')
    def test_fistula_form_type_detected(self, _):
        payload = mpdsr_payload(_xform_id_string='uid_fistula', _id='2001')
        resp = self.client.post(WEBHOOK_URL, data=json.dumps(payload), content_type='application/json', **TEST_AUTH)
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(KoboSubmission.objects.first().form_type, FormType.FISTULA)

    @patch('submissions.views.send_submission_alert')
    def test_fistula_lands_pending(self, _):
        """Audit FIX 2.7 — fistula no longer auto-approves."""
        payload = mpdsr_payload(_xform_id_string='uid_fistula', _id='2002')
        resp = self.client.post(WEBHOOK_URL, data=json.dumps(payload), content_type='application/json', **TEST_AUTH)
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(KoboSubmission.objects.first().status, SubmissionStatus.PENDING)

    @patch('submissions.views.send_submission_alert')
    def test_baseline_auto_approves(self, _):
        """Baseline is a CIPRB-run research survey, not a service record: there is
        nothing for a manager to approve, so it lands APPROVED at ingest (the D5
        verification gate of 2026-06-25 was retired). Still attributed to CIPRB."""
        payload = mpdsr_payload(_xform_id_string='uid_baseline', _id='2003')
        resp = self.client.post(WEBHOOK_URL, data=json.dumps(payload), content_type='application/json', **TEST_AUTH)
        self.assertEqual(resp.status_code, 201)
        sub = KoboSubmission.objects.first()
        self.assertEqual(sub.status, SubmissionStatus.APPROVED)
        self.assertEqual(sub.partner, 'CIPRB')

    @patch('submissions.views.send_submission_alert')
    def test_mpdsr_forced_to_ciprb_regardless_of_payload_partner(self, _):
        """MPDSR ownership rests with CIPRB: even a payload naming Bandhu/PHD as
        the collector is stored as partner='CIPRB' (CIPRB-owned surveillance)."""
        payload = mpdsr_payload(partner='Bandhu', _id='3001')
        resp = self.client.post(WEBHOOK_URL, data=json.dumps(payload), content_type='application/json', **TEST_AUTH)
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(KoboSubmission.objects.first().partner, 'CIPRB')

    @patch('submissions.views.send_submission_alert')
    def test_geolocation_extracted(self, _):
        resp = self.client.post(
            WEBHOOK_URL, data=json.dumps(mpdsr_payload()), content_type='application/json', **TEST_AUTH
        )
        self.assertEqual(resp.status_code, 201)
        sub = KoboSubmission.objects.first()
        self.assertAlmostEqual(float(sub.latitude), 23.7104, places=4)
        self.assertAlmostEqual(float(sub.longitude), 90.4074, places=4)

    @patch('submissions.views.send_submission_alert')
    def test_raw_data_stored(self, _):
        payload = mpdsr_payload()
        self.client.post(WEBHOOK_URL, data=json.dumps(payload), content_type='application/json', **TEST_AUTH)
        sub = KoboSubmission.objects.first()
        self.assertEqual(sub.raw_data['_id'], '1001')


# ---------------------------------------------------------------------------
# Webhook — signature validation
# ---------------------------------------------------------------------------

@override_settings(**{**TEST_UIDS, 'KOBO_WEBHOOK_SECRET': 'testsecret'})
class WebhookSignatureTest(TestCase):

    def _signed_post(self, payload: dict):
        body = json.dumps(payload).encode()
        sig = hmac.new(b'testsecret', body, hashlib.sha256).hexdigest()
        return self.client.post(
            WEBHOOK_URL,
            data=body,
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Token {sig}',
        )

    @patch('submissions.views.send_submission_alert')
    def test_valid_hmac_accepted(self, _):
        resp = self._signed_post(mpdsr_payload())
        self.assertEqual(resp.status_code, 201)

    def test_missing_signature_rejected(self):
        payload = mpdsr_payload()
        resp = self.client.post(
            WEBHOOK_URL, data=json.dumps(payload), content_type='application/json'
        )
        self.assertEqual(resp.status_code, 403)

    def test_wrong_hmac_rejected(self):
        body = json.dumps(mpdsr_payload()).encode()
        resp = self.client.post(
            WEBHOOK_URL,
            data=body,
            content_type='application/json',
            HTTP_AUTHORIZATION='Token deadbeef',
        )
        self.assertEqual(resp.status_code, 403)

    @patch('submissions.views.send_submission_alert')
    def test_valid_query_token_accepted(self, _):
        payload = mpdsr_payload()
        resp = self.client.post(
            WEBHOOK_URL + '?token=testsecret',
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 201)


# ---------------------------------------------------------------------------
# Webhook — fail-closed behaviour when KOBO_WEBHOOK_SECRET is unset/empty
# ---------------------------------------------------------------------------

@override_settings(**{**TEST_UIDS, 'KOBO_WEBHOOK_SECRET': ''})
class WebhookFailClosedTest(TestCase):
    """
    When KOBO_WEBHOOK_SECRET is empty (env var missing or blank in
    Railway), every webhook request must be REJECTED with 403. There
    is no 'accept anything' mode — an open webhook on a public host
    accepts arbitrary writes from the internet.
    """

    def _post(self, **kwargs):
        return self.client.post(
            WEBHOOK_URL,
            data=json.dumps(mpdsr_payload()),
            content_type='application/json',
            **kwargs,
        )

    def test_no_auth_header_rejected(self):
        self.assertEqual(self._post().status_code, 403)
        self.assertEqual(KoboSubmission.objects.count(), 0)

    def test_auth_header_with_value_still_rejected(self):
        """Even a 'correct' header value cannot pass when secret is empty."""
        resp = self._post(HTTP_AUTHORIZATION='Token anything')
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(KoboSubmission.objects.count(), 0)

    def test_query_token_rejected(self):
        resp = self.client.post(
            WEBHOOK_URL + '?token=anything',
            data=json.dumps(mpdsr_payload()),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(KoboSubmission.objects.count(), 0)


# ---------------------------------------------------------------------------
# Manager approval API
# ---------------------------------------------------------------------------

@override_settings(**TEST_UIDS)
class SubmissionApiTest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.phd_manager = make_user('pm@phd.org', Organisation.PHD, Role.MANAGER)
        self.bondhu_manager = make_user('bm@bandhu.org', Organisation.BANDHU, Role.MANAGER)

    def _make_submission(self, partner='PHD', form_type=FormType.MPDSR, kobo_id='sub-001'):
        return KoboSubmission.objects.create(
            kobo_id=kobo_id,
            form_type=form_type,
            partner=partner,
            worker_name='Rina',
            district='Dhaka',
            region='Dhaka',
            submitted_at='2024-06-01T08:00:00+00:00',
            raw_data={'_id': kobo_id},
        )

    def test_phd_manager_sees_only_phd_submissions(self):
        self._make_submission(partner='PHD', kobo_id='s-phd')
        self._make_submission(partner='Bandhu', kobo_id='s-bondhu')
        self.client.force_authenticate(user=self.phd_manager)
        resp = self.client.get('/api/submissions/')
        self.assertEqual(resp.status_code, 200)
        # No global pagination — endpoint returns a plain list.
        results = resp.data if isinstance(resp.data, list) else resp.data['results']
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['partner'], 'PHD')

    def test_bondhu_manager_cannot_see_phd_submissions(self):
        self._make_submission(partner='PHD', kobo_id='s-phd')
        self.client.force_authenticate(user=self.bondhu_manager)
        resp = self.client.get('/api/submissions/')
        self.assertEqual(resp.status_code, 200)
        results = resp.data if isinstance(resp.data, list) else resp.data['results']
        self.assertEqual(len(results), 0)

    def test_unauthenticated_returns_403(self):
        resp = self.client.get('/api/submissions/')
        self.assertEqual(resp.status_code, 403)

    def test_approve_changes_status(self):
        sub = self._make_submission()
        self.client.force_authenticate(user=self.phd_manager)
        resp = self.client.post(f'/api/submissions/{sub.id}/approve/')
        self.assertEqual(resp.status_code, 200)
        sub.refresh_from_db()
        self.assertEqual(sub.status, SubmissionStatus.APPROVED)
        self.assertEqual(sub.reviewed_by, self.phd_manager)
        self.assertIsNotNone(sub.reviewed_at)

    def test_reject_records_reason(self):
        sub = self._make_submission()
        self.client.force_authenticate(user=self.phd_manager)
        resp = self.client.post(
            f'/api/submissions/{sub.id}/reject/',
            {'rejection_reason': 'Duplicate entry'},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        sub.refresh_from_db()
        self.assertEqual(sub.status, SubmissionStatus.REJECTED)
        self.assertEqual(sub.rejection_reason, 'Duplicate entry')

    def test_reject_requires_reason(self):
        sub = self._make_submission()
        self.client.force_authenticate(user=self.phd_manager)
        resp = self.client.post(
            f'/api/submissions/{sub.id}/reject/',
            {'rejection_reason': ''},
            format='json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_cannot_approve_already_approved(self):
        sub = self._make_submission()
        sub.status = SubmissionStatus.APPROVED
        sub.save()
        self.client.force_authenticate(user=self.phd_manager)
        resp = self.client.post(f'/api/submissions/{sub.id}/approve/')
        self.assertEqual(resp.status_code, 400)

    def test_cannot_reject_already_rejected(self):
        sub = self._make_submission()
        sub.status = SubmissionStatus.REJECTED
        sub.save()
        self.client.force_authenticate(user=self.phd_manager)
        resp = self.client.post(
            f'/api/submissions/{sub.id}/reject/',
            {'rejection_reason': 'Again'},
            format='json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_create_via_api_returns_405(self):
        self.client.force_authenticate(user=self.phd_manager)
        resp = self.client.post('/api/submissions/', {'kobo_id': 'x'}, format='json')
        self.assertEqual(resp.status_code, 405)

    def test_detail_includes_raw_data(self):
        sub = self._make_submission()
        self.client.force_authenticate(user=self.phd_manager)
        resp = self.client.get(f'/api/submissions/{sub.id}/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('raw_data', resp.data)

    def test_phd_manager_cannot_approve_bondhu_submission(self):
        sub = self._make_submission(partner='Bandhu', kobo_id='bondhu-sub')
        self.client.force_authenticate(user=self.phd_manager)
        resp = self.client.post(f'/api/submissions/{sub.id}/approve/')
        self.assertEqual(resp.status_code, 404)  # OrgFilterMixin hides it


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------

@override_settings(**TEST_UIDS)
class SignalTest(TestCase):

    def _make_pending(self):
        return KoboSubmission.objects.create(
            kobo_id='sig-001',
            form_type=FormType.FISTULA,
            partner='PHD',
            worker_name='Rina',
            district='Dhaka',
            region='Dhaka',
            submitted_at='2024-06-01T08:00:00+00:00',
            raw_data={},
        )

    def test_approving_fistula_does_not_raise(self):
        """Signal fires but FistulaCase doesn't exist yet — must fail silently."""
        sub = self._make_pending()
        sub.status = SubmissionStatus.APPROVED
        sub.save()  # triggers signal
        sub.refresh_from_db()
        self.assertEqual(sub.status, SubmissionStatus.APPROVED)

    def test_pending_status_does_not_trigger_case_creation(self):
        sub = self._make_pending()
        sub.save()
        sub.refresh_from_db()
        self.assertEqual(sub.status, SubmissionStatus.PENDING)


@override_settings(**TEST_UIDS)
class BaselineExcludedFromSubmissionsQueueTest(TestCase):
    """Regression: baseline interviews have their own CIPRB verification queue
    (/api/baseline/verification/) and must NOT leak into the generic approval
    queue (/api/submissions/) at ANY status — otherwise the frontend renders
    them as a wrong kind='legacy' card in the CIPRB tab, and they become
    approvable via /submissions/<id>/approve/ (CanApproveSubmissions),
    side-stepping the narrower CanApproveBaseline gate."""

    def setUp(self):
        self.client = APIClient()
        # A CIPRB manager sees all orgs and passes both CanApproveSubmissions and
        # CanViewBaseline — one user exercises both endpoints.
        self.ciprb_manager = make_user('tanjina@ciprb.org', Organisation.CIPRB, Role.MANAGER)
        self.client.force_authenticate(user=self.ciprb_manager)

    def _mk(self, form_type, status, kobo_id):
        sub = KoboSubmission.objects.create(
            kobo_id=kobo_id, form_type=form_type, partner='CIPRB',
            worker_name='Enum', district='Dhaka', region='Dhaka',
            submitted_at='2024-06-01T08:00:00+00:00',
            raw_data={'population': 'hijra', 'questionnaire_serial': 'H-9', '_id': kobo_id},
            status=SubmissionStatus.PENDING,
        )
        if status != SubmissionStatus.PENDING:
            # .update() bypasses the approval post_save signal — this test only
            # needs the row to carry the target status, not to materialise.
            KoboSubmission.objects.filter(pk=sub.pk).update(status=status)
        return sub

    def _form_types(self, status):
        resp = self.client.get('/api/submissions/', {'status': status})
        self.assertEqual(resp.status_code, 200)
        rows = resp.data if isinstance(resp.data, list) else resp.data['results']
        return [r['form_type'] for r in rows]

    def test_pending_baseline_absent_from_submissions_queue(self):
        self._mk(FormType.BASELINE, SubmissionStatus.PENDING, 'bl-p')
        self._mk(FormType.FISTULA, SubmissionStatus.PENDING, 'fi-p')  # control stays
        fts = self._form_types(SubmissionStatus.PENDING)
        self.assertNotIn(FormType.BASELINE, fts)
        self.assertIn(FormType.FISTULA, fts)

    def test_approved_baseline_absent_from_submissions_queue(self):
        self._mk(FormType.BASELINE, SubmissionStatus.APPROVED, 'bl-a')
        self.assertNotIn(FormType.BASELINE, self._form_types(SubmissionStatus.APPROVED))

    def test_rejected_baseline_absent_from_submissions_queue(self):
        self._mk(FormType.BASELINE, SubmissionStatus.REJECTED, 'bl-r')
        self.assertNotIn(FormType.BASELINE, self._form_types(SubmissionStatus.REJECTED))

    def test_baseline_detail_not_reachable_via_submissions(self):
        # Closes the approve side-door: get_object() shares get_queryset, so a
        # baseline id 404s on /submissions/<id>/ (and thus approve/reject).
        sub = self._mk(FormType.BASELINE, SubmissionStatus.PENDING, 'bl-d')
        resp = self.client.get(f'/api/submissions/{sub.pk}/')
        self.assertEqual(resp.status_code, 404)

    def test_pending_baseline_still_in_verification_queue(self):
        self._mk(FormType.BASELINE, SubmissionStatus.PENDING, 'bl-v')
        resp = self.client.get('/api/baseline/verification/')
        self.assertEqual(resp.status_code, 200)
        rows = resp.data if isinstance(resp.data, list) else resp.data.get('results', [])
        self.assertEqual(len(rows), 1)
