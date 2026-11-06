"""?count_only=1 on the approvals queue: the same totals, none of the payload.

The Spine badge polls /api/programs/pending-approvals/ every 30 seconds on every
page, for every signed-in user, and reads exactly one field from the response:
`total`. The full response serialises up to 200 rows per approval model, each
carrying a built summary and narrative — roughly 86 KB an answer, which was 57%
of the deployment's measured HTTP egress and the single largest line on the
Railway bill.

count_only keeps the counts (they come from queries that already ran) and drops
the rows. These tests pin the contract: the numbers must not move, and an empty
`items` must never be mistakable for an empty queue.
"""
import datetime

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import Organisation, Role, User
from programs.models import ServiceCenter, OutreachSession


def _user(email, org, role):
    return User.objects.create_user(
        email=email, password='Str0ng-Passw0rd-2026', full_name='T',
        organisation=org, role=role)


class PendingApprovalsCountOnlyTest(TestCase):
    def setUp(self):
        self.centre = ServiceCenter.objects.create(
            organisation='Bandhu', name='DIC', code='BND-DIC-CO',
            center_type='DIC', district='Dhaka')
        self.phd_centre = ServiceCenter.objects.create(
            organisation='PHD', name='DIC2', code='PHD-DIC-CO',
            center_type='DIC', district='Dhaka')
        self.dev = _user('dev@co.org', Organisation.CIPRB, Role.DEVELOPER)
        for i in range(3):
            OutreachSession.objects.create(
                organisation='Bandhu', center=self.centre,
                session_date=datetime.date.today(),
                peer_educator_name='PE%d' % i)
        OutreachSession.objects.create(
            organisation='PHD', center=self.phd_centre,
            session_date=datetime.date.today(), peer_educator_name='PE-PHD')
        self.client_api = APIClient()
        self.client_api.force_authenticate(self.dev)

    def _get(self, **params):
        r = self.client_api.get('/api/programs/pending-approvals/', params)
        self.assertEqual(r.status_code, 200)
        return r.json()

    def test_total_is_identical_to_the_full_response(self):
        self.assertEqual(self._get(count_only=1)['total'], self._get()['total'])

    def test_counts_by_org_is_identical_to_the_full_response(self):
        self.assertEqual(self._get(count_only=1)['counts_by_org'],
                         self._get()['counts_by_org'])
        self.assertEqual(self._get(count_only=1)['counts_by_org']['Bandhu'], 3)

    def test_items_are_dropped(self):
        self.assertEqual(self._get(count_only=1)['items'], [])
        self.assertEqual(self._get(count_only=1)['returned'], 0)

    def test_an_empty_items_list_is_flagged_not_implied(self):
        # `truncated` exists so the UI never reads a capped page as a drained
        # queue. count_only drops every row, so it must say so just as loudly.
        body = self._get(count_only=1)
        self.assertIs(body['count_only'], True)
        self.assertIs(body['truncated'], True)

    def test_full_response_still_says_it_is_not_count_only(self):
        self.assertIs(self._get()['count_only'], False)

    def test_counts_by_type_is_the_true_backlog_not_a_capped_page(self):
        self.assertEqual(self._get(count_only=1)['counts_by_type'],
                         {'outreach_session': 4})

    def test_the_full_payload_is_unchanged_when_the_flag_is_absent(self):
        body = self._get()
        self.assertEqual(len(body['items']), 4)
        self.assertEqual(body['returned'], 4)

    def test_falsey_values_do_not_switch_the_mode_on(self):
        for v in ('0', 'false', ''):
            self.assertEqual(len(self._get(count_only=v)['items']), 4, v)

    def test_role_scoping_still_applies(self):
        # UNFPA's lane is stage-2 only (Bandhu MANAGER_APPROVED). Nothing here
        # has reached that stage, so the badge must read zero — the cheap path
        # must not accidentally count another role's queue.
        unfpa = _user('u@co.org', Organisation.UNFPA, Role.SUPERVISOR)
        c = APIClient()
        c.force_authenticate(unfpa)
        r = c.get('/api/programs/pending-approvals/', {'count_only': 1})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['total'], 0)

    def test_reviewed_mode_still_works_with_count_only(self):
        body = self._get(count_only=1, status='reviewed')
        self.assertEqual(body['total'], 0)
        self.assertEqual(body['items'], [])
