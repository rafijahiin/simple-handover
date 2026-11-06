"""End-to-end guard: a stillbirth review must reach the approval queue and,
once approved, must show on the CIPRB dashboard.

Context. 45 stillbirths are notified and none has ever been reviewed. The four
structured review forms cannot receive one (F-02 has no stillbirth field, F-05
records live-born neonates only), so the ONLY route is the Social Autopsy form,
whose first question offers মৃতজন্ম as option 3.

Two things previously conspired to make such a review invisible even if a
district did submit one:
  * DeathType has no stillbirth member, so ingest folded sa_death_type 3 into
    PERINATAL, indistinguishable from a reviewed neonatal death.
  * The Social Autopsy tile filters to maternal, so it would never show there
    either.

sa_death_kind and review_counts['sb_reviewed'] fixed that. This test walks the
whole path with an option-3 payload so it cannot quietly regress: submitted →
PENDING → visible to the CIPRB approver → approved → counted on the dashboard.
"""

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import Organisation, Role, User
from mpdsr.models import DeathType, MPDSRCase
from programs.ciprb_handlers import handle_ciprb_social_autopsy

# A Social Autopsy submission that reviewed a STILLBIRTH: sa_death_type = 3.
STILLBIRTH_PAYLOAD = {
    '_id': '900001',
    'sa_death_type': '3',
    'meeting_date': '2026-07-20',
    'district': 'Bhola',
    'upazila': 'Char Fasson',
    'slip_number': 'SB-TEST-001',
    'deceased_name': 'Test stillbirth review',
    'death_narrative': 'Committee meeting narrative.',
    'prevention_1': 'Earlier referral',
    'decision_1': 'Strengthen ANC follow-up',
    'collector_name': 'Field Officer',
}

NEONATAL_PAYLOAD = dict(STILLBIRTH_PAYLOAD, _id='900002', sa_death_type='2',
                        slip_number='ND-TEST-001')


class StillbirthReviewReachesApprovalAndDashboard(TestCase):
    def setUp(self):
        # MANAGER is the CIPRB approving role (Tanjina). ORG_LEAD is
        # deliberately view-only, so it is the wrong role for this path.
        self.approver = User.objects.create_user(
            email='tanjina@test.ciprb.org', password='p', full_name='CIPRB Approver',
            organisation=Organisation.CIPRB, role=Role.MANAGER)
        self.client_api = APIClient()
        self.client_api.force_authenticate(self.approver)

    def _submit(self, payload):
        response = handle_ciprb_social_autopsy(payload, 22.5, 90.8)
        self.assertEqual(response.status_code, 200, response.content)
        return MPDSRCase.objects.get(sub_form_type='sa_md',
                                     case_hash='sa:' + payload['slip_number'])

    # ── 1. ingest ──────────────────────────────────────────────────────────
    def test_option_three_is_stored_as_stillbirth_not_lost_in_perinatal(self):
        case = self._submit(STILLBIRTH_PAYLOAD)
        self.assertEqual(case.sa_death_kind, 'stillbirth')
        # death_type stays PERINATAL because DeathType has no stillbirth
        # member; sa_death_kind is what keeps the two apart.
        self.assertEqual(case.death_type, DeathType.PERINATAL)

    def test_a_neonatal_autopsy_is_not_mistaken_for_a_stillbirth(self):
        case = self._submit(NEONATAL_PAYLOAD)
        self.assertEqual(case.sa_death_kind, 'neonatal')

    # ── 2. approval queue ──────────────────────────────────────────────────
    def test_new_stillbirth_review_lands_in_the_queue_as_pending(self):
        case = self._submit(STILLBIRTH_PAYLOAD)
        self.assertEqual(case.approval_status, 'PENDING',
                         'a stillbirth review must never auto-approve')

    def test_the_ciprb_approver_can_see_it_in_pending_approvals(self):
        case = self._submit(STILLBIRTH_PAYLOAD)
        r = self.client_api.get('/api/programs/pending-approvals/')
        self.assertEqual(r.status_code, 200)
        body = r.content.decode()
        self.assertIn('mpdsr_case', body,
                      'MPDSR review cases must be an approvable type')
        self.assertIn(str(case.id), body,
                      'the stillbirth review itself must be in the queue')

    def test_it_can_be_approved_through_the_normal_endpoint(self):
        case = self._submit(STILLBIRTH_PAYLOAD)
        r = self.client_api.post('/api/programs/pending-approvals/', {
            'id': str(case.id), 'model_type': 'mpdsr_case', 'action': 'approve',
            'reason': '',
        }, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        case.refresh_from_db()
        self.assertEqual(case.approval_status, 'APPROVED')

    def test_org_lead_may_read_the_queue_but_never_approve(self):
        # Sayeed's account sees everything and approves nothing (2026-06-20
        # directive). A stillbirth review must not become the exception.
        case = self._submit(STILLBIRTH_PAYLOAD)
        lead = APIClient()
        lead.force_authenticate(User.objects.create_user(
            email='lead@test.ciprb.org', password='p', full_name='CIPRB Lead',
            organisation=Organisation.CIPRB, role=Role.ORG_LEAD))
        self.assertEqual(lead.get('/api/programs/pending-approvals/').status_code, 200)
        r = lead.post('/api/programs/pending-approvals/', {
            'id': str(case.id), 'model_type': 'mpdsr_case', 'action': 'approve',
            'reason': '',
        }, format='json')
        self.assertEqual(r.status_code, 403, r.content)
        case.refresh_from_db()
        self.assertEqual(case.approval_status, 'PENDING')

    # ── 3. dashboard ───────────────────────────────────────────────────────
    def _agg(self):
        r = self.client_api.get('/api/mpdsr/aggregates/')
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()

    def test_pending_review_is_not_counted_before_approval(self):
        self._submit(STILLBIRTH_PAYLOAD)
        self.assertEqual(self._agg()['review_counts'].get('sb_reviewed', 0), 0,
                         'only APPROVED records may reach the dashboard')

    def test_approved_review_appears_on_the_stillbirth_tile(self):
        case = self._submit(STILLBIRTH_PAYLOAD)
        MPDSRCase.objects.filter(pk=case.pk).update(approval_status='APPROVED')
        agg = self._agg()
        self.assertEqual(agg['review_counts']['sb_reviewed'], 1)
        # It must NOT leak into the maternal social-autopsy tile.
        self.assertEqual(agg['social_autopsy']['total'], 0)
        self.assertEqual(agg['social_autopsy']['by_kind']['stillbirth'], 1)

    def test_stillbirth_and_neonatal_reviews_stay_separate_on_the_dashboard(self):
        sb = self._submit(STILLBIRTH_PAYLOAD)
        nd = self._submit(NEONATAL_PAYLOAD)
        MPDSRCase.objects.filter(pk__in=[sb.pk, nd.pk]).update(
            approval_status='APPROVED')
        agg = self._agg()
        self.assertEqual(agg['review_counts']['sb_reviewed'], 1,
                         'the neonatal autopsy must not inflate the stillbirth tile')
        self.assertEqual(agg['social_autopsy']['by_kind']['neonatal'], 1)
        self.assertEqual(sum(agg['social_autopsy']['by_kind'].values()),
                         agg['social_autopsy']['all_kinds_total'])
